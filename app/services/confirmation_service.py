"""Service de confirmation acheteur (phase 7 - contrôle par l'acheteur).

Après le rapprochement, l'acheteur vérifie et confirme les quantités et les
produits facturés (permission ``INVOICE_CONFIRM``). La confirmation peut :

- corriger les valeurs extraites d'une ligne de facture (quantité, prix
  unitaire, référence produit) ;
- considérer comme vérifiées les lignes confirmées pour lesquelles aucune
  correction n'est fournie ;
- résoudre les anomalies de matching liées (quantité, produit absent,
  montant) étant validées par l'acheteur ;
- tracer l'action dans le journal d'audit (``AuditAction.CONFIRMED``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.enums import (
    AnomalyCategory,
    AuditAction,
)
from app.repositories import (
    AnomalyRepository,
    AuditLogRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from app.schemas.validation import InvoiceConfirm

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice
    from app.models.user import User

# Ces catégories d'anomalies portent sur des quantités/produits/prix :
# leur résolution relève de la confirmation de l'acheteur.
_CONFIRMABLE_CATEGORIES = frozenset(
    {
        AnomalyCategory.QUANTITY,
        AnomalyCategory.PRODUCT_MISSING,
        AnomalyCategory.AMOUNT,
    }
)


class BuyerConfirmationService:
    """Confirmation des quantités/produits d'une facture par l'acheteur."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.lines = InvoiceLineRepository(db)
        self.anomalies = AnomalyRepository(db)
        self.audit = AuditLogRepository(db)

    def confirm(self, invoice: Invoice, user: User, payload: InvoiceConfirm) -> Invoice:
        """Applique la confirmation de l'acheteur et trace l'action.

        Les valeurs fournies (quantité, prix, référence) écrasent celles des
        lignes correspondantes. Les anomalies confirmables encore ouvertes de
        la facture sont marquées résolues.
        """
        confirmed_lines: list[dict] = []

        if payload.lines:
            lines = {line.line_number: line for line in self.lines.list_by_invoice(invoice.id)}
            for item in payload.lines:
                line = lines.get(item.line_number)
                if line is None:
                    continue
                updates: dict = {}
                if item.quantity is not None:
                    updates["quantity"] = item.quantity
                if item.unit_price is not None:
                    updates["unit_price"] = item.unit_price
                if item.product_ref is not None:
                    updates["product_ref"] = item.product_ref
                if updates:
                    self.lines.update(line, **updates)
                confirmed_lines.append(
                    {
                        "line_number": item.line_number,
                        "confirmed": item.confirmed,
                        "updated_fields": sorted(updates),
                    }
                )

        resolved = self._resolve_confirmable_anomalies(invoice)

        self.audit.create(
            invoice_id=invoice.id,
            user_id=user.id,
            action=AuditAction.CONFIRMED,
            message="Quantités et produits confirmés par l'acheteur.",
            details={
                "lines": confirmed_lines,
                "anomalies_resolved": resolved,
            },
        )
        self.db.flush()
        return invoice

    def _resolve_confirmable_anomalies(self, invoice: Invoice) -> list[int]:
        """Résout les anomalies confirmables (quantité/produit/prix) de la facture."""
        resolved: list[int] = []
        for anomaly in self.anomalies.list_by_invoice(invoice.id):
            if anomaly.resolved or anomaly.category not in _CONFIRMABLE_CATEGORIES:
                continue
            self.anomalies.resolve(anomaly)
            resolved.append(anomaly.id)
        return resolved