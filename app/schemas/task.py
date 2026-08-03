"""Schémas des tâches asynchrones (jobs OCR, polling de statut)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskKind, TaskState
from app.models.task import Task


class TaskRead(BaseModel):
    """Statut observable d'une tâche asynchrone."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: TaskKind
    state: TaskState
    invoice_id: int | None = None
    error_message: str | None = None
    result: dict | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class TaskListResponse(BaseModel):
    """Page de tâches."""

    items: list[TaskRead]
    total: int = Field(ge=0)


def task_read(task: Task) -> TaskRead:
    """Construit un ``TaskRead`` à partir du modèle (résultat JSON décodé)."""
    import json

    result: dict | None = None
    if task.result:
        try:
            result = json.loads(task.result)
        except (TypeError, ValueError):
            result = None
    return TaskRead(
        id=task.id,
        kind=task.kind,
        state=task.state,
        invoice_id=task.invoice_id,
        error_message=task.error_message,
        result=result,
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
    )