"""Tests des modèles SQLAlchemy : enregistrement, valeurs de statut,
contraintes d'unicité, checks et intégrité référentielle."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models.anomaly import Anomaly
from app.models.enums import (
    AnomalyCategory,
    AnomalySeverity,
    InvoiceStatus,
    UserRole,
)
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.supplier import Supplier
from app.models.user import User

from tests.conftest import make_invoice, make_supplier


EXPECTED_TABLES = {
    "users",
    "suppliers",
    "purchase_orders",
    "purchase_order_lines",
    "invoices",
    "invoice_lines",
    "anomalies",
    "audit_logs",
    "refresh_tokens",
}


class TestSchema:
    def test_all_models_are_registered(self) -> None:
        assert EXPECTED_TABLES == {
            name for name in Base.metadata.tables if name != "alembic_version"
        }

    def test_foreign_keys_referential_integrity(self) -> None:
        assert Invoice.__table__.foreign_keys.__len__() == 2
        assert InvoiceLine.__table__.foreign_keys.__len__() == 1
        assert Anomaly.__table__.foreign_keys.__len__() == 1
        assert PurchaseOrder.__table__.foreign_keys.__len__() == 1
        assert PurchaseOrderLine.__table__.foreign_keys.__len__() == 1


class TestInvoiceStatus:
    def test_status_values_are_exact(self) -> None:
        expected = [
            "Déposée",
            "En cours d'analyse",
            "À vérifier",
            "Validée",
            "Vendor Bill créée",
            "Rejetée",
            "Erreur système",
        ]
        assert [s.value for s in InvoiceStatus] == expected

    def test_default_status_is_submitted(self, session) -> None:
        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        session.commit()
        assert invoice.status is InvoiceStatus.SUBMITTED
        assert invoice.status.value == "Déposée"


class TestConstraints:
    def test_duplicate_supplier_invoice_number_rejected(self, session) -> None:
        supplier = make_supplier(session)
        make_invoice(session, supplier.id, invoice_number="FAC-001")
        session.commit()

        with pytest.raises(IntegrityError):
            make_invoice(session, supplier.id, invoice_number="FAC-001")
            session.commit()

    def test_same_number_different_supplier_allowed(self, session) -> None:
        supplier_a = make_supplier(session, odoo_id=1, name="A")
        supplier_b = make_supplier(session, odoo_id=2, name="B")
        make_invoice(session, supplier_a.id, invoice_number="FAC-001")
        make_invoice(session, supplier_b.id, invoice_number="FAC-001")
        session.commit()

    def test_invalid_status_rejected_by_db_check(self, session) -> None:
        supplier = make_supplier(session)
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO invoices (invoice_number, supplier_id, status) "
                    "VALUES (:num, :sid, :status)"
                ),
                {"num": "X", "sid": supplier.id, "status": "statut-invalide"},
            )
            session.commit()

    def test_ocr_score_range_enforced(self, session) -> None:
        supplier = make_supplier(session)
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO invoices (invoice_number, supplier_id, status, "
                    "ocr_confidence_score) VALUES (:num, :sid, :status, :score)"
                ),
                {"num": "X", "sid": supplier.id, "status": "Déposée", "score": 1.5},
            )
            session.commit()

    def test_duplicate_username_rejected(self, session) -> None:
        from app.repositories import UserRepository

        repo = UserRepository(session)
        repo.create(username="dup", email="a@x.io", hashed_password="x")
        session.commit()
        with pytest.raises(IntegrityError):
            repo.create(username="dup", email="b@x.io", hashed_password="x")
            session.commit()

    def test_duplicate_email_rejected(self, session) -> None:
        from app.repositories import UserRepository

        repo = UserRepository(session)
        repo.create(username="a", email="same@x.io", hashed_password="x")
        session.commit()
        with pytest.raises(IntegrityError):
            repo.create(username="b", email="same@x.io", hashed_password="x")
            session.commit()

    def test_duplicate_purchase_order_reference_rejected(self, session) -> None:
        from app.repositories import PurchaseOrderRepository

        supplier = make_supplier(session)
        repo = PurchaseOrderRepository(session)
        repo.create(odoo_id=10, reference="PO0001", supplier_id=supplier.id)
        session.commit()
        with pytest.raises(IntegrityError):
            repo.create(odoo_id=11, reference="PO0001", supplier_id=supplier.id)
            session.commit()

    def test_duplicate_invoice_line_number_rejected(self, session) -> None:
        from app.repositories import InvoiceLineRepository

        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        repo = InvoiceLineRepository(session)
        repo.create(invoice_id=invoice.id, line_number=1, description="Widget")
        session.commit()
        with pytest.raises(IntegrityError):
            repo.create(invoice_id=invoice.id, line_number=1, description="Autre")
            session.commit()


class TestIntegrity:
    def test_delete_invoice_cascades_to_lines_and_anomalies(self, session) -> None:
        from app.repositories import AnomalyRepository, InvoiceLineRepository

        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        invoice_id = invoice.id
        InvoiceLineRepository(session).create(
            invoice_id=invoice_id, line_number=1, description="Widget"
        )
        AnomalyRepository(session).create(
            invoice_id=invoice_id,
            category=AnomalyCategory.DUPLICATE,
            message="doublon",
        )
        session.commit()

        session.delete(invoice)
        session.commit()

        assert InvoiceLineRepository(session).list_by_invoice(invoice_id) == []
        assert AnomalyRepository(session).list_by_invoice(invoice_id) == []

    def test_delete_supplier_with_invoices_rejected(self, session) -> None:
        supplier = make_supplier(session)
        make_invoice(session, supplier.id)
        session.commit()
        with pytest.raises(IntegrityError):
            session.delete(supplier)
            session.commit()


class TestEnumsDefaults:
    def test_user_role_default(self, session) -> None:
        from app.repositories import UserRepository

        user = UserRepository(session).create(
            username="u1", email="u1@x.io", hashed_password="x"
        )
        session.commit()
        assert user.role is UserRole.ACCOUNTANT

    def test_anomaly_severity_default(self, session) -> None:
        from app.repositories import AnomalyRepository

        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        anomaly = AnomalyRepository(session).create(
            invoice_id=invoice.id,
            category=AnomalyCategory.AMOUNT,
            message="écart de montant",
        )
        session.commit()
        assert anomaly.severity is AnomalySeverity.WARNING
