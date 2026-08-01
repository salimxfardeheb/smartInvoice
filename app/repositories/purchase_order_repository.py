"""Repository de l'entité ``PurchaseOrder`` (cache local du purchase.order Odoo)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.purchase_order import PurchaseOrder
from app.repositories.base import BaseRepository


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    """Accès aux données des bons de commande."""

    model = PurchaseOrder

    def create(
        self,
        *,
        odoo_id: int,
        reference: str,
        supplier_id: int,
        state: str | None = None,
        currency: str = "EUR",
        date_order: date | None = None,
        total_amount: Decimal | None = None,
    ) -> PurchaseOrder:
        """Crée un bon de commande dans le cache local."""
        return self.add(
            PurchaseOrder(
                odoo_id=odoo_id,
                reference=reference,
                supplier_id=supplier_id,
                state=state,
                currency=currency,
                date_order=date_order,
                total_amount=total_amount,
            )
        )

    def get_by_reference(self, reference: str) -> PurchaseOrder | None:
        """Retourne le bon de commande correspondant à sa référence."""
        stmt = select(PurchaseOrder).where(PurchaseOrder.reference == reference)
        return self.session.scalars(stmt).first()

    def get_by_odoo_id(self, odoo_id: int) -> PurchaseOrder | None:
        """Retourne le bon de commande correspondant au ``purchase.order`` Odoo."""
        stmt = select(PurchaseOrder).where(PurchaseOrder.odoo_id == odoo_id)
        return self.session.scalars(stmt).first()

    def list_by_supplier(self, supplier_id: int) -> list[PurchaseOrder]:
        """Retourne les bons de commande d'un fournisseur."""
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.supplier_id == supplier_id)
            .order_by(PurchaseOrder.date_order)
        )
        return list(self.session.scalars(stmt))
