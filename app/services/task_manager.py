"""Gestionnaire de tâches asynchrones (file d'attente des jobs OCR).

Basé sur un *thread pool* in-process : aucune infrastructure externe (broker)
n'est requise, chaque job exécute son propre cycle de transaction sur sa
propre session SQLAlchemy, distincte de la session de la requête HTTP.

Trois exécuteurs sont fournis :
- :class:`ThreadedExecutor` : exécution réelle dans un pool de threads ;
- :class:`InlineExecutor` : exécution immédiate dans l'appelant (tests).
Un exécuteur ``None`` correspond aussi à de l'exécution synchrone.

Le cycle d'une tâche : ``PENDING`` → ``RUNNING`` → ``SUCCEEDED`` | ``FAILED``,
chaque transition étant commitée pour être observable par polling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.enums import TaskKind
from app.repositories.task_repository import TaskRepository


class Executor(ABC):
    """Abstraction de lancement d'un job (thread réel ou inline)."""

    @abstractmethod
    def submit(self, fn: Callable[[], None]) -> None:  # pragma: no cover
        ...


class ThreadedExecutor(Executor):
    """Exécute les jobs dans un pool de threads de taille fixe."""

    def __init__(self, workers: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers))

    def submit(self, fn: Callable[[], None]) -> None:
        self._pool.submit(fn)

    def shutdown(self) -> None:  # pragma: no cover - utilité de nettoyage
        self._pool.shutdown(wait=False)


class InlineExecutor(Executor):
    """Exécute le job immédiatement, dans le fil d'appel (tests déterministes)."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()


RunFn = Callable[["TaskManager", int], Any]


class TaskManager:
    """De file de jobs, responsable du cycle de vie ``Task`` et du dispatch."""

    def __init__(
        self,
        *,
        session_factory: Any = SessionLocal,
        executor: Executor | None = None,
        workers: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        workers = workers if workers is not None else get_settings().task_queue_workers
        # ``InlineExecutor`` / ``None`` → exécution synchrone (tests, dev).
        self.executor = (
            executor
            if isinstance(executor, InlineExecutor)
            else (ThreadedExecutor(workers) if executor is None else executor)
        )

    # --- Envoi ---------------------------------------------------------------

    def submit(
        self,
        *,
        kind: TaskKind,
        invoice_id: int | None = None,
        run: RunFn,
    ) -> int:
        """Crée une tâche PENDING, la planifie et retourne son identifiant.

        La fonction ``run`` est exécutée dans son propre contexte de session ;
        elle reçoit le gestionnaire afin de récupérer ``session_factory``.
        """
        task_id = self._create_task(kind, invoice_id)

        def _execute() -> None:
            try:
                self._phase_running(task_id)
                payload = run(self)
                self._phase_success(task_id, payload)
            except Exception as exc:  # noqa: BLE001 - état FAILED attendu
                self._phase_failed(task_id, exc)

        self.executor.submit(_execute)
        return task_id

    def get_task(self, task_id: int) -> Any:
        """Retourne la tâche (session fraîche), détachée pour usage hors-session."""
        with self.session_factory() as session:
            task = TaskRepository(session).get(task_id)
            if task is not None:
                session.expunge(task)
            return task

    # --- Cycle de vie persistant ---------------------------------------------

    def _create_task(self, kind: TaskKind, invoice_id: int | None) -> int:
        with self.session_factory() as session:
            task = TaskRepository(session).create(kind=kind, invoice_id=invoice_id)
            session.commit()
            return task.id

    def _write_running(self, task_id: int) -> None:
        with self.session_factory() as session:
            TaskRepository(session).mark_running(task_id)
            session.commit()

    def _phase_running(self, task_id: int) -> None:
        self._write_running(task_id)

    def _phase_success(self, task_id: int, payload: Any) -> None:
        import json

        raw = payload if isinstance(payload, str) else json.dumps(payload)
        with self.session_factory() as session:
            TaskRepository(session).succeed(task_id, result_payload=raw)
            session.commit()

    def _phase_failed(self, task_id: int, exc: Exception) -> None:
        with self.session_factory() as session:
            TaskRepository(session).fail(task_id, message=str(exc))
            session.commit()


# Singleton d'application : gestionnaire lié à ``SessionLocal`` et au pool.
_default_manager: TaskManager | None = None


def get_default_task_manager() -> TaskManager:
    """Retourne le gestionnaire de tâches partagé de l'application.

    La charge de travail (nombre de workers) provient de la configuration ;
    on le construit paresseusement pour ne créer le pool qu'au premier usage.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = TaskManager()
    return _default_manager