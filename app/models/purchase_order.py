"""Modèle « référence Bon de Commande » : cache local du ``purchase.order`` Odoo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice
    from app.models.supplier import Supplier


class PurchaseOrder(Base, TimestampMixin):
    """Bon de commande fournisseur, miroir local de ``purchase.order`` Odoo.

    ``reference`` est la référence du BC (ex. « PO000123 ») et doit être
    unique : un même BC Odoo ne doit être mis en cache qu'une seule fois.
    """

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    odoo_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    reference: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[str | None] = mapped_column(
        String(32)
    )  # état Odoo : draft, sent, purchase, done, cancel...
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )
    date_order: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    supplier: Mapped[Supplier] = relationship(back_populates="purchase_orders")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="purchase_order")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<PurchaseOrder id={self.id} reference={self.reference!r}>"
