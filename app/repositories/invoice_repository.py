"""Repository de l'entité ``Invoice`` (facture).

Point d'accès principal au suivi des factures : CRUD, détection des doublons
(couple fournisseur + numéro) et filtres métier (statut, fournisseur, date).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.repositories.base import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    """Accès aux données des factures."""

    model = Invoice

    def create(
        self,
        *,
        invoice_number: str,
        supplier_id: int,
        status: InvoiceStatus = InvoiceStatus.SUBMITTED,
        purchase_order_id: int | None = None,
        issue_date: date | None = None,
        due_date: date | None = None,
        currency: str = "EUR",
        total_excl_tax: str | None = None,
        tax_amount: str | None = None,
        total_incl_tax: str | None = None,
        discount: str | None = None,
        shipping_fees: str | None = None,
        ocr_confidence_score: float | None = None,
        matching_score: float | None = None,
        vendor_bill_id: int | None = None,
        file_path: str | None = None,
        extracted_data: dict | None = None,
        rejection_reason: str | None = None,
        error_message: str | None = None,
    ) -> Invoice:
        """Crée une facture. Le statut par défaut est « Déposée »."""
        return self.add(
            Invoice(
                invoice_number=invoice_number,
                supplier_id=supplier_id,
                status=status,
                purchase_order_id=purchase_order_id,
                issue_date=issue_date,
                due_date=due_date,
                currency=currency,
                total_excl_tax=total_excl_tax,
                tax_amount=tax_amount,
                total_incl_tax=total_incl_tax,
                discount=discount,
                shipping_fees=shipping_fees,
                ocr_confidence_score=ocr_confidence_score,
                matching_score=matching_score,
                vendor_bill_id=vendor_bill_id,
                file_path=file_path,
                extracted_data=extracted_data,
                rejection_reason=rejection_reason,
                error_message=error_message,
            )
        )

    # --- Détection de doublons -------------------------------------------------

    def get_by_supplier_and_number(
        self, supplier_id: int, invoice_number: str
    ) -> Invoice | None:
        """Retourne la facture (fournisseur, numéro) ou ``None``.

        Utile pour la détection de doublon lors du dépôt d'une facture.
        """
        stmt = select(Invoice).where(
            Invoice.supplier_id == supplier_id,
            Invoice.invoice_number == invoice_number,
        )
        return self.session.scalars(stmt).first()

    def exists_duplicate(self, supplier_id: int, invoice_number: str) -> bool:
        """Indique si une facture identique (fournisseur, numéro) existe déjà."""
        return self.get_by_supplier_and_number(supplier_id, invoice_number) is not None

    # --- Filtres ---------------------------------------------------------------

    def filter(
        self,
        *,
        status: InvoiceStatus | None = None,
        supplier_id: int | None = None,
        issue_date_from: date | None = None,
        issue_date_to: date | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Invoice]:
        """Filtre les factures selon les critères fournis (tous facultatifs).

        Les critères peuvent être combinés (statut ET fournisseur ET période).
        La pagination est contrôlée par ``limit`` / ``offset``.
        """
        stmt = select(Invoice)
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        if supplier_id is not None:
            stmt = stmt.where(Invoice.supplier_id == supplier_id)
        if issue_date_from is not None:
            stmt = stmt.where(Invoice.issue_date >= issue_date_from)
        if issue_date_to is not None:
            stmt = stmt.where(Invoice.issue_date <= issue_date_to)
        if created_from is not None:
            stmt = stmt.where(Invoice.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(Invoice.created_at <= created_to)
        stmt = (
            stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        status: InvoiceStatus | None = None,
        supplier_id: int | None = None,
        issue_date_from: date | None = None,
        issue_date_to: date | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        """Compte les factures correspondant aux mêmes critères que ``filter``."""
        stmt = select(func.count(Invoice.id))
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        if supplier_id is not None:
            stmt = stmt.where(Invoice.supplier_id == supplier_id)
        if issue_date_from is not None:
            stmt = stmt.where(Invoice.issue_date >= issue_date_from)
        if issue_date_to is not None:
            stmt = stmt.where(Invoice.issue_date <= issue_date_to)
        if created_from is not None:
            stmt = stmt.where(Invoice.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(Invoice.created_at <= created_to)
        return int(self.session.scalar(stmt) or 0)

    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]:
        """Retourne les factures d'un statut donné."""
        return self.filter(status=status)

    def list_by_supplier(self, supplier_id: int) -> list[Invoice]:
        """Retourne les factures d'un fournisseur donné."""
        return self.filter(supplier_id=supplier_id)

    def list_by_date_range(self, start: date, end: date) -> list[Invoice]:
        """Retourne les factures émises entre ``start`` et ``end`` (inclus)."""
        return self.filter(issue_date_from=start, issue_date_to=end)
