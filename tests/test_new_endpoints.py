"""Tests d'intégration des nouveaux endpoints (synchronisation Odoo, anomalies,
configuration, catalogue, confirmation acheteur, relance, dépôt par lot).

Couvre les routes exposées par les nouveaux routers :
``/api/odoo/sync/*``, ``/api/anomalies``, ``/api/config``, ``/api/suppliers``,
``/api/purchase-orders`` et les extensions de ``/api/invoices`` (confirm,
retry, batch).
"""

from __future__ import annotations

import io

import pytest
from fastapi import Depends
from PIL import Image
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import OdooError  # noqa: F401  (utile aux bouchons)
from app.models.enums import (
    AnomalyCategory,
    AnomalySeverity,
    AuditAction,
    InvoiceStatus,
    UserRole,
)
from app.services.odoo_service import OdooSyncService


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    return buf.getvalue()


def _register_roles(client) -> dict[str, dict[str, str]]:
    """Crée admin + comptable + acheteur et retourne leurs en-têtes."""
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
        "admin": admin,
        "comptable": auth_headers(client, "comptable"),
        "acheteur": auth_headers(client, "acheteur"),
    }


def _make_supplier_invoice(engine, *, status: str = "À vérifier", odoo_id: int = 42):
    """Crée fournisseur + facture ; retourne (supplier_id, invoice_id)."""
    from tests.conftest import make_invoice, make_supplier

    db = sessionmaker(bind=engine)()
    try:
        supplier = make_supplier(db, odoo_id=odoo_id, name="ACME SAS")
        invoice = make_invoice(
            db, supplier.id, invoice_number=f"FAC-NEW-{odoo_id}", status=status
        )
        db.commit()
        return supplier.id, invoice.id
    finally:
        db.close()


# --- Synchronisation Odoo --------------------------------------------------


class FakeOdooClient:
    """Bouchon du client Odoo jouant les enregistrements par modèle."""

    def __init__(self, holder) -> None:
        self.holder = holder

    def search_read(self, model, domain, fields, *, limit=None, offset=0):
        return list(self.holder.get(model, []))


def _partner(odoo_id, name, **extra):
    return {"id": odoo_id, "name": name, **extra}


def _po(odoo_id, ref, partner_id):
    return {
        "id": odoo_id, "name": ref, "partner_id": (partner_id, "ACME SAS"),
        "state": "purchase", "date_order": "2026-01-10",
        "amount_total": 100.0, "currency_id": (1, "EUR"),
    }


def _line(odoo_id, order_id, seq, ref, name):
    return {
        "id": odoo_id, "order_id": order_id, "sequence": seq,
        "product_id": (5, name), "name": name, "product_qty": 2.0,
        "product_uom": (1, "Unités"), "price_unit": 8.5, "discount": 0.0,
        "price_subtotal": 17.0,
    }


@pytest.fixture()
def odoo_sync(client):
    from app.api.deps import get_db, get_odoo_sync_service

    holder = {
        "res.partner": [_partner(7, "ACME SAS", vat="FR123")],
        "purchase.order": [_po(100, "PO-2026-001", 7)],
        "purchase.order.line": [_line(1, 100, 10, "CBL-001", "Câble HDMI")],
        "product.product": [{"id": 5, "default_code": "CBL-001"}],
    }

    def _override(db=Depends(get_db)):
        return OdooSyncService(db, FakeOdooClient(holder))

    client.app.dependency_overrides[get_odoo_sync_service] = _override
    yield client
    client.app.dependency_overrides.clear()


class TestOdooSyncEndpoints:
    def test_sync_supplier_by_name(self, odoo_sync, engine) -> None:
        headers = _register_roles(odoo_sync)["comptable"]
        resp = odoo_sync.post(
            "/api/odoo/sync/suppliers", json={"name": "ACME SAS"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["synced"] is True
        assert body["supplier"]["name"] == "ACME SAS"

    def test_sync_purchase_order_by_reference(self, odoo_sync, engine) -> None:
        from tests.conftest import make_supplier

        headers = _register_roles(odoo_sync)["comptable"]
        # Le fournisseur du BC doit d'abord être mis en cache local.
        db = sessionmaker(bind=engine)()
        try:
            make_supplier(db, odoo_id=7, name="ACME SAS")
            db.commit()
        finally:
            db.close()
        resp = odoo_sync.post(
            "/api/odoo/sync/purchase-orders", json={"reference": "PO-2026-001"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["synced"] is True
        assert resp.json()["purchase_order"]["reference"] == "PO-2026-001"

    def test_purchase_order_lines_read_and_sync(self, odoo_sync, engine) -> None:
        from app.repositories import PurchaseOrderRepository, SupplierRepository

        headers = _register_roles(odoo_sync)["comptable"]
        supplier_id, _ = _make_supplier_invoice(engine, status="Déposée")
        db = sessionmaker(bind=engine)()
        try:
            po = PurchaseOrderRepository(db).create(
                odoo_id=100, reference="PO-2026-001", supplier_id=supplier_id
            )
            db.commit()
            po_id = po.id
        finally:
            db.close()

        # Lecture des lignes en cache → vide si non synchronisées.
        read = odoo_sync.get(f"/api/odoo/sync/purchase-orders/{po_id}/lines", headers=headers)
        assert read.status_code == 200, read.text
        assert read.json()["items"] == []

        # Synchronisation depuis Odoo → 1 ligne.
        synced = odoo_sync.post(
            f"/api/odoo/sync/purchase-orders/{po_id}/lines", headers=headers
        )
        assert synced.status_code == 200, synced.text
        assert synced.json()["total"] == 1
        assert synced.json()["items"][0]["product_ref"] == "CBL-001"


# --------------------------------------------------------------------------
# Anomalies


def _create_anomalies(engine, invoice_id) -> list[int]:
    from app.repositories import AnomalyRepository

    db = sessionmaker(bind=engine)()
    try:
        repo = AnomalyRepository(db)
        crit = repo.create(
            invoice_id=invoice_id, category=AnomalyCategory.AMOUNT,
            severity=AnomalySeverity.CRITICAL, message="Montant en écart",
            expected_value="100", actual_value="120",
        )
        warn = repo.create(
            invoice_id=invoice_id, category=AnomalyCategory.QUANTITY,
            severity=AnomalySeverity.WARNING, message="Quantité différente.",
        )
        db.commit()
        crit_id, warn_id = crit.id, warn.id
        repo.resolve(warn)
        db.commit()
        return [crit_id, warn_id]
    finally:
        db.close()


class TestAnomaliesEndpoints:
    def test_list_anomalies_filters(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        _, invoice_id = _make_supplier_invoice(engine)
        _create_anomalies(engine, invoice_id)

        resp = client.get("/api/anomalies?resolved=false", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["severity"] == "critical"

    def test_resolve_anomaly(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        _, invoice_id = _make_supplier_invoice(engine)
        crit_id, _ = _create_anomalies(engine, invoice_id)

        resp = client.post(f"/api/anomalies/{crit_id}/resolve", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["resolved"] is True
        assert resp.json()["resolved_at"] is not None

    def test_resolve_invoice_anomaly(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        supplier_id, invoice_id = _make_supplier_invoice(engine)
        crit_id, _ = _create_anomalies(engine, invoice_id)
        _, other_id = _make_supplier_invoice(engine, odoo_id=43)
        resp = client.post(
            f"/api/invoices/{invoice_id}/anomalies/{crit_id}/resolve", headers=headers
        )
        assert resp.status_code == 200, resp.text
        # Une anomalie appartenant à une autre facture → 404.
        resp2 = client.post(
            f"/api/invoices/{other_id}/anomalies/{crit_id}/resolve", headers=headers
        )
        assert resp2.status_code == 404, resp2.text

    def test_anomalies_unauthenticated(self, client, engine) -> None:
        assert client.get("/api/anomalies").status_code == 401


# --------------------------------------------------------------------------
# Configuration


class TestConfigEndpoints:
    def test_read_config_returns_public_settings(self, client, engine) -> None:
        headers = _register_roles(client)["admin"]
        resp = client.get("/api/config", headers=headers)
        assert resp.status_code == 200, resp.text
        assert "matching_amount_tolerance" in resp.json()
        # Jamais de secret exposé.
        assert "odoo_password" not in resp.json()

    def test_read_requires_config_permission(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        assert client.get("/api/config", headers=headers).status_code == 403

    def test_update_config_requires_write_permission(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        resp = client.patch("/api/config", json={"matching_quantity_tolerance": 0.1}, headers=headers)
        assert resp.status_code == 403, resp.text

    def test_update_config_applies_override(self, client, engine) -> None:
        headers = _register_roles(client)["admin"]
        resp = client.patch(
            "/api/config", json={"matching_quantity_tolerance": 0.1}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["matching_quantity_tolerance"] == 0.1


# --------------------------------------------------------------------------
# Catalogue (fournisseurs / bons de commande)


class TestCatalogEndpoints:
    def test_supplier_crud(self, client, engine) -> None:
        roles = _register_roles(client)

        # Lecture par le comptable (INVOICE_READ).
        listing = client.get("/api/suppliers", headers=roles["comptable"])
        assert listing.status_code == 200, listing.text

        # Création refusée au comptable (CONFIG_WRITE requis)...
        denied = client.post(
            "/api/suppliers", json={"odoo_id": 1, "name": "ACME"}, headers=roles["comptable"]
        )
        assert denied.status_code == 403, denied.text

        # ...mais acceptée par l'admin.
        created = client.post(
            "/api/suppliers", json={"odoo_id": 1, "name": "ACME SAS"}, headers=roles["admin"]
        )
        assert created.status_code == 201, created.text
        supplier_id = created.json()["id"]

        updated = client.patch(
            f"/api/suppliers/{supplier_id}", json={"vat": "FR12345"}, headers=roles["admin"]
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["vat"] == "FR12345"

        assert client.get(
            f"/api/suppliers/{supplier_id}", headers=roles["comptable"]
        ).status_code == 200

    def test_purchase_order_read_and_lines(self, client, engine) -> None:
        from app.repositories import PurchaseOrderRepository

        roles = _register_roles(client)
        supplier_id, _ = _make_supplier_invoice(engine, status="Déposée")
        db = sessionmaker(bind=engine)()
        try:
            po = PurchaseOrderRepository(db).create(
                odoo_id=200, reference="PO-0001", supplier_id=supplier_id
            )
            db.commit()
            po_id = po.id
        finally:
            db.close()

        listing = client.get("/api/purchase-orders", headers=roles["comptable"])
        assert listing.status_code == 200, listing.text
        detail = client.get(f"/api/purchase-orders/{po_id}", headers=roles["comptable"])
        assert detail.status_code == 200, detail.text
        lines = client.get(f"/api/purchase-orders/{po_id}/lines", headers=roles["comptable"])
        assert lines.status_code == 200, lines.text


# --------------------------------------------------------------------------
# Confirmation acheteur / relances / dépôt batch


class TestBuyerConfirmation:
    def test_confirm_resolves_anomalies_and_traces(self, client, engine) -> None:
        from app.repositories import AnomalyRepository, InvoiceLineRepository

        roles = _register_roles(client)
        buyer_headers = roles["acheteur"]
        _, invoice_id = _make_supplier_invoice(engine, status="À vérifier")
        db = sessionmaker(bind=engine)()
        try:
            InvoiceLineRepository(db).create(
                invoice_id=invoice_id, line_number=1, description="Câble HDMI",
                product_ref="CBL-001", quantity=2, unit_price="8.5",
            )
            anomaly = AnomalyRepository(db).create(
                invoice_id=invoice_id, category=AnomalyCategory.QUANTITY,
                severity=AnomalySeverity.WARNING, message="Quantité différente.",
            )
            db.commit()
            anomaly_id = anomaly.id
        finally:
            db.close()

        resp = client.post(
            f"/api/invoices/{invoice_id}/confirm",
            json={"lines": [{"line_number": 1, "quantity": "10"}]},
            headers=buyer_headers,
        )
        assert resp.status_code == 200, resp.text

        # L'anomalie est résolue (vue comptable/acheteur: INVOICE_READ).
        anomaly = client.get(
            "/api/anomalies?resolved=true", headers=buyer_headers
        ).json()
        assert any(a["id"] == anomaly_id for a in anomaly["items"])

        # L'audit trace la confirmation (JOURNAL_READ : comptable).
        logs = client.get(
            f"/api/invoices/{invoice_id}/audit-logs", headers=roles["comptable"]
        )
        actions = [e["action"] for e in logs.json()["items"]]
        assert AuditAction.CONFIRMED.value in actions


class TestRetry:
    def test_retry_requires_system_error(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        _, invoice_id = _make_supplier_invoice(engine, status="Déposée")
        resp = client.post(f"/api/invoices/{invoice_id}/retry", headers=headers)
        assert resp.status_code == 409, resp.text

    def test_retry_logs_audit(self, client, engine) -> None:
        headers = _register_roles(client)["comptable"]
        _, invoice_id = _make_supplier_invoice(engine, status="Erreur système")
        db = sessionmaker(bind=engine)()
        try:
            from app.repositories import InvoiceRepository

            from app.models.enums import InvoiceStatus

            inv = InvoiceRepository(db).get(invoice_id)
            InvoiceRepository(db).update(inv, error_message="Echec précédent")
            db.commit()
        finally:
            db.close()

        resp = client.post(f"/api/invoices/{invoice_id}/retry", headers=headers)
        assert resp.status_code == 200, resp.text

        logs = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers).json()
        assert logs["items"][0]["action"] == AuditAction.REPROCESSED.value

    def test_retry_requires_deposit_permission(self, client, engine) -> None:
        headers = _register_roles(client)["acheteur"]
        _, invoice_id = _make_supplier_invoice(engine, status="Erreur système")
        resp = client.post(f"/api/invoices/{invoice_id}/retry", headers=headers)
        assert resp.status_code == 403, resp.text


class TestBatchDeposit:
    def test_batch_deposit_multiple_files(self, client, engine, tmp_path) -> None:
        from app.api.deps import get_storage
        from app.storage.local import LocalStorage

        client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
        headers = _register_roles(client)["comptable"]
        supplier_id, _ = _make_supplier_invoice(engine, status="Déposée")

        resp = client.post(
            "/api/invoices/batch",
            files=[
                ("files", ("a.png", _png(), "image/png")),
                ("files", ("b.png", _png(), "image/png")),
            ],
            data={
                "invoice_numbers": ["BATCH-001", "BATCH-002"],
                "supplier_ids": [str(supplier_id), str(supplier_id)],
            },
            headers=headers,
        )
        client.app.dependency_overrides.clear()

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["total"] == 2
        assert all(item["invoice"] is not None for item in body["items"])

    def test_batch_mismatched_lengths_409(self, client, engine, tmp_path) -> None:
        from app.api.deps import get_storage
        from app.storage.local import LocalStorage

        client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
        headers = _register_roles(client)["comptable"]
        supplier_id, _ = _make_supplier_invoice(engine, status="Déposée")

        resp = client.post(
            "/api/invoices/batch",
            files=[("files", ("a.png", _png(), "image/png"))],
            data={
                "invoice_numbers": ["BATCH-001", "BATCH-002"],
                "supplier_ids": [str(supplier_id)],
            },
            headers=headers,
        )
        client.app.dependency_overrides.clear()
        assert resp.status_code == 409, resp.text