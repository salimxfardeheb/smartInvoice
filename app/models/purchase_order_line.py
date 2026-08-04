"""Modèle « ligne de Bon de Commande » : cache local du ``purchase.order.line`` Odoo."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.purchase_order import PurchaseOrder


class PurchaseOrderLine(Base, TimestampMixin):
    """Ligne d'un bon de commande, miroir local de ``purchase.order.line`` Odoo.

    ``odoo_id`` est l'identifiant unique de la ligne dans Odoo. ``line_number``
    positionne la ligne dans le BC (dérivé de la séquence Odoo). Ces lignes
    servent de référence lors du matching avec les lignes de facture
    (``invoice_lines.purchase_order_line_odoo_id``, phase 6).
    """

    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id", "odoo_id", name="uq_purchase_order_lines_po_odoo"
        ),
        Index("ix_purchase_order_lines_purchase_order_id", "purchase_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    odoo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_ref: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(32))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Taux de TVA lu depuis Odoo (account.tax) pour un rapprochement fiable.
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<PurchaseOrderLine id={self.id} odoo_id={self.odoo_id} "
            f"line={self.line_number} name={self.name!r}>"
        )
