"""Endpoints de gestion des anomalies.

Liste globale paginée et filtrable (sévérité, catégorie, statut résolu) et
résolution d'une anomalie. La résolution est une action de contrôle (sévérité
élevée) : elle est réservée aux rôles disposant de la permission de
validation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import (
    get_anomaly_repository,
    require_permissions,
)
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.models.enums import AnomalyCategory, AnomalySeverity
from app.repositories import AnomalyRepository
from app.schemas.anomaly import AnomalyListResponse, AnomalyRead

router = APIRouter()

AnomalyRepoDep = Annotated[AnomalyRepository, Depends(get_anomaly_repository)]
AnomalyReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
AnomalyResolvePerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_VALIDATE))
]


def _to_read(anomaly) -> AnomalyRead:
    """Schéma de sortie enrichi du contexte facture/fournisseur."""
    invoice = anomaly.invoice
    return AnomalyRead(
        id=anomaly.id,
        invoice_id=anomaly.invoice_id,
        invoice_number=invoice.invoice_number,
        supplier_name=invoice.supplier.name if invoice.supplier else None,
        category=anomaly.category,
        severity=anomaly.severity,
        message=anomaly.message,
        expected_value=anomaly.expected_value,
        actual_value=anomaly.actual_value,
        resolved=anomaly.resolved,
        resolved_at=anomaly.resolved_at,
        created_at=anomaly.created_at,
    )


@router.get(
    "",
    response_model=AnomalyListResponse,
    summary="Lister les anomalies (paginé, filtrable)",
)
def list_anomalies(
    severity: AnomalySeverity | None = Query(default=None, description="Filtrer par sévérité"),
    category: AnomalyCategory | None = Query(default=None, description="Filtrer par catégorie"),
    resolved: bool | None = Query(default=None, description="Filtrer par statut résolu"),
    invoice_id: int | None = Query(default=None, description="Filtrer par facture"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    anomalies: AnomalyRepoDep = None,
    _: AnomalyReadPerm = None,
) -> AnomalyListResponse:
    """Liste paginée des anomalies, avec filtres combinables et total."""
    items = anomalies.filter(
        severity=severity,
        category=category,
        resolved=resolved,
        invoice_id=invoice_id,
        limit=limit,
        offset=offset,
    )
    total = anomalies.count(
        severity=severity,
        category=category,
        resolved=resolved,
        invoice_id=invoice_id,
    )
    return AnomalyListResponse(items=[_to_read(a) for a in items], total=total)


@router.post(
    "/{anomaly_id}/resolve",
    response_model=AnomalyRead,
    summary="Résoudre une anomalie",
)
def resolve_anomaly(
    anomaly_id: Annotated[int, Path(description="Identifiant de l'anomalie")],
    anomalies: AnomalyRepoDep = None,
    _: AnomalyResolvePerm = None,
) -> AnomalyRead:
    """Marque une anomalie comme résolue (``resolved_at`` renseigné)."""
    anomaly = anomalies.get(anomaly_id)
    if anomaly is None:
        raise NotFoundError("Anomalie introuvable.")
    return _to_read(anomalies.resolve(anomaly))