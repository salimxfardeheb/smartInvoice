"""Service de rapprochement facture ↔ bon de commande (phase 6 - matching).

Compare une facture (dont les données ont été extraites par l'OCR) au bon de
commande Odoo mis en cache localement, puis :

- vérifie le fournisseur (facture ↔ ``res.partner``) ;
- rapproche les lignes de facture avec les lignes du BC (produit) ;
- calcule les écarts de quantité et de prix unitaire ligne à ligne ;
- compare les montants (HT, TTC) et la TVA avec le bon de commande ;
- calcule un score de matching global (0..1) et le persiste sur la facture ;
- détecte et enregistre les anomalies par catégorie : montant, TVA,
  quantité, produit absent, doublon, fournisseur, bon de commande.

L'orchestration se fait via :meth:`MatchingService.match`, pensée pour être
appelée après l'analyse OCR (le BC devant avoir été synchronisé au préalable
par :class:`app.services.odoo_service.OdooSyncService`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import AnomalyCategory, AnomalySeverity
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.repositories import (
    AnomalyRepository,
    InvoiceLineRepository,
    InvoiceRepository,
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
    SettingRepository,
)

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.anomaly import Anomaly

# Seuil de similarité des noms (descriptions / fournisseurs) pour la
# correspondance « floue » (difflib), en complément des correspondances exactes.
_NAME_MATCH_THRESHOLD = 0.9

# Poids des composantes du score de matching global (la somme vaut 1.0).
_SCORE_WEIGHTS: dict[str, float] = {
    "supplier": 0.10,
    "purchase_order": 0.20,
    "product": 0.25,
    "quantity": 0.15,
    "price": 0.15,
    "amount": 0.15,
}

# Catégories d'anomalies gérées par le matching : elles sont nettoyées à
# chaque nouveau passage (idempotence) pour éviter les doublons. Les anomalies
# issues de l'OCR (catégorie « autre ») sont préservées.
_MATCHING_CATEGORIES: frozenset[AnomalyCategory] = frozenset(
    {
        AnomalyCategory.AMOUNT,
        AnomalyCategory.TAX,
        AnomalyCategory.QUANTITY,
        AnomalyCategory.PRODUCT_MISSING,
        AnomalyCategory.DUPLICATE,
        AnomalyCategory.SUPPLIER,
        AnomalyCategory.PURCHASE_ORDER,
    }
)


@dataclass(frozen=True)
class LineMatch:
    """Résultat du rapprochement d'une ligne de facture avec une ligne de BC.

    ``quantity_delta`` et ``unit_price_delta`` sont des écarts relatifs
    (fractions, ex. ``0.05`` pour 5 %). Une ligne est « matchée » dès qu'une
    ligne de BC correspondante a été trouvée (``purchase_order_line``).
    """

    invoice_line: InvoiceLine
    purchase_order_line: PurchaseOrderLine | None = None
    quantity_matched: bool = False
    unit_price_matched: bool = False
    quantity_delta: float | None = None
    unit_price_delta: float | None = None

    @property
    def matched(self) -> bool:
        """Indique si une ligne de BC a été associée à la ligne de facture."""
        return self.purchase_order_line is not None


@dataclass(frozen=True)
class MatchingResult:
    """Résultat complet d'un passage de matching.

    ``score`` est la moyenne pondérée des composantes (fournisseur, BC,
    produits, quantités, prix, montants). ``anomalies`` liste les anomalies
    créées lors de ce passage.
    """

    invoice_id: int
    supplier_match: bool = False
    duplicate_found: bool = False
    purchase_order: PurchaseOrder | None = None
    line_matches: list[LineMatch] = field(default_factory=list)
    score: float = 0.0
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def matched_line_count(self) -> int:
        """Nombre de lignes de facture rapprochées avec une ligne de BC."""
        return sum(1 for match in self.line_matches if match.matched)


class MatchingService:
    """Rapproche une facture à son bon de commande et enregistre le résultat.

    Les tolérances d'écart sont lues depuis la configuration
    (:attr:`app.core.config.Settings.matching_*_tolerance`).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.lines = InvoiceLineRepository(db)
        self.anomalies = AnomalyRepository(db)
        self.purchase_orders = PurchaseOrderRepository(db)
        self.purchase_order_lines = PurchaseOrderLineRepository(db)

        # Tolérances effectives : un réglage stocké en base (table ``settings``)
        # prime sur la configuration applicative, sans redéploiement.
        repo = SettingRepository(db)
        self.quantity_tolerance = repo.get_typed(
            "matching_quantity_tolerance", get_settings().matching_quantity_tolerance
        )
        self.price_tolerance = repo.get_typed(
            "matching_price_tolerance", get_settings().matching_price_tolerance
        )
        self.amount_tolerance = repo.get_typed(
            "matching_amount_tolerance", get_settings().matching_amount_tolerance
        )
        self.tax_tolerance = repo.get_typed(
            "matching_tax_tolerance", get_settings().matching_tax_tolerance
        )

    # --- Orchestration ----------------------------------------------------------

    def match(self, invoice: Invoice) -> MatchingResult:
        """Rapproche une facture à son bon de commande.

        Déroulé : nettoyage des anomalies de matching précédentes, détection
        des doublons, vérification du fournisseur, recherche du bon de
        commande, rapprochement des lignes (produit, quantité, prix),
        comparaison des montants et de la TVA, calcul du score global et
        persistance (score, liens BC/lignes, doublon).

        Retourne le détail du rapprochement ; le score est enregistré sur la
        facture (``matching_score``).
        """
        self._reset_matching_anomalies(invoice)
        self.db.flush()

        created: list[Anomaly] = []
        invoice_lines = self.lines.list_by_invoice(invoice.id)

        duplicate_found, _ = self._detect_duplicate(invoice, created)
        supplier_match, supplier_score = self._match_supplier(invoice, created)
        purchase_order, po_score, po_supplier_match = self._find_purchase_order(
            invoice, created
        )

        po_lines: list[PurchaseOrderLine] = []
        line_matches: list[LineMatch] = []
        if purchase_order is not None:
            po_lines = self.purchase_order_lines.list_by_purchase_order(
                purchase_order.id
            )
            if po_supplier_match:
                line_matches = self._match_lines(invoice, invoice_lines, po_lines, created)
            else:
                # Le BC appartient à un autre fournisseur : rien à rapprocher.
                line_matches = [
                    LineMatch(invoice_line=line) for line in invoice_lines
                ]

        amount_ok = self._check_amounts_and_tax(
            invoice, purchase_order, po_lines, line_matches, po_supplier_match, created
        )

        score = self._compute_score(
            supplier_score=supplier_score,
            po_score=po_score,
            line_matches=line_matches,
            po_found=purchase_order is not None,
            amount_ok=amount_ok,
        )

        self._persist_line_matches(line_matches)
        self._persist_invoice_links(invoice, purchase_order, po_supplier_match, score, duplicate_found)
        self.db.flush()

        return MatchingResult(
            invoice_id=invoice.id,
            supplier_match=supplier_match,
            duplicate_found=duplicate_found,
            purchase_order=purchase_order,
            line_matches=line_matches,
            score=score,
            anomalies=created,
        )

    # --- Fournisseur --------------------------------------------------------------

    def _match_supplier(
        self, invoice: Invoice, created: list[Anomaly]
    ) -> tuple[bool, float]:
        """Vérifie que le fournisseur extrait correspond à la facture.

        Retourne ``(correspondance, composante_de_score)``. Si aucun nom n'a
        été extrait, la vérification est neutre (composante à 1.0).
        """
        extracted_name = self._extracted_general(invoice).get("supplier_name")
        supplier = invoice.supplier
        if not extracted_name or not supplier:
            return True, 1.0
        if self._normalize(extracted_name) == self._normalize(supplier.name):
            return True, 1.0
        if self._name_similar(extracted_name, supplier.name):
            return True, 1.0

        created.append(
            self._add_anomaly(
                invoice,
                category=AnomalyCategory.SUPPLIER,
                severity=AnomalySeverity.WARNING,
                message=(
                    "Le fournisseur extrait « "
                    + extracted_name
                    + " » ne correspond pas au fournisseur de la facture « "
                    + supplier.name
                    + " »."
                ),
                expected_value=supplier.name,
                actual_value=extracted_name,
            )
        )
        return False, 0.0

    # --- Bon de commande --------------------------------------------------------------

    def _find_purchase_order(
        self, invoice: Invoice, created: list[Anomaly]
    ) -> tuple[PurchaseOrder | None, float, bool]:
        """Retrouve le bon de commande local à partir de la référence extraite.

        Retourne ``(BC, composante_de_score, fournisseur_conforme)``. Le BC
        peut être retrouvé via la référence extraite ou, à défaut, via le lien
        déjà présent sur la facture (``purchase_order_id``).
        """
        reference = self._extracted_general(invoice).get("purchase_order_reference")
        purchase_order = None
        if reference:
            purchase_order = self.purchase_orders.get_by_reference(reference.strip())
        if purchase_order is None and invoice.purchase_order_id is not None:
            purchase_order = self.purchase_orders.get(invoice.purchase_order_id)

        if purchase_order is None:
            created.append(
                self._add_anomaly(
                    invoice,
                    category=AnomalyCategory.PURCHASE_ORDER,
                    severity=AnomalySeverity.WARNING,
                    message=(
                        "Aucun bon de commande trouvé pour la référence « "
                        + (reference or "inconnue")
                        + " »."
                    ),
                    expected_value=reference,
                )
            )
            return None, 0.0, False

        if purchase_order.supplier_id != invoice.supplier_id:
            created.append(
                self._add_anomaly(
                    invoice,
                    category=AnomalyCategory.PURCHASE_ORDER,
                    severity=AnomalySeverity.WARNING,
                    message=(
                        "Le bon de commande « "
                        + purchase_order.reference
                        + " » appartient à un autre fournisseur."
                    ),
                    expected_value=str(invoice.supplier_id),
                    actual_value=str(purchase_order.supplier_id),
                )
            )
            return purchase_order, 0.0, False

        return purchase_order, 1.0, True

    # --- Doublons --------------------------------------------------------------

    def _detect_duplicate(
        self, invoice: Invoice, created: list[Anomaly]
    ) -> tuple[bool, Anomaly | None]:
        """Détecte un doublon (facture déjà enregistrée pour ce fournisseur).

        Le numéro saisi au dépôt est vérifié en premier ; si l'OCR a extrait
        un numéro différent, celui-ci est vérifié à son tour. Une facture
        identique est signalée comme doublon et la facture courante est
        marquée ``is_duplicate``.
        """
        numbers = [invoice.invoice_number]
        extracted_number = self._extracted_general(invoice).get("invoice_number")
        if extracted_number and self._normalize(extracted_number) != self._normalize(
            invoice.invoice_number
        ):
            numbers.append(extracted_number)

        for number in dict.fromkeys(numbers):
            other = self.invoices.find_other_with_supplier_number(
                invoice.id, invoice.supplier_id, number
            )
            if other is not None:
                anomaly = self._add_anomaly(
                    invoice,
                    category=AnomalyCategory.DUPLICATE,
                    severity=AnomalySeverity.CRITICAL,
                    message=(
                        "Facture déjà enregistrée pour ce fournisseur "
                        f"(numéro « {number} », facture #{other.id})."
                    ),
                    expected_value=str(other.id),
                    actual_value=str(invoice.id),
                )
                created.append(anomaly)
                return True, anomaly
        return False, None

    # --- Lignes : produit, quantité, prix -----------------------------------------------

    def _match_lines(
        self,
        invoice: Invoice,
        invoice_lines: list[InvoiceLine],
        po_lines: list[PurchaseOrderLine],
        created: list[Anomaly],
    ) -> list[LineMatch]:
        """Rapproche chaque ligne de facture avec une ligne de BC.

        La correspondance privilégie la référence produit, puis le nom
        exact, puis une correspondance approximative (difflib). Chaque ligne
        de BC n'est consommée qu'une seule fois (rapprochement 1-1). Les
        lignes sans correspondance déclenchent une anomalie « produit absent ».
        """
        by_ref: dict[str, list[PurchaseOrderLine]] = {}
        by_name: dict[str, list[PurchaseOrderLine]] = {}
        for po_line in po_lines:
            ref = self._normalize(po_line.product_ref)
            name = self._normalize(po_line.name)
            if ref:
                by_ref.setdefault(ref, []).append(po_line)
            if name:
                by_name.setdefault(name, []).append(po_line)

        used: set[int] = set()
        matches: list[LineMatch] = []

        for invoice_line in invoice_lines:
            po_line = self._match_one(invoice_line, po_lines, by_ref, by_name, used)

            if po_line is None:
                created.append(
                    self._add_anomaly(
                        invoice=invoice,
                        category=AnomalyCategory.PRODUCT_MISSING,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "Produit « "
                            + invoice_line.description
                            + (
                                f" » (réf {invoice_line.product_ref})"
                                if invoice_line.product_ref
                                else " »"
                            )
                            + " absent du bon de commande."
                        ),
                        expected_value=invoice_line.product_ref,
                    )
                )
                matches.append(LineMatch(invoice_line=invoice_line))
                continue

            used.add(po_line.id)
            quantity_delta = self._relative_delta(
                invoice_line.quantity, po_line.quantity
            )
            unit_price_delta = self._relative_delta(
                invoice_line.unit_price, po_line.unit_price
            )
            quantity_ok = self._within_tolerance(
                quantity_delta, self.quantity_tolerance
            )
            unit_price_ok = self._within_tolerance(
                unit_price_delta, self.price_tolerance
            )

            if not quantity_ok:
                created.append(
                    self._add_anomaly(
                        invoice=invoice,
                        category=AnomalyCategory.QUANTITY,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "Quantité en écart pour « "
                            + invoice_line.description
                            + " » : facturé "
                            + self._fmt(invoice_line.quantity)
                            + " vs commandé "
                            + self._fmt(po_line.quantity)
                            + f" (écart {self._fmt_delta(quantity_delta)})."
                        ),
                        expected_value=self._fmt(po_line.quantity),
                        actual_value=self._fmt(invoice_line.quantity),
                    )
                )
            if not unit_price_ok:
                created.append(
                    self._add_anomaly(
                        invoice=invoice,
                        category=AnomalyCategory.AMOUNT,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "Prix unitaire en écart pour « "
                            + invoice_line.description
                            + " » : facturé "
                            + self._fmt(invoice_line.unit_price)
                            + " vs commandé "
                            + self._fmt(po_line.unit_price)
                            + f" (écart {self._fmt_delta(unit_price_delta)})."
                        ),
                        expected_value=self._fmt(po_line.unit_price),
                        actual_value=self._fmt(invoice_line.unit_price),
                    )
                )

            matches.append(
                LineMatch(
                    invoice_line=invoice_line,
                    purchase_order_line=po_line,
                    quantity_matched=quantity_ok,
                    unit_price_matched=unit_price_ok,
                    quantity_delta=quantity_delta,
                    unit_price_delta=unit_price_delta,
                )
            )
        return matches

    def _match_one(
        self,
        invoice_line: InvoiceLine,
        po_lines: list[PurchaseOrderLine],
        by_ref: dict[str, list[PurchaseOrderLine]],
        by_name: dict[str, list[PurchaseOrderLine]],
        used: set[int],
    ) -> PurchaseOrderLine | None:
        """Cherche une ligne de BC non encore consommée pour une ligne de facture."""
        ref = self._normalize(invoice_line.product_ref)
        if ref:
            po_line = self._take_first_unused(by_ref.get(ref, []), used)
            if po_line is not None:
                return po_line

        name = self._normalize(invoice_line.description)
        if name:
            po_line = self._take_first_unused(by_name.get(name, []), used)
            if po_line is not None:
                return po_line

        return self._fuzzy_match(invoice_line, po_lines, used)

    def _fuzzy_match(
        self,
        invoice_line: InvoiceLine,
        po_lines: list[PurchaseOrderLine],
        used: set[int],
    ) -> PurchaseOrderLine | None:
        """Correspondance approximative sur le nom/la description (difflib)."""
        target = self._normalize(invoice_line.description)
        if not target:
            return None
        best: tuple[float, PurchaseOrderLine] | None = None
        for po_line in po_lines:
            if po_line.id in used:
                continue
            candidate = self._normalize(po_line.name)
            if not candidate:
                continue
            ratio = SequenceMatcher(None, target, candidate).ratio()
            if ratio >= _NAME_MATCH_THRESHOLD and (
                best is None or ratio > best[0]
            ):
                best = (ratio, po_line)
        return best[1] if best else None

    @staticmethod
    def _take_first_unused(
        candidates: list[PurchaseOrderLine], used: set[int]
    ) -> PurchaseOrderLine | None:
        """Retourne la première ligne de BC de ``candidates`` non consommée."""
        for po_line in candidates:
            if po_line.id not in used:
                return po_line
        return None

    # --- Montants & TVA --------------------------------------------------------------

    def _check_amounts_and_tax(
        self,
        invoice: Invoice,
        purchase_order: PurchaseOrder | None,
        po_lines: list[PurchaseOrderLine],
        line_matches: list[LineMatch],
        po_supplier_match: bool,
        created: list[Anomaly],
    ) -> bool:
        """Compare les montants (HT, TTC) et la TVA avec le bon de commande.

        Retourne ``True`` si aucun écart de montant ou de TVA n'a été détecté.
        La comparaison des totaux n'est faite que si le BC est conforme au
        fournisseur de la facture.
        """
        if purchase_order is None or not po_supplier_match:
            return False

        amount_ok = True
        all_matched = bool(line_matches) and all(m.matched for m in line_matches)

        # Total HT facturé vs total des lignes de BC rapprochées.
        if all_matched and invoice.total_excl_tax is not None:
            expected = sum(
                (
                    m.purchase_order_line.amount
                    for m in line_matches
                    if m.purchase_order_line is not None
                    and m.purchase_order_line.amount is not None
                ),
                Decimal("0"),
            )
            if expected:
                delta = self._relative_delta(invoice.total_excl_tax, expected)
                if not self._within_tolerance(delta, self.amount_tolerance):
                    amount_ok = False
                    created.append(
                        self._add_anomaly(
                            invoice,
                            category=AnomalyCategory.AMOUNT,
                            severity=AnomalySeverity.WARNING,
                            message=(
                                "Total HT facturé "
                                + self._fmt(invoice.total_excl_tax)
                                + " vs commandé "
                                + self._fmt(expected)
                                + f" (écart {self._fmt_delta(delta)})."
                            ),
                            expected_value=self._fmt(expected),
                            actual_value=self._fmt(invoice.total_excl_tax),
                        )
                    )

        # Total TTC facturé vs total du bon de commande.
        if purchase_order.total_amount is not None and invoice.total_incl_tax is not None:
            delta = self._relative_delta(invoice.total_incl_tax, purchase_order.total_amount)
            if not self._within_tolerance(delta, self.amount_tolerance):
                amount_ok = False
                created.append(
                    self._add_anomaly(
                        invoice,
                        category=AnomalyCategory.AMOUNT,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "Total TTC facturé "
                            + self._fmt(invoice.total_incl_tax)
                            + " vs bon de commande "
                            + self._fmt(purchase_order.total_amount)
                            + f" (écart {self._fmt_delta(delta)})."
                        ),
                        expected_value=self._fmt(purchase_order.total_amount),
                        actual_value=self._fmt(invoice.total_incl_tax),
                    )
                )

        # TVA : taxe déduite du BC (total TTC − total HT des lignes) vs TVA facturée.
        if purchase_order.total_amount is not None:
            po_excl = sum(
                (po_line.amount for po_line in po_lines if po_line.amount is not None),
                Decimal("0"),
            )
            po_tax = purchase_order.total_amount - po_excl
        else:
            po_tax = None
        if po_tax is not None and invoice.tax_amount is not None:
            delta = self._relative_delta(invoice.tax_amount, po_tax)
            if not self._within_tolerance(delta, self.tax_tolerance):
                amount_ok = False
                created.append(
                    self._add_anomaly(
                        invoice,
                        category=AnomalyCategory.TAX,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "TVA facturée "
                            + self._fmt(invoice.tax_amount)
                            + " vs TVA déduite du bon de commande "
                            + self._fmt(po_tax)
                            + f" (écart {self._fmt_delta(delta)})."
                        ),
                        expected_value=self._fmt(po_tax),
                        actual_value=self._fmt(invoice.tax_amount),
                    )
                )

        # Cohérence interne de la facture : TVA = TTC − HT.
        if (
            invoice.total_incl_tax is not None
            and invoice.total_excl_tax is not None
            and invoice.tax_amount is not None
        ):
            implied = invoice.total_incl_tax - invoice.total_excl_tax
            delta = self._relative_delta(invoice.tax_amount, implied)
            if not self._within_tolerance(delta, self.tax_tolerance):
                amount_ok = False
                created.append(
                    self._add_anomaly(
                        invoice,
                        category=AnomalyCategory.TAX,
                        severity=AnomalySeverity.WARNING,
                        message=(
                            "TVA incohérente sur la facture : "
                            + self._fmt(invoice.tax_amount)
                            + " facturée vs "
                            + self._fmt(implied)
                            + " attendue (TTC − HT)."
                        ),
                        expected_value=self._fmt(implied),
                        actual_value=self._fmt(invoice.tax_amount),
                    )
                )
        return amount_ok

    # --- Score global --------------------------------------------------------------

    def _compute_score(
        self,
        *,
        supplier_score: float,
        po_score: float,
        line_matches: list[LineMatch],
        po_found: bool,
        amount_ok: bool,
    ) -> float:
        """Calcule le score de matching global (moyenne pondérée, 0..1).

        Sans bon de commande, les composantes produits/quantités/prix/montants
        sont nulles : la facture ne peut pas être rapprochée.
        """
        if not po_found:
            product_score = quantity_score = price_score = amount_score = 0.0
        else:
            total = len(line_matches)
            product_score = (
                (sum(1 for m in line_matches if m.matched) / total) if total else 1.0
            )
            matched = [m for m in line_matches if m.matched]
            if matched:
                quantity_score = (
                    sum(1 for m in matched if m.quantity_matched) / len(matched)
                )
                price_score = (
                    sum(1 for m in matched if m.unit_price_matched) / len(matched)
                )
            else:
                quantity_score = price_score = 0.0
            amount_score = 1.0 if amount_ok else 0.0

        components = {
            "supplier": supplier_score,
            "purchase_order": po_score,
            "product": product_score,
            "quantity": quantity_score,
            "price": price_score,
            "amount": amount_score,
        }
        score = sum(_SCORE_WEIGHTS[key] * components[key] for key in _SCORE_WEIGHTS)
        return round(score, 4)

    # --- Persistance --------------------------------------------------------------

    def _persist_line_matches(self, line_matches: list[LineMatch]) -> None:
        """Lie chaque ligne de facture à sa ligne de BC (``odoo_id`` Odoo)."""
        for match in line_matches:
            odoo_id = (
                match.purchase_order_line.odoo_id
                if match.purchase_order_line is not None
                else None
            )
            self.lines.update(match.invoice_line, purchase_order_line_odoo_id=odoo_id)

    def _persist_invoice_links(
        self,
        invoice: Invoice,
        purchase_order: PurchaseOrder | None,
        po_supplier_match: bool,
        score: float,
        duplicate_found: bool,
    ) -> None:
        """Persiste score, doublon et éventuel lien vers le bon de commande."""
        updates: dict = {
            "matching_score": score,
            "is_duplicate": duplicate_found,
        }
        if purchase_order is not None and po_supplier_match:
            updates["purchase_order_id"] = purchase_order.id
        self.invoices.update(invoice, **updates)

    def _reset_matching_anomalies(self, invoice: Invoice) -> None:
        """Supprime les anomalies de matching du passage précédent (idempotence)."""
        for anomaly in self.anomalies.list_by_invoice(invoice.id):
            if anomaly.category in _MATCHING_CATEGORIES:
                self.anomalies.delete(anomaly)

    # --- Helpers ------------------------------------------------------------------

    def _add_anomaly(
        self,
        invoice: Invoice,
        *,
        category: AnomalyCategory,
        severity: AnomalySeverity,
        message: str,
        expected_value: str | None = None,
        actual_value: str | None = None,
    ) -> Anomaly:
        """Crée et enregistre une anomalie liée à la facture."""
        return self.anomalies.create(
            invoice_id=invoice.id,
            category=category,
            severity=severity,
            message=message,
            expected_value=expected_value,
            actual_value=actual_value,
        )

    @staticmethod
    def _extracted_general(invoice: Invoice) -> dict:
        """Champs généraux extraits par l'OCR (dict vide si absents)."""
        data = invoice.extracted_data or {}
        general = data.get("general")
        return general if isinstance(general, dict) else {}

    @staticmethod
    def _normalize(value: str | None) -> str:
        """Normalise un texte : minuscules, espaces réduits."""
        return " ".join((value or "").strip().lower().split())

    @staticmethod
    def _name_similar(left: str, right: str) -> bool:
        """Indique si deux textes sont proches (correspondance approximative)."""
        return (
            SequenceMatcher(None, MatchingService._normalize(left), MatchingService._normalize(right)).ratio()
            >= _NAME_MATCH_THRESHOLD
        )

    @staticmethod
    def _relative_delta(
        left: Decimal | None, right: Decimal | None
    ) -> float | None:
        """Écart relatif entre deux valeurs (``None`` si non comparable).

        Ex. ``_relative_delta(Decimal("12"), Decimal("10")) == 0.1666...``.
        """
        if left is None or right is None:
            return None
        try:
            left = Decimal(str(left))
            right = Decimal(str(right))
        except (InvalidOperation, ValueError, TypeError):
            return None
        denominator = max(abs(left), abs(right))
        if denominator == 0:
            return 0.0
        return float(abs(left - right) / denominator)

    @staticmethod
    def _within_tolerance(relative: float | None, tolerance: float) -> bool:
        """Indique si un écart relatif reste sous la tolérance acceptée."""
        return relative is None or relative <= tolerance

    @staticmethod
    def _fmt(value) -> str:
        """Formate une valeur lisible pour les messages d'anomalie."""
        if value is None:
            return "—"
        try:
            return f"{Decimal(str(value)):f}"
        except (InvalidOperation, ValueError, TypeError):
            return str(value)

    @staticmethod
    def _fmt_delta(relative: float | None) -> str:
        """Formate un écart relatif en pourcentage (``None`` → « — »)."""
        if relative is None:
            return "—"
        return f"{relative:.1%}"
