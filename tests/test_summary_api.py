"""Tests d'intégration de l'API « tableau de bord » (phase 8 - synthèse).

Couvre le endpoint ``GET /api/invoices/summary`` : comptage par statut et
remontée des anomalies non résolues, ainsi que l'authentification.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.enums import AnomalyCategory, AnomalySeverity, InvoiceStatus


def _create_fixture(engine) -> tuple[int, int]:
    """Crée un fournisseur, trois factures de statuts variés et une anomalie.

    Retourne ``(supplier_id, invoice_id)`` de la facture « À vérifier ».
    """
    from tests.conftest import make_invoice, make_supplier
    from app.repositories import AnomalyRepository

    session = sessionmaker(bind=engine)()
    try:
        supplier = make_supplier(session, odoo_id=7, name="ACME SAS")
        invoice_review = make_invoice(
            session, supplier.id, invoice_number="FAC-2026-001", status="À vérifier"
        )
        make_invoice(
            session, supplier.id, invoice_number="FAC-2026-002", status="Validée"
        )
        make_invoice(
            session, supplier.id, invoice_number="FAC-2026-003", status="Déposée"
        )
        AnomalyRepository(session).create(
            invoice_id=invoice_review.id,
            category=AnomalyCategory.QUANTITY,
            severity=AnomalySeverity.WARNING,
            message="Quantité différente du bon de commande.",
            expected_value="10",
            actual_value="8",
        )
        session.commit()
        return supplier.id, invoice_review.id
    finally:
        session.close()


def _register_accountant(client) -> dict[str, str]:
    from tests.conftest import auth_headers, register_user

    register_user(client, username="comptable", email="comptable@example.com")
    return auth_headers(client, "comptable")


class TestSummary:
    def test_summary_counts_by_status(self, client, engine) -> None:
        headers = _register_accountant(client)
        supplier_id, _ = _create_fixture(engine)

        response = client.get("/api/invoices/summary", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["by_status"]["Déposée"] == 1
        assert body["by_status"]["À vérifier"] == 1
        assert body["by_status"]["Validée"] == 1
        # Les autres statuts n'ont aucune facture.
        assert body["by_status"]["Rejetée"] == 0
        assert body["by_status"]["Vendor Bill créée"] == 0

    def test_summary_lists_pending_anomalies(self, client, engine) -> None:
        headers = _register_accountant(client)
        _, invoice_id = _create_fixture(engine)

        response = client.get("/api/invoices/summary", headers=headers)

        assert response.status_code == 200, response.text
        anomalies = response.json()["pending_anomalies"]
        assert len(anomalies) == 1
        assert anomalies[0]["invoice_id"] == invoice_id
        assert anomalies[0]["invoice_number"] == "FAC-2026-001"
        assert anomalies[0]["supplier_name"] == "ACME SAS"
        assert anomalies[0]["category"] == "quantite"
        assert anomalies[0]["severity"] == "warning"

    def test_summary_requires_authentication(self, client, engine) -> None:
        response = client.get("/api/invoices/summary")
        assert response.status_code == 401

    def test_summary_readable_by_buyer(self, client, engine) -> None:
        from tests.conftest import auth_headers, register_user

        register_user(client, username="acheteur", email="acheteur@example.com")
        response = client.get(
            "/api/invoices/summary", headers=auth_headers(client, "acheteur")
        )
        assert response.status_code == 200, response.text
