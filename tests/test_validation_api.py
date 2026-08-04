"""Tests d'intégration de l'API Validation (phase 7).

Couvre le endpoint de validation, de rejet (motif obligatoire), de correction
manuelle, de création de la Vendor Bill Odoo (succès et échec → 502) et la
lecture du journal d'audit, ainsi que les permissions et les erreurs.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import OdooError
from app.models.enums import InvoiceStatus


class FakeOdooClient:
    """Bouchon du client Odoo : joue la création et enregistre les appels."""

    def __init__(
        self,
        *,
        move_id: int = 1001,
        error: OdooError | None = None,
        existing_moves: list[dict] | None = None,
    ) -> None:
        self.move_id = move_id
        self.error = error
        self.existing_moves = list(existing_moves or [])
        self.calls: list[tuple[str, dict]] = []

    def create(self, model: str, values: dict) -> int:
        self.calls.append((model, values))
        if self.error is not None:
            raise self.error
        return self.move_id

    def search_read(self, model, domain, fields, *, limit=None, offset=0) -> list[dict]:
        return list(self.existing_moves)


@pytest.fixture()
def validation_client(client, tmp_path):
    """Client de test branché sur un service de validation avec Odoo bouchon."""
    from app.api.deps import get_db, get_storage, get_validation_service
    from app.services.validation_service import ValidationService
    from app.storage.local import LocalStorage

    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    holder = {"fake": FakeOdooClient()}

    def _override_service(db=Depends(get_db)):
        return ValidationService(db, odoo_client=holder["fake"])

    client.app.dependency_overrides[get_validation_service] = _override_service
    yield client, holder
    client.app.dependency_overrides.clear()


def _create_invoice(
    engine, *, number: str = "FAC-API-001", status: str = "À vérifier"
) -> int:
    """Crée une facture liée à un fournisseur et retourne son id."""
    from tests.conftest import make_invoice, make_supplier

    session = sessionmaker(bind=engine)()
    try:
        supplier = make_supplier(session, odoo_id=42, name="ACME SAS")
        invoice = make_invoice(
            session, supplier.id, invoice_number=number, status=status
        )
        session.commit()
        return invoice.id
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


class TestValidate:
    def test_validate_success(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == InvoiceStatus.VALIDATED.value

        logs = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers)
        assert logs.status_code == 200
        assert logs.json()["items"][0]["action"] == "validation"

    def test_validate_requires_validated_state(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine, status="Déposée")

        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)

        assert response.status_code == 409, response.text

    def test_validate_unknown_invoice_404(self, validation_client) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]

        response = client.post("/api/invoices/999999/validate", headers=headers)
        assert response.status_code == 404, response.text

    def test_validate_requires_authentication(self, validation_client, engine) -> None:
        client, _ = validation_client
        invoice_id = _create_invoice(engine)
        response = client.post(f"/api/invoices/{invoice_id}/validate")
        assert response.status_code == 401

    def test_validate_requires_validate_permission(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["acheteur"]
        invoice_id = _create_invoice(engine)

        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)
        assert response.status_code == 403, response.text


class TestReject:
    def test_reject_requires_reason(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        response = client.post(f"/api/invoices/{invoice_id}/reject", json={}, headers=headers)
        assert response.status_code == 422, response.text

    def test_reject_success(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        response = client.post(
            f"/api/invoices/{invoice_id}/reject",
            json={"reason": "Montant HT différent du bon de commande."},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == InvoiceStatus.REJECTED.value
        assert body["rejection_reason"] == "Montant HT différent du bon de commande."


class TestCorrect:
    def test_correct_fields(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        response = client.put(
            f"/api/invoices/{invoice_id}/correct",
            json={"total_excl_tax": "88.50", "currency": "EUR"},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["total_excl_tax"] == "88.50"

    def test_correct_lines(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        response = client.put(
            f"/api/invoices/{invoice_id}/correct",
            json={
                "lines": [
                    {
                        "line_number": 1,
                        "description": "Câble HDMI",
                        "product_ref": "CBL-001",
                        "quantity": "10.0",
                        "unit_price": "9.00",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text

        details = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers)
        assert details.status_code == 200
        assert details.json()["items"][0]["action"] == "correction"
        assert details.json()["total"] == 1

    def test_correct_requires_correct_permission(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["acheteur"]
        invoice_id = _create_invoice(engine)

        response = client.put(
            f"/api/invoices/{invoice_id}/correct",
            json={"currency": "USD"},
            headers=headers,
        )
        assert response.status_code == 403, response.text


class TestCreateVendorBill:
    def _validate(self, client, headers, invoice_id) -> None:
        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)
        assert response.status_code == 200, response.text

    def test_vendor_bill_success(self, validation_client, engine) -> None:
        client, holder = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)
        self._validate(client, headers, invoice_id)

        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == InvoiceStatus.VENDOR_BILL_CREATED.value
        assert body["vendor_bill_id"] == holder["fake"].move_id

        assert holder["fake"].calls[0][0] == "account.move"

    def test_vendor_bill_failure_returns_502(self, validation_client, engine) -> None:
        client, holder = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)
        self._validate(client, headers, invoice_id)

        holder["fake"].error = OdooError("Odoo indisponible")
        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)

        assert response.status_code == 502, response.text
        # La facture reste « Validée » : nouvelle tentative possible.
        current = client.get(f"/api/invoices/{invoice_id}", headers=headers)
        assert current.json()["status"] == InvoiceStatus.VALIDATED.value

    def test_vendor_bill_requires_validated(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)  # À vérifier

        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)
        assert response.status_code == 409, response.text


class TestAuditLogs:
    def test_audit_logs_trace_actions_in_order(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]
        invoice_id = _create_invoice(engine)

        client.put(
            f"/api/invoices/{invoice_id}/correct",
            json={"currency": "USD"},
            headers=headers,
        )
        client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)

        response = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        actions = [entry["action"] for entry in body["items"]]
        assert actions == ["validation", "correction"]
        assert body["total"] == 2
        assert body["items"][0]["message"].startswith("Facture validée")
        assert body["items"][0]["user"]["username"] == "comptable"

    def test_audit_logs_require_journal_permission(self, validation_client, engine) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["acheteur"]
        invoice_id = _create_invoice(engine)

        response = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers)
        assert response.status_code == 403, response.text

    def test_audit_logs_unknown_invoice_404(self, validation_client) -> None:
        client, _ = validation_client
        headers = _register_roles(client)["comptable"]

        response = client.get("/api/invoices/999999/audit-logs", headers=headers)
        assert response.status_code == 404, response.text
