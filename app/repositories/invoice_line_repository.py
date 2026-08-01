"""Repository de l'entité ``InvoiceLine`` (ligne de facture)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.invoice_line import InvoiceLine
from app.repositories.base import BaseRepository


class InvoiceLineRepository(BaseRepository[InvoiceLine]):
    """Accès aux données des lignes de facture."""

    model = InvoiceLine

    def create(
        self,
        *,
        invoice_id: int,
        line_number: int,
        description: str,
        product_ref: str | None = None,
        quantity: Decimal | None = None,
        unit: str | None = None,
        unit_price: Decimal | None = None,
        tax_rate: Decimal | None = None,
        discount: Decimal | None = None,
        amount: Decimal | None = None,
        purchase_order_line_odoo_id: int | None = None,
    ) -> InvoiceLine:
        """Crée une ligne de facture."""
        return self.add(
            InvoiceLine(
                invoice_id=invoice_id,
                line_number=line_number,
                description=description,
                product_ref=product_ref,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                tax_rate=tax_rate,
                discount=discount,
                amount=amount,
                purchase_order_line_odoo_id=purchase_order_line_odoo_id,
            )
        )

    def list_by_invoice(self, invoice_id: int) -> list[InvoiceLine]:
        """Retourne les lignes d'une facture, triées par position."""
        stmt = (
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.line_number)
        )
        return list(self.session.scalars(stmt))
