"""Modèle « ligne de facture »."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice


class InvoiceLine(Base, TimestampMixin):
    """Ligne d'une facture (issue de l'OCR ou corrigée manuellement).

    ``line_number`` positionne la ligne dans la facture ; le couple
    (invoice_id, line_number) est unique.
    """

    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id", "line_number", name="uq_invoice_lines_invoice_line"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    product_ref: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(32))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchase_order_line_odoo_id: Mapped[int | None] = mapped_column(
        BigInteger
    )  # id de purchase.order.line Odoo (matching, phase 6)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<InvoiceLine id={self.id} line={self.line_number} desc={self.description!r}>"
