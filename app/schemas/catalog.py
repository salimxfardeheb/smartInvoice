"""Schémas du catalogue (fournisseurs et bons de commande).

Fournit le CRUD API des référentiels : les ``suppliers`` (cache local de
``res.partner`` Odoo) et les ``purchase_orders`` (cache de ``purchase.order``)
avec leurs lignes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):
    """Création manuelle d'un fournisseur (référentiel)."""

    odoo_id: int = Field(ge=1, description="Identifiant du partenaire Odoo")
    name: str = Field(min_length=1, max_length=255)
    vat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None)


class SupplierUpdate(BaseModel):
    """Mise à jour partielle d'un fournisseur."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    vat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None)
    is_active: bool | None = None


class SupplierRead(BaseModel):
    """Fournisseur exposé par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    odoo_id: int
    name: str
    vat: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool


class SupplierListResponse(BaseModel):
    """Résultat paginé de la liste des fournisseurs."""

    items: list[SupplierRead]
    total: int


class PurchaseOrderCreate(BaseModel):
    """Création manuelle d'un bon de commande (cache local)."""

    odoo_id: int = Field(ge=1, description="Identifiant du purchase.order Odoo")
    reference: str = Field(min_length=1, max_length=64)
    supplier_id: int
    state: str | None = Field(default=None, max_length=32)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    date_order: date | None = None
    total_amount: Decimal | None = None


class PurchaseOrderUpdate(BaseModel):
    """Mise à jour partielle d'un bon de commande."""

    supplier_id: int | None = None
    state: str | None = Field(default=None, max_length=32)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    date_order: date | None = None
    total_amount: Decimal | None = None


class PurchaseOrderSupplierBrief(BaseModel):
    """Représentation allégée du fournisseur d'un bon de commande."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PurchaseOrderRead(BaseModel):
    """Bon de commande exposé par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    odoo_id: int
    reference: str
    supplier_id: int
    state: str | None = None
    currency: str = "EUR"
    date_order: date | None = None
    total_amount: Decimal | None = None

    supplier: PurchaseOrderSupplierBrief | None = None


class PurchaseOrderLineRead(BaseModel):
    """Ligne de bon de commande exposée par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_id: int
    odoo_id: int
    line_number: int
    product_ref: str | None = None
    name: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    amount: Decimal | None = None


class PurchaseOrderListResponse(BaseModel):
    """Résultat paginé de la liste des bons de commande."""

    items: list[PurchaseOrderRead]
    total: int