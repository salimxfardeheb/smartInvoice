"""Endpoint « métriques » : exposition Prometheus des indicateurs d'exploitation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.metrics import get_metrics
from app.models.enums import TaskState
from app.repositories.task_repository import TaskRepository

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


@router.get(
    "/metrics",
    summary="Métriques d'exploitation (format texte Prometheus)",
    include_in_schema=False,
)
def metrics(db: DbDep) -> Response:
    """Retourne les métriques en texte brut au format d'exposition Prometheus."""
    metrics = get_metrics()
    # Jauge du nombre de tâches en file par état.
    for state in TaskState:
        metrics.set_gauge(f"task_queue_{state.value.replace(' ', '_')}",
                          TaskRepository(db).count_by_state(state))
    return Response(
        content=metrics.render(),
        media_type="text/plain; version=0.0.4",
    )