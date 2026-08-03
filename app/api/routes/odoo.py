"""Endpoints de synchronisation Odoo (phase 5).

Expose le :class:`OdooSyncService` sous forme de routes FastAPI :
synchronisation d'un fournisseur par nom, d'un bon de commande par référence,
et lecture/actualisation des lignes d'un BC mis en cache localement.

Les recherches sont faites dans Odoo ; les entités trouvées sont écrites dans
le cache local et renvoyées (``synced: true``). En cas de fournisseur ou de
BC introuvable, l'erreur métier correspondante est traduite en HTTP (404/409/502).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import get_odoo_sync_service, require_permissions
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.schemas.odoo import (
    PurchaseOrderLinesRead,
    PurchaseOrderSyncRequest,
    PurchaseOrderSyncResponse,
    SupplierSyncRequest,
    SupplierSyncResponse,
)
from app.services.odoo_service import OdooSyncService

router = APIRouter()

OdooSyncServiceDep = Annotated[OdooSyncService, Depends(get_odoo_sync_service)]
SyncReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
SyncWritePerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_DEPOSIT))
]


def _get_cached_purchase_order(service: OdooSyncService, po_id: int):
    """Retourne le BC local (404 si absent)."""
    purchase_order = service.purchase_orders.get(po_id)
    if purchase_order is None:
        raise NotFoundError("Bon de commande introuvable dans le cache local.")
    return purchase_order


@router.post(
    "/suppliers",
    response_model=SupplierSyncResponse,
    summary="Synchroniser un fournisseur Odoo par nom",
)
def sync_supplier(
    payload: SupplierSyncRequest,
    service: OdooSyncServiceDep = None,
    _: SyncWritePerm = None,
) -> SupplierSyncResponse:
    """Recherche le fournisseur dans Odoo (par nom) et le met en cache local."""
    supplier = service.sync_supplier_from_name(payload.name)
    return SupplierSyncResponse(synced=True, supplier=supplier)


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderSyncResponse,
    summary="Synchroniser un bon de commande Odoo par référence",
)
def sync_purchase_order(
    payload: PurchaseOrderSyncRequest,
    service: OdooSyncServiceDep = None,
    _: SyncWritePerm = None,
) -> PurchaseOrderSyncResponse:
    """Recherche le bon de commande dans Odoo (par référence) et le met en cache."""
    purchase_order = service.find_purchase_order(payload.reference)
    return PurchaseOrderSyncResponse(synced=True, purchase_order=purchase_order)


@router.get(
    "/purchase-orders/{purchase_order_id}/lines",
    response_model=PurchaseOrderLinesRead,
    summary="Lire les lignes (en cache) d'un bon de commande",
)
def get_purchase_order_lines(
    purchase_order_id: Annotated[int, Path(description="Identifiant du bon de commande")],
    service: OdooSyncServiceDep = None,
    _: SyncReadPerm = None,
) -> PurchaseOrderLinesRead:
    """Retourne les lignes du bon de commande actuellement mises en cache."""
    purchase_order = _get_cached_purchase_order(service, purchase_order_id)
    lines = service.purchase_order_lines.list_by_purchase_order(purchase_order.id)
    return PurchaseOrderLinesRead(
        purchase_order_id=purchase_order.id,
        items=lines,
        total=len(lines),
    )


@router.post(
    "/purchase-orders/{purchase_order_id}/lines",
    response_model=PurchaseOrderLinesRead,
    summary="Actualiser les lignes d'un bon de commande depuis Odoo",
)
def sync_purchase_order_lines(
    purchase_order_id: Annotated[int, Path(description="Identifiant du bon de commande")],
    service: OdooSyncServiceDep = None,
    _: SyncWritePerm = None,
) -> PurchaseOrderLinesRead:
    """Recherche et crée/actualise les lignes d'un bon de commande dans Odoo."""
    purchase_order = _get_cached_purchase_order(service, purchase_order_id)
    lines = service.load_purchase_order_lines(purchase_order)
    return PurchaseOrderLinesRead(
        purchase_order_id=purchase_order.id,
        items=lines,
        total=len(lines),
    )