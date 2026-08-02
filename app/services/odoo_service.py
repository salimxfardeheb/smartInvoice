"""Service de synchronisation avec Odoo (phase 5).

À partir des données extraites par l'OCR (nom du fournisseur, référence du
bon de commande), ce service interroge Odoo via :class:`app.odoo.OdooClient`
et alimente le cache local :

- ``res.partner`` → table ``suppliers`` (recherche par nom) ;
- ``purchase.order`` → table ``purchase_orders`` (recherche par référence) ;
- ``purchase.order.line`` → table ``purchase_order_lines`` (chargement des
  lignes d'un BC).

Chaque cas particulier est géré par une exception dédiée :
:class:`SupplierNotFoundError` / :class:`MultipleSuppliersFoundError` pour le
fournisseur, :class:`PurchaseOrderNotFoundError` /
:class:`MultiplePurchaseOrdersError` / :class:`PurchaseOrderCancelledError`
pour le bon de commande. Les erreurs réseau/Odoo remontent telles quelles du
client (:class:`OdooError` et ses sous-classes).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.core.exceptions import (
    MultiplePurchaseOrdersError,
    MultipleSuppliersFoundError,
    PurchaseOrderCancelledError,
    PurchaseOrderNotFoundError,
    SupplierNotFoundError,
)
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.supplier import Supplier
from app.odoo import OdooClient
from app.repositories import (
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
    SupplierRepository,
)

# Champs lus dans Odoo (une seule requête par entité).
_PARTNER_FIELDS = [
    "id", "name", "vat", "email", "phone", "street", "zip", "city",
    "supplier_rank",
]
_PO_FIELDS = ["id", "name", "partner_id", "state", "date_order", "amount_total", "currency_id"]
_PO_LINE_FIELDS = [
    "id", "order_id", "sequence", "product_id", "name", "product_qty",
    "product_uom", "price_unit", "discount", "price_subtotal",
]
_PRODUCT_FIELDS = ["id", "default_code"]

# État Odoo d'un bon de commande annulé.
_CANCELLED_STATES = ("cancel",)

# Limites de recherche (évitent des réponses gigantesques).
_PARTNER_SEARCH_LIMIT = 20
_PO_SEARCH_LIMIT = 20
_PO_LINE_LIMIT = 500


class OdooSyncService:
    """Synchronise les référentiels Odoo vers le cache local SmartInvoice."""

    def __init__(self, db: Session, client: OdooClient | None = None) -> None:
        self.db = db
        self.client = client or OdooClient()
        self.suppliers = SupplierRepository(db)
        self.purchase_orders = PurchaseOrderRepository(db)
        self.purchase_order_lines = PurchaseOrderLineRepository(db)

    # --- Fournisseur -----------------------------------------------------------

    def sync_supplier_from_name(self, name: str) -> Supplier:
        """Retrouve un fournisseur Odoo par nom et le met en cache local.

        Lève :class:`SupplierNotFoundError` si aucun fournisseur ne
        correspond, :class:`MultipleSuppliersFoundError` si plusieurs
        correspondances (un seul nom exact est toléré) subsistent.
        """
        if not name or not name.strip():
            raise SupplierNotFoundError("Le nom du fournisseur extrait est vide.")

        matches = self.client.search_read(
            "res.partner",
            self._partner_domain(name),
            _PARTNER_FIELDS,
            limit=_PARTNER_SEARCH_LIMIT,
        )
        if not matches:
            raise SupplierNotFoundError(
                f"Aucun fournisseur trouvé dans Odoo pour « {name.strip()} »."
            )
        return self._upsert_supplier(self._resolve_unique_partner(matches, name))

    def _partner_domain(self, name: str) -> list:
        """Domaine de recherche des fournisseurs (``res.partner``, Odoo 16+)."""
        return [["name", "ilike", name], ["supplier_rank", ">", 0]]

    def _resolve_unique_partner(self, matches: list[dict], name: str) -> dict:
        """Retourne l'unique correspondance, en privilégiant un nom exact."""
        exact = [m for m in matches if self._normalize(m.get("name")) == self._normalize(name)]
        if len(exact) == 1:
            return exact[0]
        raise MultipleSuppliersFoundError(
            "Plusieurs fournisseurs correspondent à « "
            + name.strip()
            + " » : "
            + ", ".join(str(m.get("name")) for m in exact or matches)
            + "."
        )

    def _upsert_supplier(self, data: dict) -> Supplier:
        """Crée ou met à jour le fournisseur local à partir du partenaire Odoo."""
        odoo_id = int(data["id"])
        fields = {
            "name": data.get("name") or "Fournisseur",
            "vat": data.get("vat"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "address": self._format_address(data),
        }
        supplier = self.suppliers.get_by_odoo_id(odoo_id)
        if supplier is None:
            supplier = self.suppliers.create(odoo_id=odoo_id, **fields)
        else:
            self.suppliers.update(supplier, **fields)
        return supplier

    # --- Bon de commande ---------------------------------------------------------

    def find_purchase_order(
        self, reference: str, *, supplier: Supplier | None = None
    ) -> PurchaseOrder:
        """Retrouve un bon de commande Odoo par référence et le met en cache.

        Si ``supplier`` est fourni, la recherche est restreinte à ce
        fournisseur. Lève :class:`PurchaseOrderNotFoundError` si aucun BC ne
        correspond, :class:`MultiplePurchaseOrdersError` si plusieurs,
        :class:`PurchaseOrderCancelledError` si le BC trouvé est annulé.
        """
        if not reference or not reference.strip():
            raise PurchaseOrderNotFoundError("La référence du bon de commande est vide.")

        domain = [["name", "=", reference.strip()]]
        if supplier is not None:
            domain.append(["partner_id", "=", supplier.odoo_id])

        matches = self.client.search_read(
            "purchase.order", domain, _PO_FIELDS, limit=_PO_SEARCH_LIMIT
        )
        if not matches:
            raise PurchaseOrderNotFoundError(
                f"Aucun bon de commande trouvé dans Odoo pour « {reference.strip()} »."
            )
        if len(matches) > 1:
            raise MultiplePurchaseOrdersError(
                "Plusieurs bons de commande correspondent à la référence « "
                f"{reference.strip()} »."
            )

        data = matches[0]
        if data.get("state") in _CANCELLED_STATES:
            raise PurchaseOrderCancelledError(
                f"Le bon de commande « {reference.strip()} » est annulé."
            )

        supplier = supplier or self._supplier_for_order(data)
        return self._upsert_purchase_order(data, supplier)

    def _supplier_for_order(self, data: dict) -> Supplier:
        """Retrouve le fournisseur local correspondant au partenaire du BC."""
        partner_id = data.get("partner_id")
        odoo_partner_id = (
            partner_id[0] if isinstance(partner_id, (list, tuple)) else partner_id
        )
        supplier = self.suppliers.get_by_odoo_id(int(odoo_partner_id))
        if supplier is None:
            raise SupplierNotFoundError(
                "Le fournisseur du bon de commande n'est pas encore synchronisé ; "
                "synchronisez-le d'abord."
            )
        return supplier

    def _upsert_purchase_order(self, data: dict, supplier: Supplier) -> PurchaseOrder:
        """Crée ou met à jour le bon de commande local à partir d'Odoo."""
        odoo_id = int(data["id"])
        fields = {
            "reference": data.get("name"),
            "supplier_id": supplier.id,
            "state": data.get("state"),
            "currency": self._currency_code(data.get("currency_id")),
            "date_order": self._as_date(data.get("date_order")),
            "total_amount": self._as_decimal(data.get("amount_total")),
        }
        purchase_order = self.purchase_orders.get_by_odoo_id(odoo_id)
        if purchase_order is None:
            purchase_order = self.purchase_orders.create(odoo_id=odoo_id, **fields)
        else:
            self.purchase_orders.update(purchase_order, **fields)
        return purchase_order

    # --- Lignes du bon de commande ------------------------------------------------

    def load_purchase_order_lines(
        self, purchase_order: PurchaseOrder
    ) -> list[PurchaseOrderLine]:
        """Charge les lignes d'un BC depuis Odoo et met à jour le cache local.

        Les lignes sont identifiées par leur ``odoo_id`` : créées si absentes,
        mises à jour sinon. La référence produit est résolue en un second appel
        sur ``product.product``.
        """
        rows = self.client.search_read(
            "purchase.order.line",
            [["order_id", "=", purchase_order.odoo_id]],
            _PO_LINE_FIELDS,
            limit=_PO_LINE_LIMIT,
        )
        product_ids = {
            int(row["product_id"][0])
            for row in rows
            if isinstance(row.get("product_id"), (list, tuple)) and row["product_id"]
        }
        refs = self._load_product_refs(sorted(product_ids)) if product_ids else {}

        lines: list[PurchaseOrderLine] = []
        for index, row in enumerate(rows):
            lines.append(self._upsert_line(purchase_order, row, index, refs))
        return lines

    def _load_product_refs(self, product_ids: list[int]) -> dict[int, str]:
        """Retourne ``{id produit: référence interne}`` depuis ``product.product``."""
        rows = self.client.search_read(
            "product.product",
            [["id", "in", product_ids]],
            _PRODUCT_FIELDS,
            limit=len(product_ids),
        )
        return {int(row["id"]): row.get("default_code") for row in rows}

    def _upsert_line(
        self,
        purchase_order: PurchaseOrder,
        row: dict,
        index: int,
        refs: dict[int, str],
    ) -> PurchaseOrderLine:
        """Crée ou met à jour une ligne de BC dans le cache local."""
        odoo_id = int(row["id"])
        fields = {
            "purchase_order_id": purchase_order.id,
            "line_number": int(row.get("sequence") or index + 1),
            "product_ref": self._product_ref(row, refs),
            "name": row.get("name"),
            "quantity": self._as_decimal(row.get("product_qty")),
            "unit": self._name_of(row.get("product_uom")),
            "unit_price": self._as_decimal(row.get("price_unit")),
            "discount": self._as_decimal(row.get("discount")),
            "amount": self._as_decimal(row.get("price_subtotal")),
        }
        line = self.purchase_order_lines.get_by_odoo_id(odoo_id)
        if line is None:
            line = self.purchase_order_lines.create(odoo_id=odoo_id, **fields)
        else:
            self.purchase_order_lines.update(line, **fields)
        return line

    def _product_ref(self, row: dict, refs: dict[int, str]) -> str | None:
        """Référence interne du produit de la ligne (``None`` si inconnue)."""
        product_id = row.get("product_id")
        odoo_product_id = (
            product_id[0] if isinstance(product_id, (list, tuple)) else product_id
        )
        if not odoo_product_id:
            return None
        return refs.get(int(odoo_product_id))

    # --- Helpers de conversion ------------------------------------------------------

    @staticmethod
    def _normalize(value: str | None) -> str:
        """Normalise un nom pour la comparaison (minuscules, espaces réduits)."""
        return " ".join((value or "").strip().lower().split())

    @staticmethod
    def _format_address(data: dict) -> str | None:
        """Assemble rue + code postal + ville en une adresse lisible."""
        parts = [data.get("street"), data.get("zip"), data.get("city")]
        address = ", ".join(str(p) for p in parts if p)
        return address or None

    @staticmethod
    def _name_of(value) -> str | None:
        """Nom d'un champ relationnel Odoo (tuple ``(id, nom)``)."""
        if isinstance(value, (list, tuple)) and len(value) >= 2 and value[1]:
            return str(value[1])
        return None

    @staticmethod
    def _currency_code(value) -> str:
        """Code devise depuis ``currency_id`` Odoo (défaut EUR)."""
        code = OdooSyncService._name_of(value)
        return code if code else "EUR"

    @staticmethod
    def _as_decimal(value) -> Decimal | None:
        """Convertit une valeur Odoo en ``Decimal`` (``None`` si absente)."""
        if value is None or isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _as_date(value) -> date | None:
        """Convertit une date Odoo en ``date`` (``None`` si illisible)."""
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, datetime):  # pragma: no cover - datetime ⊂ date, déjà couvert ci-dessus
            return value.date()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None
