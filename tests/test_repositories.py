"""Tests des repositories : CRUD, détection de doublons et filtres métier."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import (
    AnomalyCategory,
    AuditAction,
    InvoiceStatus,
)
from app.models.refresh_token import RefreshToken
from app.repositories import (
    AnomalyRepository,
    AuditLogRepository,
    InvoiceLineRepository,
    InvoiceRepository,
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
    RefreshTokenRepository,
    SupplierRepository,
    UserRepository,
)

from tests.conftest import make_invoice, make_supplier


class TestBaseRepository:
    def test_list_paginated(self, session) -> None:
        repo = UserRepository(session)
        for i in range(5):
            repo.create(username=f"u{i}", email=f"u{i}@x.io", hashed_password="x")
        session.commit()

        assert len(repo.list(limit=2, offset=0)) == 2
        assert len(repo.list(limit=2, offset=2)) == 2
        assert len(repo.list(limit=2, offset=4)) == 1

    def test_count(self, session) -> None:
        repo = UserRepository(session)
        assert repo.count() == 0
        repo.create(username="a", email="a@x.io", hashed_password="x")
        session.commit()
        assert repo.count() == 1


class TestUserRepository:
    def test_create_and_get(self, session) -> None:
        repo = UserRepository(session)
        user = repo.create(
            username="salim",
            email="salim@x.io",
            hashed_password="hashed",
            full_name="Salim",
        )
        session.commit()
        assert repo.get(user.id) is user
        assert repo.get_by_username("salim") is user
        assert repo.get_by_email("salim@x.io") is user
        assert repo.get_by_username("inconnu") is None

    def test_update_and_delete(self, session) -> None:
        repo = UserRepository(session)
        user = repo.create(username="a", email="a@x.io", hashed_password="x")
        session.commit()
        repo.update(user, full_name="Alpha", is_active=False)
        session.commit()
        session.refresh(user)
        assert user.full_name == "Alpha"
        assert user.is_active is False

        repo.delete(user)
        session.commit()
        assert repo.get(user.id) is None

    def test_list_active(self, session) -> None:
        repo = UserRepository(session)
        repo.create(username="a", email="a@x.io", hashed_password="x")
        repo.create(
            username="b", email="b@x.io", hashed_password="x", is_active=False
        )
        session.commit()
        assert {u.username for u in repo.list_active()} == {"a"}

    def test_filter_by_active(self, session) -> None:
        repo = UserRepository(session)
        repo.create(username="a", email="a@x.io", hashed_password="x")
        repo.create(
            username="b", email="b@x.io", hashed_password="x", is_active=False
        )
        session.commit()

        assert {u.username for u in repo.filter(active=True)} == {"a"}
        assert {u.username for u in repo.filter(active=False)} == {"b"}
        assert len(repo.filter()) == 2
        assert len(repo.filter(limit=1)) == 1


class TestSupplierRepository:
    def test_create_and_lookup(self, session) -> None:
        repo = SupplierRepository(session)
        supplier = repo.create(odoo_id=42, name="ACME", vat="FR12345678901")
        session.commit()
        assert repo.get_by_odoo_id(42) is supplier
        assert repo.get_by_vat("FR12345678901") is supplier
        assert repo.get_by_odoo_id(999) is None

    def test_search_by_name_is_case_insensitive(self, session) -> None:
        repo = SupplierRepository(session)
        repo.create(odoo_id=1, name="Acme Industrie")
        repo.create(odoo_id=2, name="Beta SARL")
        session.commit()
        names = [s.name for s in repo.search_by_name("acme")]
        assert names == ["Acme Industrie"]

    def test_unique_odoo_id(self, session) -> None:
        repo = SupplierRepository(session)
        repo.create(odoo_id=1, name="A")
        session.commit()
        with pytest.raises(IntegrityError):
            repo.create(odoo_id=1, name="B")
            session.commit()


class TestPurchaseOrderRepository:
    def test_create_and_lookup(self, session) -> None:
        supplier = make_supplier(session)
        repo = PurchaseOrderRepository(session)
        po = repo.create(
            odoo_id=100,
            reference="PO-2026-001",
            supplier_id=supplier.id,
            date_order=date(2026, 1, 10),
            total_amount="1500.00",
        )
        session.commit()
        assert repo.get_by_reference("PO-2026-001") is po
        assert repo.get_by_odoo_id(100) is po
        assert repo.get_by_reference("PO-0000") is None

    def test_list_by_supplier(self, session) -> None:
        supplier_a = make_supplier(session, odoo_id=1, name="A")
        supplier_b = make_supplier(session, odoo_id=2, name="B")
        repo = PurchaseOrderRepository(session)
        repo.create(odoo_id=1, reference="PO-A1", supplier_id=supplier_a.id)
        repo.create(odoo_id=2, reference="PO-A2", supplier_id=supplier_a.id)
        repo.create(odoo_id=3, reference="PO-B1", supplier_id=supplier_b.id)
        session.commit()
        refs = [po.reference for po in repo.list_by_supplier(supplier_a.id)]
        assert refs == ["PO-A1", "PO-A2"]


class TestPurchaseOrderLineRepository:
    def test_create_and_list_ordered(self, session) -> None:
        supplier = make_supplier(session)
        po = PurchaseOrderRepository(session).create(
            odoo_id=100, reference="PO-001", supplier_id=supplier.id
        )
        repo = PurchaseOrderLineRepository(session)
        repo.create(
            purchase_order_id=po.id, odoo_id=2, line_number=20,
            product_ref="B", quantity="2.0",
        )
        repo.create(
            purchase_order_id=po.id, odoo_id=1, line_number=10,
            product_ref="A", quantity="1.0",
        )
        session.commit()

        lines = repo.list_by_purchase_order(po.id)
        assert [line.line_number for line in lines] == [10, 20]
        assert repo.get_by_odoo_id(1) is lines[0]
        assert repo.get_by_odoo_id(999) is None


class TestInvoiceRepository:
    def test_crud(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        invoice = repo.create(
            invoice_number="FAC-001",
            supplier_id=supplier.id,
            total_incl_tax="125.50",
        )
        session.commit()

        assert repo.get(invoice.id) is invoice

        repo.update(invoice, status=InvoiceStatus.VALIDATED, matching_score=0.95)
        session.commit()
        session.refresh(invoice)
        assert invoice.status is InvoiceStatus.VALIDATED
        assert invoice.matching_score == 0.95

        repo.delete(invoice)
        session.commit()
        assert repo.get(invoice.id) is None

    def test_duplicate_detection(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        repo.create(invoice_number="FAC-001", supplier_id=supplier.id)
        session.commit()

        assert repo.exists_duplicate(supplier.id, "FAC-001") is True
        assert repo.get_by_supplier_and_number(supplier.id, "FAC-001") is not None
        assert repo.exists_duplicate(supplier.id, "FAC-002") is False

    def test_filter_by_status(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        repo.create(invoice_number="F-1", supplier_id=supplier.id)
        repo.create(
            invoice_number="F-2",
            supplier_id=supplier.id,
            status=InvoiceStatus.TO_REVIEW,
        )
        session.commit()

        submitted = repo.list_by_status(InvoiceStatus.SUBMITTED)
        assert [i.invoice_number for i in submitted] == ["F-1"]

    def test_filter_by_supplier(self, session) -> None:
        supplier_a = make_supplier(session, odoo_id=1, name="A")
        supplier_b = make_supplier(session, odoo_id=2, name="B")
        repo = InvoiceRepository(session)
        repo.create(invoice_number="F-A1", supplier_id=supplier_a.id)
        repo.create(invoice_number="F-B1", supplier_id=supplier_b.id)
        session.commit()

        result = repo.list_by_supplier(supplier_a.id)
        assert [i.invoice_number for i in result] == ["F-A1"]

    def test_filter_by_date_range(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        repo.create(
            invoice_number="Jan", supplier_id=supplier.id,
            issue_date=date(2026, 1, 15),
        )
        repo.create(
            invoice_number="Fev", supplier_id=supplier.id,
            issue_date=date(2026, 2, 20),
        )
        session.commit()

        result = repo.list_by_date_range(date(2026, 1, 1), date(2026, 1, 31))
        assert [i.invoice_number for i in result] == ["Jan"]
        assert repo.list_by_date_range(date(2026, 3, 1), date(2026, 3, 31)) == []

        assert repo.count(
            issue_date_from=date(2026, 1, 1), issue_date_to=date(2026, 1, 31)
        ) == 1
        assert repo.count(issue_date_from=date(2026, 3, 1)) == 0

    def test_filter_combined(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        repo.create(
            invoice_number="A-ok", supplier_id=supplier.id,
            status=InvoiceStatus.VALIDATED, issue_date=date(2026, 1, 5),
        )
        repo.create(
            invoice_number="A-ko", supplier_id=supplier.id,
            status=InvoiceStatus.TO_REVIEW, issue_date=date(2026, 1, 6),
        )
        repo.create(
            invoice_number="B-ok", supplier_id=supplier.id,
            status=InvoiceStatus.VALIDATED, issue_date=date(2026, 2, 1),
        )
        session.commit()

        result = repo.filter(
            status=InvoiceStatus.VALIDATED,
            supplier_id=supplier.id,
            issue_date_from=date(2026, 1, 1),
            issue_date_to=date(2026, 1, 31),
        )
        assert [i.invoice_number for i in result] == ["A-ok"]
        assert repo.count(status=InvoiceStatus.VALIDATED, supplier_id=supplier.id) == 2

    def test_filter_pagination(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        for i in range(5):
            repo.create(invoice_number=f"F-{i}", supplier_id=supplier.id)
        session.commit()

        page = repo.filter(limit=2, offset=0)
        assert len(page) == 2
        assert repo.count() == 5

    def test_filter_by_created_at(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        repo.create(invoice_number="F-1", supplier_id=supplier.id)
        repo.create(invoice_number="F-2", supplier_id=supplier.id)
        session.commit()

        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        later = datetime(2099, 1, 1, tzinfo=timezone.utc)
        assert len(repo.filter(created_from=past)) >= 2
        assert len(repo.filter(created_to=later)) >= 2
        assert len(repo.filter(created_from=later)) == 0
        assert repo.count(created_from=past) >= 2
        assert repo.count(created_to=later) >= 2
        assert repo.count(created_from=later) == 0

    def test_find_other_with_supplier_number(self, session) -> None:
        supplier = make_supplier(session)
        repo = InvoiceRepository(session)
        first = repo.create(invoice_number="FAC-001", supplier_id=supplier.id)
        second = repo.create(invoice_number="FAC-002", supplier_id=supplier.id)
        session.commit()

        assert repo.find_other_with_supplier_number(
            first.id, supplier.id, "FAC-001"
        ) is None
        assert repo.find_other_with_supplier_number(
            second.id, supplier.id, "FAC-001"
        ) is first


class TestInvoiceLineRepository:
    def test_create_and_list_ordered(self, session) -> None:
        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        repo = InvoiceLineRepository(session)
        repo.create(invoice_id=invoice.id, line_number=2, description="Second")
        repo.create(invoice_id=invoice.id, line_number=1, description="Premier")
        session.commit()

        lines = repo.list_by_invoice(invoice.id)
        assert [line.line_number for line in lines] == [1, 2]


class TestAnomalyRepository:
    def test_create_list_and_resolve(self, session) -> None:
        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        repo = AnomalyRepository(session)
        anomaly = repo.create(
            invoice_id=invoice.id,
            category=AnomalyCategory.QUANTITY,
            message="quantité en écart",
            expected_value="10",
            actual_value="8",
        )
        session.commit()

        assert repo.list_by_invoice(invoice.id) == [anomaly]
        assert repo.list_unresolved() == [anomaly]

        repo.resolve(anomaly)
        session.commit()
        assert anomaly.resolved is True
        assert anomaly.resolved_at is not None
        assert repo.list_unresolved() == []


class TestAuditLogRepository:
    def test_create_list_and_recent(self, session) -> None:
        supplier = make_supplier(session)
        invoice = make_invoice(session, supplier.id)
        repo = AuditLogRepository(session)
        repo.create(
            invoice_id=invoice.id,
            user_id=None,
            action=AuditAction.CORRECTED,
            message="Facture créée",
        )
        repo.create(
            invoice_id=invoice.id,
            user_id=None,
            action=AuditAction.VALIDATED,
            message="Validée",
            details={"champ": "valeur"},
        )
        session.commit()

        entries = repo.list_by_invoice(invoice.id)
        assert [e.action for e in entries] == [
            AuditAction.VALIDATED,
            AuditAction.CORRECTED,
        ]
        assert entries[0].details == {"champ": "valeur"}

        recent = repo.list_recent(limit=1)
        assert len(recent) == 1
        assert recent[0].action in {
            AuditAction.VALIDATED,
            AuditAction.CORRECTED,
        }

        all_recent = repo.list_recent()
        assert len(all_recent) == 2
        assert {e.action for e in all_recent} == {
            AuditAction.VALIDATED,
            AuditAction.CORRECTED,
        }


class TestRefreshTokenRepository:
    def _token(self, repo, user_id: int, *, token_hash="h1", jti="j1"):
        return repo.create(
            user_id=user_id,
            token_hash=token_hash,
            jti=jti,
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )

    def test_create_and_lookups(self, session) -> None:
        user = UserRepository(session).create(
            username="salim", email="salim@x.io", hashed_password="hashed"
        )
        session.commit()
        repo = RefreshTokenRepository(session)
        token = self._token(repo, user.id)
        session.commit()

        assert repo.get(token.id) is token
        assert isinstance(token, RefreshToken)
        assert repo.get_by_token_hash("h1") is token
        assert repo.get_by_jti("j1") is token
        assert repo.get_by_token_hash("inconnu") is None
        assert repo.get_by_jti("inconnu") is None

    def test_revoke_and_list_active(self, session) -> None:
        user = UserRepository(session).create(
            username="salim", email="salim@x.io", hashed_password="hashed"
        )
        session.commit()
        repo = RefreshTokenRepository(session)
        first = self._token(repo, user.id, token_hash="h1", jti="j1")
        self._token(repo, user.id, token_hash="h2", jti="j2")
        session.commit()

        assert len(repo.list_active_for_user(user.id)) == 2

        repo.revoke(first)
        session.commit()
        assert first.revoked_at is not None
        assert len(repo.list_active_for_user(user.id)) == 1

    def test_revoke_all_for_user(self, session) -> None:
        user = UserRepository(session).create(
            username="salim", email="salim@x.io", hashed_password="hashed"
        )
        session.commit()
        repo = RefreshTokenRepository(session)
        self._token(repo, user.id, token_hash="h1", jti="j1")
        self._token(repo, user.id, token_hash="h2", jti="j2")
        session.commit()

        revoked = repo.revoke_all_for_user(user.id)
        session.commit()

        assert revoked == 2
        assert repo.list_active_for_user(user.id) == []
        assert repo.revoke_all_for_user(user.id) == 0
