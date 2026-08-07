"""Tests des durcissements (phase 10) :

- tâches asynchrones OCR : /process → task_id, polling GET /api/tasks/{id},
  historique /api/tasks ;
- optimistic locking (CAS) sur les transitions de statut ;
- rate limiting de l'authentification (429) ;
- assainissement des saisies (numéro de facture, nom de fichier) ;
- métriques /metrics (texte Prometheus) ;
- réglages persistés en base (overrides de matching tolérés et lus en contexte).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from tests.conftest import auth_headers, register_user
from tests.ocr_fakes import FakeOcrEngine, make_pdf_bytes


def _supplier(engine) -> int:
    session = sessionmaker(bind=engine)()
    try:
        from tests.conftest import make_supplier

        supplier = make_supplier(session, odoo_id=10, name="ACME SAS")
        session.commit()
        return supplier.id
    finally:
        session.close()


def _accountant(client) -> dict:
    register_user(client, username="cptable", email="cptable@example.com")
    return auth_headers(client, "cptable")


@pytest.fixture()
def hardening_client(client, tmp_path):
    """Client avec stockage local et moteur OCR factice (tâches inline)."""
    from app.api.deps import get_ocr_engine_dep, get_storage
    from app.storage.local import LocalStorage

    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    client.app.dependency_overrides[get_ocr_engine_dep] = lambda: FakeOcrEngine()
    yield client
    client.app.dependency_overrides.clear()


class TestAsyncTasks:
    def test_process_returns_task_and_polling_gives_result(
        self, hardening_client, engine, tmp_path
    ) -> None:
        from app.api.deps import get_ocr_engine_dep
        from tests.ocr_fakes import fake_engine_ok

        client = hardening_client
        hardening_client.app.dependency_overrides[get_ocr_engine_dep] = (
            lambda: fake_engine_ok()
        )
        headers = _accountant(client)
        supplier_id = _supplier(engine)
        invoice = client.post(
            "/api/invoices",
            files={"file": ("f.pdf", make_pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-TASK-1", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        invoice_id = invoice.json()["id"]

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=headers
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["id"]

        task = client.get(f"/api/tasks/{task_id}", headers=headers)
        assert task.status_code == 200, task.text
        body = task.json()
        assert body["state"] == "réussi"
        assert body["invoice_id"] == invoice_id
        assert body["result"]["invoice_id"] == invoice_id

        listing = client.get("/api/tasks", headers=headers)
        assert listing.status_code == 200
        assert any(t["id"] == task_id for t in listing.json()["items"])

    def test_task_unknown_id_404(self, hardening_client) -> None:
        client = hardening_client
        headers = _accountant(client)
        assert client.get("/api/tasks/999999", headers=headers).status_code == 404

    def test_tasks_require_authentication(self, hardening_client) -> None:
        assert hardening_client.get("/api/tasks").status_code == 401


class TestOptimisticLock:
    def test_cas_rejects_stale_version(self, engine) -> None:
        from app.repositories import InvoiceRepository, SupplierRepository
        from tests.conftest import make_invoice

        Session = sessionmaker(bind=engine)
        with Session() as db:
            supplier = SupplierRepository(db).create(odoo_id=2, name="S2")
            inv = make_invoice(db, supplier.id)
            db.commit()
            invoice_id = inv.id
            loaded = InvoiceRepository(db).get(invoice_id)
            # 1re écriture : la version lue (0) correspond → accepté.
            assert InvoiceRepository(db).update_cas(
                invoice_id, loaded.version, status="En cours d'analyse"
            )
            # 2e écriture avec une version périmée → refusé (conflit).
            assert not InvoiceRepository(db).update_cas(
                invoice_id, loaded.version, status="Validée"
            )


class TestRateLimit:
    def test_login_throttled_after_burst(self, client, monkeypatch) -> None:
        from app.api import deps as deps_module
        from app.core.ratelimit import SlidingWindowLimiter

        register_user(client, username="rlim", email="rlim@example.com")
        limiter = SlidingWindowLimiter(max_calls=2, window_seconds=60)
        monkeypatch.setattr(deps_module, "get_limiter", lambda: limiter)

        for _ in range(2):
            assert client.post(
                "/api/auth/login",
                data={"username": "rlim", "password": "Password123!"},
            ).status_code == 200

        response = client.post(
            "/api/auth/login",
            data={"username": "rlim", "password": "Password123!"},
        )
        assert response.status_code == 429, response.text


class TestSanitise:
    def test_invoice_number_trimmed_and_filename_basename(
        self, hardening_client, engine
    ) -> None:
        client = hardening_client
        headers = _accountant(client)
        supplier_id = _supplier(engine)
        response = client.post(
            "/api/invoices",
            files={"file": ("../chemin/facture.pdf", make_pdf_bytes(), "application/pdf")},
            data={"invoice_number": "  FAC-SA-1  ", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["invoice_number"] == "FAC-SA-1"
        assert body["file_info"]["original_filename"] == "facture.pdf"

    def test_invoice_number_too_long_is_rejected(self, hardening_client, engine) -> None:
        client = hardening_client
        headers = _accountant(client)
        supplier_id = _supplier(engine)
        response = client.post(
            "/api/invoices",
            files={"file": ("f.pdf", make_pdf_bytes(), "application/pdf")},
            data={"invoice_number": "X" * 200, "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 422, response.text


class TestMetrics:
    def test_metrics_exposed_without_auth(self, hardening_client) -> None:
        response = hardening_client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "task_queue" in response.text


class TestPersistentSettings:
    def test_config_override_persists_and_is_read_by_matching(
        self, client, engine
    ) -> None:
        register_user(client, username="adminc", email="adminc@example.com")
        headers = auth_headers(client, "adminc")
        response = client.patch(
            "/api/config",
            json={"matching_quantity_tolerance": 0.5},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["matching_quantity_tolerance"] == 0.5

        from app.services.matching_service import MatchingService

        from app.repositories import SupplierRepository

        Session = sessionmaker(bind=engine)
        with Session() as db:
            SupplierRepository(db).create(odoo_id=9, name="S9")
            db.commit()
            sm = MatchingService(db)
            assert sm.quantity_tolerance == 0.5