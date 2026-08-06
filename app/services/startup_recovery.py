"""Reprise au démarrage : neutralisation des tâches orphelines.

La file de jobs (:mod:`app.services.task_manager`) vit **dans le processus** :
un pool de threads, sans broker ni persistance de la file. Une tâche en cours
d'exécution au moment d'un arrêt du serveur (redéploiement, OOM, crash) n'est
donc jamais reprise, mais laisse deux traces incohérentes en base :

- la ``Task`` reste indéfiniment à l'état « en cours » ;
- la facture associée reste bloquée en « En cours d'analyse », état depuis
  lequel ``POST /invoices/{id}/process`` répond 409 (analyse déjà en cours) et
  ``POST /invoices/{id}/retry`` répond 409 (état « Erreur système » exigé) —
  la facture est inexploitable sans intervention manuelle.

Ce module est appelé une fois au démarrage de l'application (``lifespan`` dans
:mod:`app.main`) : il marque ces tâches « échoué » et ramène les factures
concernées en « Erreur système », état depuis lequel ``/retry`` est justement
prévu. Chaque reprise est tracée dans le journal d'audit, sans utilisateur
(``user_id`` NULL) puisqu'il s'agit d'une action système.

La transition « En cours d'analyse » → « Erreur système » est celle du graphe
de :mod:`app.services.invoice_service` (``VALID_TRANSITIONS``) : la reprise ne
crée pas de chemin d'état nouveau, elle emprunte celui du pipeline en erreur.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.enums import AuditAction, InvoiceStatus, TaskState
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.task_repository import TaskRepository

#: Message porté par les tâches neutralisées et par ``invoice.error_message``.
ORPHAN_TASK_MESSAGE = "Tâche interrompue suite au redémarrage du serveur"


@dataclass(frozen=True)
class RecoveryReport:
    """Résultat d'un balayage de reprise.

    Attributs:
        tasks_failed: tâches « en cours » passées à « échoué ».
        invoices_recovered: factures débloquées (« En cours d'analyse » →
            « Erreur système »). Toujours ``<=`` ``tasks_failed`` : une tâche
            sans facture, ou dont la facture a déjà progressé, n'en débloque
            aucune.
    """

    tasks_failed: int = 0
    invoices_recovered: int = 0

    @property
    def is_empty(self) -> bool:
        """Indique qu'aucune incohérence n'a été trouvée (cas nominal)."""
        return self.tasks_failed == 0 and self.invoices_recovered == 0


def recover_orphan_tasks(session: Session) -> RecoveryReport:
    """Neutralise les tâches restées « en cours » et débloque leurs factures.

    Opère dans la session fournie **sans committer** : l'appelant maîtrise la
    transaction (le ``lifespan`` committe, les tests peuvent inspecter puis
    annuler). Retourne le détail de ce qui a été repris.
    """
    tasks = TaskRepository(session)
    invoices = InvoiceRepository(session)
    audit_logs = AuditLogRepository(session)

    orphans = tasks.list_by_state(TaskState.RUNNING)
    invoices_recovered = 0

    for task in orphans:
        tasks.fail(task.id, ORPHAN_TASK_MESSAGE)

        # Une tâche peut ne référencer aucune facture (``invoice_id`` nullable).
        if task.invoice_id is None:
            continue

        invoice = invoices.get(task.invoice_id)
        # La facture a pu progresser avant l'interruption (l'OCR s'était terminé
        # mais la tâche n'avait pas encore été marquée « réussi ») : on ne touche
        # que celles réellement bloquées.
        if invoice is None or invoice.status is not InvoiceStatus.ANALYZING:
            continue

        applied = invoices.update_cas(
            invoice.id,
            invoice.version,
            status=InvoiceStatus.SYSTEM_ERROR,
            error_message=ORPHAN_TASK_MESSAGE,
        )
        if not applied:  # pragma: no cover - aucune concurrence au démarrage
            continue

        # Ré-aligne l'instance en session : ``update_cas`` fait un UPDATE bulk
        # qui n'expire pas l'objet déjà chargé.
        invoice.status = InvoiceStatus.SYSTEM_ERROR
        invoice.error_message = ORPHAN_TASK_MESSAGE
        invoice.version += 1

        audit_logs.create(
            invoice_id=invoice.id,
            user_id=None,  # action système, aucun utilisateur à l'origine
            action=AuditAction.TASK_INTERRUPTED,
            message=ORPHAN_TASK_MESSAGE,
            details={
                "task_id": task.id,
                "task_kind": task.kind.value,
                "previous_status": InvoiceStatus.ANALYZING.value,
                "new_status": InvoiceStatus.SYSTEM_ERROR.value,
            },
        )
        invoices_recovered += 1

    return RecoveryReport(
        tasks_failed=len(orphans), invoices_recovered=invoices_recovered
    )
