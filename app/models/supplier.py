"""Modèle « référence fournisseur » : cache local du ``res.partner`` Odoo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder


class Supplier(Base, TimestampMixin):
    """Fournisseur, miroir local de l'entité ``res.partner`` d'Odoo.

    La colonne ``odoo_id`` permet de retrouver de manière fiable le partenaire
    Odoo d'origine lors du rapprochement (phase 5).
    """

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    odoo_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    vat: Mapped[str | None] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="supplier", passive_deletes=True
    )
    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        back_populates="supplier", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<Supplier id={self.id} name={self.name!r} odoo_id={self.odoo_id}>"
