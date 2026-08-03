"""Repository de l'entité ``Task`` (jobs asynchrones)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update

from app.models.enums import TaskKind, TaskState
from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Accès aux données des tâches asynchrones."""

    model = Task

    def create(
        self,
        *,
        kind: TaskKind,
        invoice_id: int | None = None,
    ) -> Task:
        """Crée (PENDING) une tâche rattachée éventuellement à une facture."""
        return self.add(Task(kind=kind, invoice_id=invoice_id))

    def mark_running(self, task_id: int) -> bool:
        """Passe une tâche PENDING → RUNNING. Retourne False si incohérent."""
        result = self.session.execute(
            update(Task)
            .where(Task.id == task_id, Task.state == TaskState.PENDING)
            .values(state=TaskState.RUNNING, started_at=datetime.utcnow())
        )
        return result.rowcount == 1

    def succeed(self, task_id: int, result_payload: str | None = None) -> None:
        self.session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                state=TaskState.SUCCEEDED,
                result=result_payload,
                finished_at=datetime.utcnow(),
            )
        )

    def fail(self, task_id: int, message: str) -> None:
        self.session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                state=TaskState.FAILED,
                error_message=message,
                finished_at=datetime.utcnow(),
            )
        )

    def get_by_id(self, task_id: int) -> Task | None:
        """Retourne une tâche par identifiant."""
        return self.get(task_id)

    def list_by_invoice(self, invoice_id: int, *, limit: int = 50) -> list[Task]:
        """Retourne les tâches d'une facture, des plus récentes aux plus anciennes."""
        stmt = (
            select(Task)
            .where(Task.invoice_id == invoice_id)
            .order_by(Task.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def count_by_state(self, state: TaskState) -> int:
        """Compte les tâches dans un état donné (utile pour les métriques)."""
        stmt = select(func.count(Task.id)).where(Task.state == state)
        return int(self.session.scalar(stmt) or 0)