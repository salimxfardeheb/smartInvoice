"""Service de validation comptable des factures (phase 7).

Ce service orchestre les actions décisionnelles du comptable sur une facture
arrivée « À vérifier » (après OCR et matching) :

- :meth:`ValidationService.validate` : valide la facture ;
- :meth:`ValidationService.reject` : rejette la facture avec un motif
  obligatoire ;
- :meth:`ValidationService.correct` : applique une correction manuelle des
  données extraites (champs facture et lignes) ;
- :meth:`ValidationService.create_vendor_bill` : génère la Vendor Bill Odoo
  (``account.move``) depuis la facture validée et lie le ``move_id`` créé.

Chaque action est tracée dans le journal d'audit (:class:`AuditLog`) : qui a
agi, quand, quoi et le détail structuré des changements.

Les transitions de statut réutilisent le graphe défini par
:data:`app.services.invoice_service.VALID_TRANSITIONS`.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.exceptions import (
    DuplicateInvoiceError,
    InvalidStatusTransitionError,
    OdooError,
    RejectionReasonRequiredError,
)
from app.models.enums import AuditAction, InvoiceStatus
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.odoo import OdooClient
from app.repositories import (
    AuditLogRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from app.schemas.validation import InvoiceCorrection, InvoiceLineCorrection
from app.services.invoice_service import VALID_TRANSITIONS

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.user import User

# Champs scalaires corrigibles d'une facture (attribut du schéma → colonne du modèle).
_INVOICE_SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("issue_date", "issue_date"),
    ("due_date", "due_date"),
    ("currency", "currency"),
    ("total_excl_tax", "total_excl_tax"),
    ("tax_amount", "tax_amount"),
    ("total_incl_tax", "total_incl_tax"),
    ("discount", "discount"),
    ("shipping_fees", "shipping_fees"),
)

# Champs corrigibles d'une ligne de facture (attribut du schéma → colonne du modèle).
_LINE_SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("product_ref", "product_ref"),
    ("quantity", "quantity"),
    ("unit", "unit"),
    ("unit_price", "unit_price"),
    ("tax_rate", "tax_rate"),
    ("discount", "discount"),
    ("amount", "amount"),
)

logger = logging.getLogger(__name__)


class ValidationService:
    """Actions de validation / rejet / correction et création de la Vendor Bill."""

    def __init__(self, db: Session, *, odoo_client: OdooClient | None = None) -> None:
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.lines = InvoiceLineRepository(db)
        self.audit = AuditLogRepository(db)
        self.odoo_client = odoo_client or OdooClient()

    # --- Validation ----------------------------------------------------------------

    def validate(self, invoice: Invoice, user: User) -> Invoice:
        """Valide une facture (« À vérifier » → « Validée ») et trace l'action."""
        self._transition(invoice, InvoiceStatus.VALIDATED)
        self.audit.create(
            invoice_id=invoice.id,
            user_id=user.id,
            action=AuditAction.VALIDATED,
            message="Facture validée par le comptable.",
        )
        self.db.flush()
        logger.info("Validation : facture %s validée par %s.", invoice.id, user.id)
        return invoice

    # --- Rejet ---------------------------------------------------------------------

    def reject(self, invoice: Invoice, user: User, reason: str) -> Invoice:
        """Rejette une facture avec un motif obligatoire et trace l'action.

        Lève :class:`RejectionReasonRequiredError` si le motif est vide.
        """
        if not reason or not reason.strip():
            raise RejectionReasonRequiredError(
                "Le motif de rejet est obligatoire."
            )
        reason = reason.strip()
        self._transition(invoice, InvoiceStatus.REJECTED, reason=reason)
        self.audit.create(
            invoice_id=invoice.id,
            user_id=user.id,
            action=AuditAction.REJECTED,
            message=f"Facture rejetée : {reason}",
        )
        self.db.flush()
        logger.info(
            "Validation : facture %s rejetée par %s (motif : %s).",
            invoice.id,
            user.id,
            reason,
        )
        return invoice

    # --- Correction ---------------------------------------------------------------

    def correct(
        self, invoice: Invoice, user: User, correction: InvoiceCorrection
    ) -> Invoice:
        """Applique une correction manuelle des données extraites et trace l'action.

        Seuls les champs fournis sont modifiés ; si ``lines`` est fourni, les
        lignes de la facture sont resynchronisées (mise à jour, création,
        suppression). Le détail des changements est consigné dans l'audit.
        """
        self._require_status(invoice, InvoiceStatus.TO_REVIEW)

        changes: dict[str, object] = {}

        if (
            correction.invoice_number is not None
            and correction.invoice_number != invoice.invoice_number
        ):
            if self.invoices.exists_duplicate(
                invoice.supplier_id, correction.invoice_number
            ):
                raise DuplicateInvoiceError(
                    "Une facture portant ce numéro existe déjà pour ce fournisseur."
                )
            changes["invoice_number"] = {
                "before": invoice.invoice_number,
                "after": correction.invoice_number,
            }
            self.invoices.update(invoice, invoice_number=correction.invoice_number)

        updates: dict = {}
        for attr, column in _INVOICE_SCALAR_FIELDS:
            value = getattr(correction, attr)
            if value is not None and value != getattr(invoice, column):
                changes[attr] = {
                    "before": self._serialize(getattr(invoice, column)),
                    "after": self._serialize(value),
                }
                updates[column] = value
        if updates:
            self.invoices.update(invoice, **updates)

        if correction.lines is not None:
            line_changes = self._apply_line_corrections(invoice, correction.lines)
            if line_changes:
                changes["lines"] = line_changes

        if changes:
            self.audit.create(
                invoice_id=invoice.id,
                user_id=user.id,
                action=AuditAction.CORRECTED,
                message="Correction manuelle appliquée.",
                details=changes,
            )
        self.db.flush()
        return invoice

    def _apply_line_corrections(
        self, invoice: Invoice, corrections: list[InvoiceLineCorrection]
    ) -> list[dict]:
        """Resynchronise les lignes d'une facture à partir de la correction.

        Retourne la liste des lignes modifiées (description + statut).
        """
        existing = {
            line.line_number: line
            for line in self.lines.list_by_invoice(invoice.id)
        }
        provided: set[int] = set()
        summary: list[dict] = []

        for item in corrections:
            provided.add(item.line_number)
            line = existing.get(item.line_number)
            if line is None:
                self.lines.create(invoice_id=invoice.id, **self._line_values(item))
                summary.append({"line_number": item.line_number, "status": "créée"})
                continue

            updates: dict = {}
            for attr, column in _LINE_SCALAR_FIELDS:
                value = getattr(item, attr)
                if value is not None and value != getattr(line, column):
                    updates[column] = value
            if item.description != line.description:
                updates["description"] = item.description
            if updates:
                self.lines.update(line, **updates)
                summary.append(
                    {
                        "line_number": item.line_number,
                        "status": "modifiée",
                        "fields": sorted(updates),
                    }
                )

        for line_number, line in existing.items():
            if line_number not in provided:
                self.lines.delete(line)
                summary.append({"line_number": line_number, "status": "supprimée"})

        return summary

    # --- Vendor Bill (Odoo) --------------------------------------------------------

    def create_vendor_bill(self, invoice: Invoice, user: User) -> Invoice:
        """Crée la Vendor Bill Odoo (``account.move``) de la facture validée.

        Construit l'``account.move`` (type ``in_invoice``) à partir de la
        facture et de ses lignes, puis lie le ``move_id`` créé à la facture
        et la fait passer « Vendor Bill créée ».

        Robustesse (retry et réconciliation de doublons) :
        - si une Vendor Bill est déjà liée à la facture, l'appel est
          idempotent (rien n'est recréé dans Odoo) ;
        - si la création échoue mais qu'une ``account.move`` portant la même
          référence existe déjà côté Odoo (création antérieure dont la
          réponse a été perdue), elle est réconciliée avec la facture ;
        - sinon, le compteur de tentatives (``vendor_bill_attempts``) est
          incrémenté et le dernier message d'erreur
          (``vendor_bill_error``) est conservé pour diagnostiquer la
          relance, puis l'erreur remonte (statut inchangé).
        """
        # Idempotence : la Vendor Bill est déjà liée → simple réconciliation.
        if invoice.vendor_bill_id is not None:
            self._log_reconciled(invoice, user, invoice.vendor_bill_id)
            return invoice

        self._require_status(invoice, InvoiceStatus.VALIDATED)

        values = self._build_move_values(invoice)
        logger.info(
            "Odoo : création de la Vendor Bill pour la facture %s (%s).",
            invoice.id,
            invoice.invoice_number,
        )
        try:
            move_id = int(self.odoo_client.create("account.move", values))
        except OdooError as exc:
            logger.error(
                "Odoo : création de la Vendor Bill en échec pour la facture %s "
                "(tentative %s) : %s",
                invoice.id,
                (invoice.vendor_bill_attempts or 0) + 1,
                exc,
                exc_info=True,
            )
            existing_id = self._find_existing_vendor_bill(invoice)
            if existing_id is not None:
                self.invoices.update(
                    invoice,
                    vendor_bill_id=existing_id,
                    vendor_bill_attempts=0,
                    vendor_bill_error=None,
                )
                logger.warning(
                    "Odoo : Vendor Bill %s déjà présente, facture %s réconciliée.",
                    existing_id,
                    invoice.id,
                )
                self._log_reconciled(invoice, user, existing_id)
                self.db.flush()
                return invoice
            self.invoices.update(
                invoice,
                vendor_bill_attempts=(invoice.vendor_bill_attempts or 0) + 1,
                vendor_bill_error=str(exc),
            )
            raise

        self.invoices.update(
            invoice,
            vendor_bill_id=int(move_id),
            vendor_bill_attempts=0,
            vendor_bill_error=None,
        )
        self._transition(invoice, InvoiceStatus.VENDOR_BILL_CREATED)
        self.audit.create(
            invoice_id=invoice.id,
            user_id=user.id,
            action=AuditAction.VENDOR_BILL_CREATED,
            message=f"Vendor Bill créée dans Odoo (account.move #{move_id}).",
            details={"move_id": int(move_id)},
        )
        self.db.flush()
        logger.info(
            "Odoo : Vendor Bill %s créée pour la facture %s.", move_id, invoice.id
        )
        return invoice

    def _find_existing_vendor_bill(self, invoice: Invoice) -> int | None:
        """Recherche côté Odoo une ``account.move`` portant la référence facture."""
        rows = self.odoo_client.search_read(
            "account.move",
            [["ref", "=", invoice.invoice_number]],
            ["id", "ref"],
            limit=1,
        )
        if not rows:
            return None
        return int(rows[0]["id"])

    def _log_reconciled(self, invoice: Invoice, user: User, move_id: int) -> None:
        """Trace une réconciliation : une Vendor Bill existante est rattachée."""
        self.audit.create(
            invoice_id=invoice.id,
            user_id=user.id,
            action=AuditAction.VENDOR_BILL_CREATED,
            message=(
                f"Vendor Bill déjà présente dans Odoo (account.move #{move_id}) : "
                "facture réconciliée."
            ),
            details={"move_id": int(move_id), "reconciled": True},
        )
        self.db.flush()

    def _build_move_values(self, invoice: Invoice) -> dict:
        """Construit les valeurs de l'``account.move`` (Vendor Bill) depuis la facture."""
        values: dict = {
            "move_type": "in_invoice",
            "partner_id": invoice.supplier.odoo_id,
            "ref": invoice.invoice_number,
            "invoice_date": (
                invoice.issue_date.isoformat()
                if invoice.issue_date is not None
                else date.today().isoformat()
            ),
        }
        if invoice.due_date is not None:
            values["invoice_date_due"] = invoice.due_date.isoformat()
        values["invoice_line_ids"] = [
            (0, 0, self._build_line_values(line))
            for line in self.lines.list_by_invoice(invoice.id)
        ]
        return values

    def _build_line_values(self, line: InvoiceLine) -> dict:
        """Construit les valeurs d'une ligne de l'``account.move.line``."""
        values: dict = {
            "name": line.description,
            "quantity": self._to_float(line.quantity, default=1.0),
            "price_unit": self._to_float(line.unit_price, default=0.0),
        }
        if line.discount is not None:
            values["discount"] = self._to_float(line.discount, default=0.0)
        return values

    # --- Helpers ------------------------------------------------------------------

    def _transition(
        self, invoice: Invoice, new_status: InvoiceStatus, *, reason: str | None = None
    ) -> None:
        """Applique une transition de statut si elle est valide (409 sinon)."""
        allowed = VALID_TRANSITIONS.get(invoice.status, set())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Transition invalide : « {invoice.status.value} » → "
                f"« {new_status.value} »."
            )
        updates: dict = {"status": new_status}
        if new_status is InvoiceStatus.REJECTED:
            updates["rejection_reason"] = reason
        self.invoices.update(invoice, **updates)

    def _require_status(self, invoice: Invoice, status: InvoiceStatus) -> None:
        """Exige que la facture soit exactement dans l'état ``status``."""
        if invoice.status is not status:
            raise InvalidStatusTransitionError(
                f"L'action requiert la facture à l'état « {status.value} » "
                f"(état actuel : « {invoice.status.value} »)."
            )

    @staticmethod
    def _line_values(item: InvoiceLineCorrection) -> dict:
        """Valeurs persistées d'une nouvelle ligne de facture."""
        return {
            "line_number": item.line_number,
            "description": item.description,
            "product_ref": item.product_ref,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "tax_rate": item.tax_rate,
            "discount": item.discount,
            "amount": item.amount,
        }

    @staticmethod
    def _serialize(value) -> str | None:
        """Sérialise une valeur pour le journal d'audit (JSON-safe)."""
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return f"{value}"
        return str(value)

    @staticmethod
    def _to_float(value, *, default: float) -> float:
        """Convertit une valeur en ``float`` (``default`` si illisible)."""
        if value is None:
            return default
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError):
            return default
