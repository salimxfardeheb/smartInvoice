"""Tests de la reprise au démarrage (tâches orphelines).

Trois niveaux de vérification :

1. la fonction de balayage :class:`recover_orphan_tasks` isolément (cas
   nominal, cas limites, idempotence) ;
2. son branchement effectif sur le ``lifespan`` de l'application ;
3. le déblocage vu de l'API : une facture bloquée en « En cours d'analyse »
   par un arrêt du serveur redevient relançable via ``/retry``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import (
    AuditAction,
    InvoiceStatus,
    TaskKind,
    TaskState,
)
from app.repositories import AuditLogRepository, InvoiceRepository, TaskRepository
from app.services.startup_recovery import (
    ORPHAN_TASK_MESSAGE,
    RecoveryReport,
    recover_orphan_tasks,
)
from tests.conftest import auth_headers, make_invoice, make_supplier, register_user


def _running_task(session: Session, invoice_id: int | None) -> object:
    """Crée une tâche déjà passée à l'état « en cours » (job interrompu)."""
    tasks = TaskRepository(session)
    task = tasks.create(kind=TaskKind.OCR, invoice_id=invoice_id)
    session.flush()
    tasks.mark_running(task.id)
    session.flush()
    return task


def _analyzing_invoice(session: Session, *, number: str = "FAC-2026-001") -> object:
    """Crée un fournisseur et une facture bloquée en « En cours d'analyse »."""
    supplier = make_supplier(session, odoo_id=1, name="ACME SAS")
    session.flush()
    invoice = make_invoice(
        session,
        supplier.id,
        invoice_number=number,
        status=InvoiceStatus.ANALYZING.value,
    )
    session.flush()
    return invoice


class TestRecoverOrphanTasks:
    """Balayage unitaire, sur session de test."""

    def test_running_task_is_failed_and_invoice_unblocked(
        self, session: Session
    ) -> None:
        invoice = _analyzing_invoice(session)
        task = _running_task(session, invoice.id)

        report = recover_orphan_tasks(session)
        session.flush()

        assert report == RecoveryReport(tasks_failed=1, invoices_recovered=1)

        refreshed_task = TaskRepository(session).get(task.id)
        assert refreshed_task.state is TaskState.FAILED
        assert refreshed_task.error_message == ORPHAN_TASK_MESSAGE
        assert refreshed_task.finished_at is not None

        refreshed_invoice = InvoiceRepository(session).get(invoice.id)
        assert refreshed_invoice.status is InvoiceStatus.SYSTEM_ERROR
        assert refreshed_invoice.error_message == ORPHAN_TASK_MESSAGE

    def test_recovery_is_traced_in_audit_log(self, session: Session) -> None:
        invoice = _analyzing_invoice(session)
        task = _running_task(session, invoice.id)

        recover_orphan_tasks(session)
        session.flush()

        entries = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.action is AuditAction.TASK_INTERRUPTED
        assert entry.message == ORPHAN_TASK_MESSAGE
        # Action système : aucun utilisateur à l'origine.
        assert entry.user_id is None
        assert entry.details == {
            "task_id": task.id,
            "task_kind": TaskKind.OCR.value,
            "previous_status": InvoiceStatus.ANALYZING.value,
            "new_status": InvoiceStatus.SYSTEM_ERROR.value,
        }

    def test_no_running_task_is_a_no_op(self, session: Session) -> None:
        invoice = _analyzing_invoice(session)

        report = recover_orphan_tasks(session)
        session.flush()

        assert report == RecoveryReport(tasks_failed=0, invoices_recovered=0)
        assert report.is_empty
        # Sans tâche interrompue, une facture « En cours d'analyse » n'est pas
        # touchée : elle peut appartenir à un job réellement en vol.
        assert InvoiceRepository(session).get(invoice.id).status is (
            InvoiceStatus.ANALYZING
        )
        assert AuditLogRepository(session).list_by_invoice(invoice.id) == []

    @pytest.mark.parametrize(
        "state", [TaskState.PENDING, TaskState.SUCCEEDED, TaskState.FAILED]
    )
    def test_only_running_tasks_are_swept(
        self, session: Session, state: TaskState
    ) -> None:
        """Les tâches non « en cours » sont laissées telles quelles."""
        invoice = _analyzing_invoice(session)
        tasks = TaskRepository(session)
        task = tasks.create(kind=TaskKind.OCR, invoice_id=invoice.id)
        session.flush()
        if state is not TaskState.PENDING:
            tasks.mark_running(task.id)
            if state is TaskState.SUCCEEDED:
                tasks.succeed(task.id, result_payload="{}")
            else:
                tasks.fail(task.id, "échec métier")
        session.flush()

        report = recover_orphan_tasks(session)
        session.flush()

        assert report.tasks_failed == 0
        assert report.invoices_recovered == 0
        assert TaskRepository(session).get(task.id).state is state

    def test_task_without_invoice_is_failed_without_side_effect(
        self, session: Session
    ) -> None:
        """``invoice_id`` est nullable : la tâche est neutralisée seule."""
        task = _running_task(session, None)

        report = recover_orphan_tasks(session)
        session.flush()

        assert report == RecoveryReport(tasks_failed=1, invoices_recovered=0)
        assert TaskRepository(session).get(task.id).state is TaskState.FAILED

    def test_invoice_that_already_progressed_is_left_alone(
        self, session: Session
    ) -> None:
        """L'OCR s'était terminé avant l'arrêt : la facture ne doit pas régresser.

        La tâche est bien neutralisée, mais une facture déjà passée « À
        vérifier » n'a aucune raison de repartir en « Erreur système ».
        """
        supplier = make_supplier(session, odoo_id=2, name="BETA SARL")
        session.flush()
        invoice = make_invoice(
            session,
            supplier.id,
            invoice_number="FAC-2026-002",
            status=InvoiceStatus.TO_REVIEW.value,
        )
        session.flush()
        _running_task(session, invoice.id)

        report = recover_orphan_tasks(session)
        session.flush()

        assert report == RecoveryReport(tasks_failed=1, invoices_recovered=0)
        assert InvoiceRepository(session).get(invoice.id).status is (
            InvoiceStatus.TO_REVIEW
        )
        assert AuditLogRepository(session).list_by_invoice(invoice.id) == []

    def test_several_orphans_are_all_recovered(self, session: Session) -> None:
        supplier = make_supplier(session, odoo_id=3, name="GAMMA SA")
        session.flush()
        invoices = []
        for index in range(3):
            invoice = make_invoice(
                session,
                supplier.id,
                invoice_number=f"FAC-2026-10{index}",
                status=InvoiceStatus.ANALYZING.value,
            )
            session.flush()
            _running_task(session, invoice.id)
            invoices.append(invoice)

        report = recover_orphan_tasks(session)
        session.flush()

        assert report == RecoveryReport(tasks_failed=3, invoices_recovered=3)
        for invoice in invoices:
            assert InvoiceRepository(session).get(invoice.id).status is (
                InvoiceStatus.SYSTEM_ERROR
            )

    def test_second_sweep_is_a_no_op(self, session: Session) -> None:
        """Idempotence : un second démarrage ne re-traite ni ne re-trace rien."""
        invoice = _analyzing_invoice(session)
        _running_task(session, invoice.id)

        first = recover_orphan_tasks(session)
        session.flush()
        second = recover_orphan_tasks(session)
        session.flush()

        assert first == RecoveryReport(tasks_failed=1, invoices_recovered=1)
        assert second.is_empty
        # Une seule entrée d'audit, pas une par redémarrage.
        assert len(AuditLogRepository(session).list_by_invoice(invoice.id)) == 1


class TestLifespanIntegration:
    """La reprise est bien câblée sur le démarrage de l'application."""

    def test_startup_sweeps_orphan_tasks(self, engine) -> None:
        from fastapi.testclient import TestClient

        from app.main import create_app

        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as setup:
            invoice = _analyzing_invoice(setup)
            task = _running_task(setup, invoice.id)
            invoice_id, task_id = invoice.id, task.id
            setup.commit()

        app = create_app(session_factory=session_factory)
        with TestClient(app):
            # Le lifespan s'exécute à l'entrée du contexte.
            assert app.state.recovery_report == RecoveryReport(
                tasks_failed=1, invoices_recovered=1
            )

        with session_factory() as check:
            assert TaskRepository(check).get(task_id).state is TaskState.FAILED
            assert InvoiceRepository(check).get(invoice_id).status is (
                InvoiceStatus.SYSTEM_ERROR
            )

    def test_startup_commits_the_sweep(self, engine) -> None:
        """Le balayage est bien committé (visible d'une autre session)."""
        from fastapi.testclient import TestClient

        from app.main import create_app

        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as setup:
            invoice = _analyzing_invoice(setup)
            _running_task(setup, invoice.id)
            invoice_id = invoice.id
            setup.commit()

        with TestClient(create_app(session_factory=session_factory)):
            pass

        with session_factory() as check:
            entries = AuditLogRepository(check).list_by_invoice(invoice_id)
            assert len(entries) == 1
            assert entries[0].action is AuditAction.TASK_INTERRUPTED

    def test_startup_is_a_no_op_on_a_clean_database(self, client) -> None:
        """Cas nominal : la fixture ``client`` démarre sans rien à reprendre."""
        assert client.app.state.recovery_report.is_empty

    def test_default_factory_resolves_session_local(self, engine, monkeypatch) -> None:
        """Sans fabrique explicite, le balayage vise ``SessionLocal``.

        C'est le chemin emprunté en production (``create_app()`` sans
        argument) : on substitue ``SessionLocal`` au moteur de test plutôt que
        d'ouvrir une vraie connexion PostgreSQL.
        """
        import app.db.session as session_module
        from fastapi.testclient import TestClient

        from app.main import create_app

        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        monkeypatch.setattr(session_module, "SessionLocal", session_factory)

        with session_factory() as setup:
            invoice = _analyzing_invoice(setup, number="FAC-2026-950")
            _running_task(setup, invoice.id)
            invoice_id = invoice.id
            setup.commit()

        app = create_app()  # aucune fabrique : résolution par défaut
        with TestClient(app):
            assert app.state.recovery_report == RecoveryReport(
                tasks_failed=1, invoices_recovered=1
            )

        with session_factory() as check:
            assert InvoiceRepository(check).get(invoice_id).status is (
                InvoiceStatus.SYSTEM_ERROR
            )

    def test_startup_survives_an_unreachable_database(self) -> None:
        """Un incident de base ne doit pas empêcher l'application de démarrer."""
        from fastapi.testclient import TestClient

        from app.main import create_app

        def broken_factory():
            raise RuntimeError("base injoignable")

        app = create_app(session_factory=broken_factory)
        with TestClient(app) as test_client:
            # L'application démarre malgré l'échec, le rapport reste vide.
            assert app.state.recovery_report.is_empty
            assert test_client.get("/docs").status_code == 200


class TestRecoveredInvoiceIsUsableAgain:
    """Bout en bout : la facture débloquée redevient relançable via l'API."""

    def test_retry_is_accepted_after_recovery(self, client, engine) -> None:
        register_user(client, username="compta")
        headers = auth_headers(client, "compta")

        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as setup:
            invoice = _analyzing_invoice(setup, number="FAC-2026-900")
            _running_task(setup, invoice.id)
            invoice_id = invoice.id
            setup.commit()

        # Avant reprise : la facture est inexploitable dans les deux sens.
        assert (
            client.post(f"/api/invoices/{invoice_id}/process", headers=headers)
            .status_code
            == 409
        )
        assert (
            client.post(f"/api/invoices/{invoice_id}/retry", headers=headers)
            .status_code
            == 409
        )

        with session_factory() as session:
            recover_orphan_tasks(session)
            session.commit()

        # Après reprise : « Erreur système », donc /retry est accepté (202).
        detail = client.get(f"/api/invoices/{invoice_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == InvoiceStatus.SYSTEM_ERROR.value

        retried = client.post(f"/api/invoices/{invoice_id}/retry", headers=headers)
        assert retried.status_code == 202, retried.text

    def test_recovery_entry_is_visible_in_the_audit_journal(
        self, client, engine
    ) -> None:
        register_user(client, username="auditeur")
        headers = auth_headers(client, "auditeur")

        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as setup:
            invoice = _analyzing_invoice(setup, number="FAC-2026-901")
            _running_task(setup, invoice.id)
            invoice_id = invoice.id
            setup.commit()

        with session_factory() as session:
            recover_orphan_tasks(session)
            session.commit()

        response = client.get(
            f"/api/invoices/{invoice_id}/audit-logs", headers=headers
        )
        assert response.status_code == 200
        actions = [item["action"] for item in response.json()["items"]]
        assert AuditAction.TASK_INTERRUPTED.value in actions
