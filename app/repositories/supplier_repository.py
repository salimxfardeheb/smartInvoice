"""Repository de l'entité ``Supplier`` (cache local du res.partner Odoo)."""

from __future__ import annotations

from sqlalchemy import select

from app.models.supplier import Supplier
from app.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    """Accès aux données des fournisseurs."""

    model = Supplier

    def create(
        self,
        *,
        odoo_id: int,
        name: str,
        vat: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        address: str | None = None,
    ) -> Supplier:
        """Crée un fournisseur dans le cache local."""
        return self.add(
            Supplier(
                odoo_id=odoo_id,
                name=name,
                vat=vat,
                email=email,
                phone=phone,
                address=address,
            )
        )

    def get_by_odoo_id(self, odoo_id: int) -> Supplier | None:
        """Retourne le fournisseur correspondant au ``res.partner`` Odoo."""
        stmt = select(Supplier).where(Supplier.odoo_id == odoo_id)
        return self.session.scalars(stmt).first()

    def get_by_vat(self, vat: str) -> Supplier | None:
        """Retourne le fournisseur correspondant au numéro de TVA."""
        stmt = select(Supplier).where(Supplier.vat == vat)
        return self.session.scalars(stmt).first()

    def search_by_name(self, name: str, *, limit: int = 20) -> list[Supplier]:
        """Recherche approximative (ILike) par nom de fournisseur."""
        pattern = f"%{name}%"
        stmt = (
            select(Supplier)
            .where(Supplier.name.ilike(pattern), Supplier.is_active.is_(True))
            .order_by(Supplier.name)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))
