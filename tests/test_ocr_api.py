"""Tests d'intégration de l'API OCR (phase 4).

Couvre le endpoint ``POST /api/invoices/{id}/process`` : succès, document
illisible, permissions, 404 et 409. Le moteur OCR est remplacé par un bouchon
via la dépendance ``get_ocr_engine_dep``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.enums import InvoiceStatus
from tests.ocr_fakes import (
    FakeOcrEngine,
    fake_engine_empty,
    fake_engine_ok,
    make_pdf_bytes,
)


@pytest.fixture()
def ocr_client(client, tmp_path):
    """Client de test avec stockage local et moteur OCR remplaçable."""
    from app.api.deps import get_ocr_engine_dep
    from app.storage import get_storage
    from app.storage.local import LocalStorage

    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    holder = {"engine": FakeOcrEngine()}
    client.app.dependency_overrides[get_ocr_engine_dep] = lambda: holder["engine"]
    yield client, holder
    client.app.dependency_overrides.clear()


def _create_supplier(engine, *, odoo_id: int = 1) -> int:
    from tests.conftest import make_supplier

    session = sessionmaker(bind=engine)()
    try:
        supplier = make_supplier(session, odoo_id=odoo_id, name="ACME SAS")
        session.commit()
        return supplier.id
    finally:
        session.close()


def _register_roles(client) -> dict[str, dict[str, str]]:
    """Crée admin + comptable + acheteur et retourne leurs en-têtes."""
    from app.models.enums import UserRole
    from tests.conftest import auth_headers, register_user

    register_user(client, username="admin", email="admin@example.com")
    admin = auth_headers(client, "admin")
    for username, role in (
        ("comptable", UserRole.ACCOUNTANT.value),
        ("acheteur", UserRole.BUYER.value),
    ):
        response = client.post(
            "/api/users",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "Password123!",
                "role": role,
            },
            headers=admin,
        )
        assert response.status_code in (201, 409), response.text
    return {
        "comptable": auth_headers(client, "comptable"),
        "acheteur": auth_headers(client, "acheteur"),
    }


def _deposit(client, headers, supplier_id, *, number: str = "FAC-OCR-API") -> int:
    response = client.post(
        "/api/invoices",
        files={"file": ("facture.pdf", make_pdf_bytes(), "application/pdf")},
        data={"invoice_number": number, "supplier_id": str(supplier_id)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestProcess:
    def test_process_success(self, ocr_client, engine) -> None:
        client, holder = ocr_client
        headers = _register_roles(client)["comptable"]
        supplier_id = _create_supplier(engine)
        invoice_id = _deposit(client, headers, supplier_id)
        holder["engine"] = fake_engine_ok()

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["invoice_id"] == invoice_id
        assert body["status"] == InvoiceStatus.TO_REVIEW.value
        assert body["ocr_confidence_score"] == pytest.approx(0.95, abs=1e-6)
        assert body["error_message"] is None
        assert body["extracted_data"]["general"]["invoice_number"] == "FAC-2026-001"
        assert len(body["extracted_data"]["lines"]) == 3

    def test_process_illegible_document(self, ocr_client, engine) -> None:
        client, holder = ocr_client
        headers = _register_roles(client)["comptable"]
        supplier_id = _create_supplier(engine)
        invoice_id = _deposit(client, headers, supplier_id)
        holder["engine"] = fake_engine_empty()

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == InvoiceStatus.SYSTEM_ERROR.value
        assert body["error_message"] is not None

    def test_process_missing_file(self, ocr_client, engine) -> None:
        client, holder = ocr_client
        headers = _register_roles(client)["comptable"]
        supplier_id = _create_supplier(engine)
        session = sessionmaker(bind=engine)()
        try:
            from app.repositories import InvoiceRepository

            invoice = InvoiceRepository(session).create(
                invoice_number="FAC-OCR-NOFILE", supplier_id=supplier_id
            )
            session.commit()
            invoice_id = invoice.id
        finally:
            session.close()
        holder["engine"] = fake_engine_ok()

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=headers
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == InvoiceStatus.SYSTEM_ERROR.value

    def test_process_requires_authentication(self, ocr_client, engine) -> None:
        client, _ = ocr_client
        supplier_id = _create_supplier(engine)
        response = client.post("/api/invoices/1/process")
        assert response.status_code == 401

    def test_process_requires_deposit_permission(self, ocr_client, engine) -> None:
        client, holder = ocr_client
        roles = _register_roles(client)
        supplier_id = _create_supplier(engine)
        invoice_id = _deposit(client, roles["comptable"], supplier_id)
        holder["engine"] = fake_engine_ok()

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=roles["acheteur"]
        )
        assert response.status_code == 403, response.text

    def test_process_unknown_invoice_404(self, ocr_client) -> None:
        client, _ = ocr_client
        headers = _register_roles(client)["comptable"]
        response = client.post("/api/invoices/999999/process", headers=headers)
        assert response.status_code == 404, response.text

    def test_process_invalid_state_409(self, ocr_client, engine) -> None:
        client, holder = ocr_client
        headers = _register_roles(client)["comptable"]
        supplier_id = _create_supplier(engine)
        invoice_id = _deposit(client, headers, supplier_id)
        response = client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": InvoiceStatus.ANALYZING.value},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        holder["engine"] = fake_engine_ok()

        response = client.post(
            f"/api/invoices/{invoice_id}/process", headers=headers
        )
        assert response.status_code == 409, response.text
