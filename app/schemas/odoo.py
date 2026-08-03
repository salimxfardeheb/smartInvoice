"""Schémas des endpoints de synchronisation Odoo.

Exposition des données synchronisées (fournisseurs, bons de commande, lignes)
avec le lien vers l'entité locale mise en cache. Les entrées sortantes
réutilisent les schémas du catalogue.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.catalog import (
    PurchaseOrderLineRead,
    PurchaseOrderRead,
    SupplierRead,
)


class SupplierSyncRequest(BaseModel):
    """Recherche/synchronisation d'un fournisseur Odoo par nom."""

    name: str = Field(min_length=1, description="Nom du fournisseur extrait (OCR)")


class SupplierSyncResponse(BaseModel):
    """Résultat de la synchronisation d'un fournisseur."""

    synced: bool
    supplier: SupplierRead


class PurchaseOrderSyncRequest(BaseModel):
    """Recherche/synchronisation d'un bon de commande Odoo par référence."""

    reference: str = Field(min_length=1, description="Référence du BC")


class PurchaseOrderSyncResponse(BaseModel):
    """Résultat de la synchronisation d'un bon de commande."""

    synced: bool
    purchase_order: PurchaseOrderRead


class PurchaseOrderLinesRead(BaseModel):
    """Lignes (mises en cache) d'un bon de commande."""

    purchase_order_id: int
    items: list[PurchaseOrderLineRead]
    total: int