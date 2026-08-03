"""Endpoints de gestion du catalogue (fournisseurs et bons de commande).

CRUD API des référentiels mis en cache depuis Odoo : fournisseurs
(``suppliers``) et bons de commande (``purchase_orders``) avec leurs lignes.
Les lectures exigent la permission ``INVOICE_READ`` (tous les rôles) ; les
écritures manuelles sont réservées à la permission ``CONFIG_WRITE`` (ce
référentiel est normalement alimenté par la synchronisation Odoo).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_db, require_permissions
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.repositories import (
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
    SupplierRepository,
)
from app.schemas.catalog import (
    PurchaseOrderCreate,
    PurchaseOrderLineRead,
    PurchaseOrderListResponse,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierUpdate,
)

suppliers_router = APIRouter()
purchase_orders_router = APIRouter()

CatalogReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
CatalogWritePerm = Annotated[
    object, Depends(require_permissions(Permission.CONFIG_WRITE))
]


# --- Fournisseurs ---------------------------------------------------------


@suppliers_router.get(
    "",
    response_model=SupplierListResponse,
    summary="Lister les fournisseurs (paginé)",
)
def list_suppliers(
    search: str | None = Query(default=None, description="Filtrer par nom"),
    active: bool | None = Query(default=True, description="Uniquement actifs"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    _: CatalogReadPerm = None,
) -> SupplierListResponse:
    """Liste paginée des fournisseurs (recherche partielle sur le nom)."""
    repo = SupplierRepository(db)
    if search:
        items = repo.search_by_name(search, limit=limit)
        total = repo.count_by_name(search)
    else:
        items = [
            s
            for s in repo.list(limit=limit, offset=offset)
            if active is None or s.is_active is active
        ]
        total = repo.count()
    return SupplierListResponse(items=items, total=total)


@suppliers_router.post(
    "",
    response_model=SupplierRead,
    status_code=201,
    summary="Créer un fournisseur",
)
def create_supplier(
    payload: SupplierCreate,
    db=Depends(get_db),
    _: CatalogWritePerm = None,
) -> SupplierRead:
    return SupplierRepository(db).create(**payload.model_dump())


@suppliers_router.get(
    "/{supplier_id}",
    response_model=SupplierRead,
    summary="Consulter un fournisseur",
)
def get_supplier(
    supplier_id: int,
    db=Depends(get_db),
    _: CatalogReadPerm = None,
) -> SupplierRead:
    supplier = SupplierRepository(db).get(supplier_id)
    if supplier is None:
        raise NotFoundError("Fournisseur introuvable.")
    return supplier


@suppliers_router.patch(
    "/{supplier_id}",
    response_model=SupplierRead,
    summary="Mettre à jour un fournisseur",
)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db=Depends(get_db),
    _: CatalogWritePerm = None,
) -> SupplierRead:
    repo = SupplierRepository(db)
    supplier = repo.get(supplier_id)
    if supplier is None:
        raise NotFoundError("Fournisseur introuvable.")
    return repo.update(supplier, **payload.model_dump(exclude_unset=True))


@suppliers_router.delete(
    "/{supplier_id}",
    status_code=204,
    summary="Supprimer un fournisseur",
)
def delete_supplier(
    supplier_id: int,
    db=Depends(get_db),
    _: CatalogWritePerm = None,
) -> None:
    repo = SupplierRepository(db)
    supplier = repo.get(supplier_id)
    if supplier is None:
        raise NotFoundError("Fournisseur introuvable.")
    repo.delete(supplier)


# --- Bons de commande -------------------------------------------------------


@purchase_orders_router.get(
    "",
    response_model=PurchaseOrderListResponse,
    summary="Lister les bons de commande (paginé)",
)
def list_purchase_orders(
    supplier_id: int | None = Query(default=None, description="Filtrer par fournisseur"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    _: CatalogReadPerm = None,
) -> PurchaseOrderListResponse:
    """Liste paginée des bons de commande (filtre optionnel par fournisseur)."""
    repo = PurchaseOrderRepository(db)
    if supplier_id is not None:
        items = repo.list_by_supplier(supplier_id)
    else:
        items = repo.list(limit=limit, offset=offset)
    total = len(items) if supplier_id is not None else repo.count()
    return PurchaseOrderListResponse(
        items=[PurchaseOrderRead.model_validate(po) for po in items], total=total
    )


@purchase_orders_router.post(
    "",
    response_model=PurchaseOrderRead,
    status_code=201,
    summary="Créer un bon de commande",
)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    db=Depends(get_db),
    _: CatalogWritePerm = None,
) -> PurchaseOrderRead:
    supplier = SupplierRepository(db).get(payload.supplier_id)
    if supplier is None:
        raise NotFoundError("Fournisseur introuvable.")
    values = payload.model_dump()
    po = PurchaseOrderRepository(db).create(**values)
    return PurchaseOrderRead.model_validate(po)


@purchase_orders_router.get(
    "/{purchase_order_id}",
    response_model=PurchaseOrderRead,
    summary="Consulter un bon de commande",
)
def get_purchase_order(
    purchase_order_id: int,
    db=Depends(get_db),
    _: CatalogReadPerm = None,
) -> PurchaseOrderRead:
    po = PurchaseOrderRepository(db).get(purchase_order_id)
    if po is None:
        raise NotFoundError("Bon de commande introuvable.")
    return PurchaseOrderRead.model_validate(po)


@purchase_orders_router.get(
    "/{purchase_order_id}/lines",
    response_model=list[PurchaseOrderLineRead],
    summary="Lister les lignes d'un bon de commande",
)
def list_purchase_order_lines(
    purchase_order_id: int,
    db=Depends(get_db),
    _: CatalogReadPerm = None,
) -> list[PurchaseOrderLineRead]:
    po = PurchaseOrderRepository(db).get(purchase_order_id)
    if po is None:
        raise NotFoundError("Bon de commande introuvable.")
    lines = PurchaseOrderLineRepository(db).list_by_purchase_order(purchase_order_id)
    return [PurchaseOrderLineRead.model_validate(line) for line in lines]


@purchase_orders_router.patch(
    "/{purchase_order_id}",
    response_model=PurchaseOrderRead,
    summary="Mettre à jour un bon de commande",
)
def update_purchase_order(
    purchase_order_id: int,
    payload: PurchaseOrderUpdate,
    db=Depends(get_db),
    _: CatalogWritePerm = None,
) -> PurchaseOrderRead:
    repo = PurchaseOrderRepository(db)
    po = repo.get(purchase_order_id)
    if po is None:
        raise NotFoundError("Bon de commande introuvable.")
    return PurchaseOrderRead.model_validate(
        repo.update(po, **payload.model_dump(exclude_unset=True))
    )