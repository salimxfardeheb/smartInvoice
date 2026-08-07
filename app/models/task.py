"""Modèle « tâche » : job asynchrone (ex. OCR) exécuté hors du cycle requête."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TaskKind, TaskState, enum_values
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice


class Task(Base, TimestampMixin):
    """Exécution (ou planification) d'un job asynchrone asocia à une facture.

    La facture liée est fournie à titre de contexte ; un même job peut ne
    référencer aucune facture (libellé `kind` + `payload` suffit).
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_state_created_at", "state", "created_at"),
        Index("ix_tasks_invoice_id", "invoice_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[TaskKind] = mapped_column(
        Enum(
            TaskKind,
            name="task_kind",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    state: Mapped[TaskState] = mapped_column(
        Enum(
            TaskState,
            name="task_state",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=TaskState.PENDING,
        server_default=TaskState.PENDING.value,
    )
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[Invoice | None] = relationship(back_populates="tasks")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<Task id={self.id} kind={self.kind.value!r} state={self.state.value!r}>"