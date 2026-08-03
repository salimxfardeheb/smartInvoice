"""Endpoints « tâches » : statut et historique des jobs asynchrones."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_invoice_service,
    get_task_manager,
    get_task_repository,
    require_permissions,
)
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.repositories import TaskRepository
from app.schemas.task import TaskListResponse, TaskRead, task_read
from app.services.invoice_service import InvoiceService
from app.services.task_manager import TaskManager

router = APIRouter()

InvoiceServiceDep = Annotated[InvoiceService, Depends(get_invoice_service)]
TaskRepoDep = Annotated[TaskRepository, Depends(get_task_repository)]
ManagerDep = Annotated[TaskManager, Depends(get_task_manager)]
JournalReadPerm = Annotated[object, Depends(require_permissions(Permission.INVOICE_READ))]


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Statut d'une tâche asynchrone (OCR)",
)
def get_task(
    task_id: int,
    service: InvoiceServiceDep = None,
    manager: ManagerDep = None,
    _: JournalReadPerm = None,
) -> TaskRead:
    """Retourne l'état courant d'une tâche (PENDING/RUNNING/SUCCEEDED/FAILED).

    Utilisé en *polling* par l'IHM après un appel asynchrone
    (``POST /api/invoices/{id}/process`` ou ``/retry``).
    """
    task = manager.get_task(task_id)
    if task is None:
        raise NotFoundError("Tâche introuvable.")
    return task_read(task)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="Historique des tâches asynchrones (filtrées par facture)",
)
def list_tasks(
    invoice_id: int | None = Query(default=None, description="Filtrer par facture"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tasks: TaskRepoDep = None,
    service: InvoiceServiceDep = None,
    _: JournalReadPerm = None,
) -> TaskListResponse:
    """Liste paginée des tâches, des plus récentes aux plus anciennes."""
    if invoice_id is not None:
        service.get_invoice(invoice_id)  # 404 si la facture n'existe pas
        items = tasks.list_by_invoice(invoice_id, limit=limit + offset)
        items = items[offset : offset + limit]
        total = len(tasks.list_by_invoice(invoice_id))
    else:
        all_items = tasks.list(limit=limit + offset, offset=offset)
        items = all_items
        total = tasks.count()
    return TaskListResponse(items=[task_read(t) for t in items], total=total)