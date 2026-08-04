"""Repository de l'entité ``PurchaseOrderLine`` (cache des lignes de BC Odoo)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.purchase_order_line import PurchaseOrderLine
from app.repositories.base import BaseRepository


class PurchaseOrderLineRepository(BaseRepository[PurchaseOrderLine]):
    """Accès aux données des lignes de bon de commande."""

    model = PurchaseOrderLine

    def create(
        self,
        *,
        purchase_order_id: int,
        odoo_id: int,
        line_number: int,
        product_ref: str | None = None,
        name: str | None = None,
        quantity: Decimal | None = None,
        unit: str | None = None,
        unit_price: Decimal | None = None,
        discount: Decimal | None = None,
        amount: Decimal | None = None,
        tax_rate: Decimal | None = None,
    ) -> PurchaseOrderLine:
        """Crée une ligne de bon de commande dans le cache local."""
        return self.add(
            PurchaseOrderLine(
                purchase_order_id=purchase_order_id,
                odoo_id=odoo_id,
                line_number=line_number,
                product_ref=product_ref,
                name=name,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                discount=discount,
                amount=amount,
                tax_rate=tax_rate,
            )
        )

    def get_by_odoo_id(self, odoo_id: int) -> PurchaseOrderLine | None:
        """Retourne la ligne correspondant au ``purchase.order.line`` Odoo."""
        stmt = select(PurchaseOrderLine).where(PurchaseOrderLine.odoo_id == odoo_id)
        return self.session.scalars(stmt).first()

    def list_by_purchase_order(
        self, purchase_order_id: int
    ) -> list[PurchaseOrderLine]:
        """Retourne les lignes d'un bon de commande, triées par position."""
        stmt = (
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == purchase_order_id)
            .order_by(PurchaseOrderLine.line_number)
        )
        return list(self.session.scalars(stmt))
