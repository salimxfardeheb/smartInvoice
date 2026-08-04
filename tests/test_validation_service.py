"""Tests unitaires du service de validation comptable (phase 7).

Couvre : la validation, le rejet (avec motif obligatoire), la correction
manuelle (champs et lignes), la création de la Vendor Bill Odoo (succès et
échec côté Odoo) et le traçage de chaque action dans le journal d'audit.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.exceptions import (
    DuplicateInvoiceError,
    InvalidStatusTransitionError,
    OdooError,
    RejectionReasonRequiredError,
)
from app.models.enums import AuditAction, InvoiceStatus
from app.repositories import (
    AuditLogRepository,
    InvoiceLineRepository,
    InvoiceRepository,
    UserRepository,
)
from app.schemas.validation import InvoiceCorrection, InvoiceLineCorrection
from app.services.validation_service import ValidationService

from tests.conftest import make_invoice, make_supplier


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
        self.search_calls: list[tuple] = []

    def create(self, model: str, values: dict) -> int:
        self.calls.append((model, values))
        if self.error is not None:
            raise self.error
        return self.move_id

    def search_read(self, model, domain, fields, *, limit=None, offset=0) -> list[dict]:
        self.search_calls.append((model, domain, fields, limit, offset))
        return list(self.existing_moves)


def _make_user(session, *, username: str = "comptable"):
    """Crée un utilisateur comptable de test."""
    return UserRepository(session).create(
        username=username,
        email=f"{username}@x.io",
        hashed_password="hashed",
        full_name="Compta Test",
    )


def _make_invoice(
    session,
    *,
    status: InvoiceStatus = InvoiceStatus.TO_REVIEW,
    with_lines: bool = True,
    supplier=None,
    invoice_number: str = "FAC-2026-001",
):
    """Crée une facture « À vérifier » liée à un fournisseur."""
    supplier = supplier or make_supplier(session, odoo_id=42, name="ACME SAS")
    invoice = make_invoice(
        session,
        supplier.id,
        invoice_number=invoice_number,
        status=status,
        issue_date=date(2026, 1, 15),
    )
    if with_lines:
        InvoiceLineRepository(session).create(
            invoice_id=invoice.id,
            line_number=1,
            description="Câble HDMI",
            product_ref="CBL-001",
            quantity="10.0",
            unit_price="8.50",
            amount="85.00",
        )
        InvoiceLineRepository(session).create(
            invoice_id=invoice.id,
            line_number=2,
            description="Écran LED",
            product_ref="SCR-24",
            quantity="2.0",
            unit_price="150.00",
            amount="300.00",
        )
    session.commit()
    return invoice


def _service(session, **odoo_kwargs) -> tuple[ValidationService, FakeOdooClient]:
    """Service de validation branché sur le client Odoo bouchon."""
    fake = FakeOdooClient(**odoo_kwargs)
    return ValidationService(session, odoo_client=fake), fake


class TestValidate:
    def test_validate_success(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        result = service.validate(invoice, user)

        assert result.status is InvoiceStatus.VALIDATED

    def test_validate_traces_audit_log(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        service.validate(invoice, user)
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)

        assert len(logs) == 1
        assert logs[0].action is AuditAction.VALIDATED
        assert logs[0].user_id == user.id

    def test_validate_from_wrong_status_raises(self, session) -> None:
        invoice = _make_invoice(session, status=InvoiceStatus.SUBMITTED)
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(InvalidStatusTransitionError):
            service.validate(invoice, user)


class TestReject:
    def test_reject_success(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        result = service.reject(invoice, user, "Prix HT ne correspond pas au BC.")

        assert result.status is InvoiceStatus.REJECTED
        assert result.rejection_reason == "Prix HT ne correspond pas au BC."
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert len(logs) == 1
        assert logs[0].action is AuditAction.REJECTED

    def test_reject_requires_reason(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(RejectionReasonRequiredError):
            service.reject(invoice, user, "")

    def test_reject_whitespace_reason_raises(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(RejectionReasonRequiredError):
            service.reject(invoice, user, "   ")


class TestCorrect:
    def test_correct_fields(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        service.correct(
            invoice,
            user,
            InvoiceCorrection(
                invoice_number="FAC-2026-001-R",
                issue_date=date(2026, 2, 1),
                total_excl_tax="88.50",
            ),
        )
        session.refresh(invoice)

        assert invoice.invoice_number == "FAC-2026-001-R"
        assert invoice.issue_date == date(2026, 2, 1)
        assert invoice.total_excl_tax == 88.50
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert len(logs) == 1
        assert logs[0].action is AuditAction.CORRECTED
        assert "invoice_number" in logs[0].details
        assert logs[0].details["invoice_number"]["before"] == "FAC-2026-001"

    def test_correct_lines_sync(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        service.correct(
            invoice,
            user,
            InvoiceCorrection(
                lines=[
                    InvoiceLineCorrection(
                        line_number=1,
                        description="Câble HDMI Premium",
                        product_ref="CBL-001",
                        quantity="12.0",
                        unit_price="9.00",
                        amount="108.00",
                    ),
                    InvoiceLineCorrection(
                        line_number=3,
                        description="Adaptateur USB",
                        product_ref="USB-C",
                        quantity="5.0",
                        unit_price="3.00",
                        amount="15.00",
                    ),
                ]
            ),
        )

        lines = InvoiceLineRepository(session).list_by_invoice(invoice.id)
        by_number = {line.line_number: line for line in lines}
        # La ligne 2 a été supprimée, la ligne 1 mise à jour, la ligne 3 créée.
        assert set(by_number) == {1, 3}
        assert by_number[1].description == "Câble HDMI Premium"
        assert by_number[1].quantity == 12.0
        assert by_number[3].description == "Adaptateur USB"
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert len(logs) == 1
        assert [l["status"] for l in logs[0].details["lines"]] == [
            "modifiée",
            "créée",
            "supprimée",
        ]

    def test_correct_no_change_no_audit(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session)

        service.correct(invoice, user, InvoiceCorrection())
        assert AuditLogRepository(session).list_by_invoice(invoice.id) == []

    def test_correct_from_wrong_status_raises(self, session) -> None:
        invoice = _make_invoice(session, status=InvoiceStatus.SUBMITTED)
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(InvalidStatusTransitionError):
            service.correct(invoice, user, InvoiceCorrection(currency="USD"))

    def test_correct_duplicate_number_raises(self, session) -> None:
        supplier = make_supplier(session, odoo_id=42, name="ACME SAS")
        make_invoice(session, supplier.id, invoice_number="FAC-EXISTANT")
        invoice = _make_invoice(session, supplier=supplier)
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(DuplicateInvoiceError):
            service.correct(
                invoice, user, InvoiceCorrection(invoice_number="FAC-EXISTANT")
            )


class TestCreateVendorBill:
    def test_vendor_bill_success(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, fake = _service(session)

        # La facture doit d'abord être validée.
        service.validate(invoice, user)
        result = service.create_vendor_bill(invoice, user)

        assert result.status is InvoiceStatus.VENDOR_BILL_CREATED
        assert result.vendor_bill_id == fake.move_id

        model, values = fake.calls[0]
        assert model == "account.move"
        assert values["move_type"] == "in_invoice"
        assert values["partner_id"] == 42  # odoo_id du fournisseur
        assert values["ref"] == "FAC-2026-001"
        assert values["invoice_date"] == "2026-01-15"
        assert len(values["invoice_line_ids"]) == 2
        assert values["invoice_line_ids"][0][0] == 0
        assert values["invoice_line_ids"][0][2]["name"] == "Câble HDMI"

        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert {log.action for log in logs} == {
            AuditAction.VALIDATED,
            AuditAction.VENDOR_BILL_CREATED,
        }

    def test_vendor_bill_failure_leaves_invoice_validated(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, fake = _service(session, error=OdooError("Odoo indisponible"))

        service.validate(invoice, user)
        with pytest.raises(OdooError):
            service.create_vendor_bill(invoice, user)

        assert invoice.status is InvoiceStatus.VALIDATED
        assert invoice.vendor_bill_id is None

    def test_vendor_bill_failure_records_attempt_and_error(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, _ = _service(session, error=OdooError("timeout"))

        service.validate(invoice, user)
        with pytest.raises(OdooError):
            service.create_vendor_bill(invoice, user)
        with pytest.raises(OdooError):
            service.create_vendor_bill(invoice, user)

        assert invoice.vendor_bill_attempts == 2
        assert "timeout" in invoice.vendor_bill_error

    def test_vendor_bill_success_resets_attempts(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, fake = _service(session, error=OdooError("down"))
        service.validate(invoice, user)
        with pytest.raises(OdooError):
            service.create_vendor_bill(invoice, user)
        assert invoice.vendor_bill_attempts == 1

        # La relance finit par réussir : compteur remis à zéro, erreur effacée.
        fake.error = None
        result = service.create_vendor_bill(invoice, user)
        assert result.status is InvoiceStatus.VENDOR_BILL_CREATED
        assert invoice.vendor_bill_attempts == 0
        assert invoice.vendor_bill_error is None

    def test_vendor_bill_failure_reconciles_existing_move(self, session) -> None:
        invoice = _make_invoice(session)
        user = _make_user(session)
        service, fake = _service(
            session,
            error=OdooError("Duplicate ref"),
            existing_moves=[{"id": 7777, "ref": "FAC-2026-001"}],
        )
        service.validate(invoice, user)

        result = service.create_vendor_bill(invoice, user)

        # L'account.move Odoo déjà présente est réconciliée avec la facture.
        assert result.vendor_bill_id == 7777
        assert result.vendor_bill_attempts == 0
        assert result.vendor_bill_error is None
        assert result.status is InvoiceStatus.VALIDATED  # pas de transition forcée
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert AuditAction.VENDOR_BILL_CREATED in {log.action for log in logs}
        assert any("réconciliée" in log.message for log in logs)

    def test_vendor_bill_is_idempotent_when_already_linked(self, session) -> None:
        invoice = _make_invoice(
            session, status=InvoiceStatus.VALIDATED
        )
        invoice = InvoiceRepository(session).update(
            invoice, vendor_bill_id=1234
        )
        session.commit()
        user = _make_user(session)
        service, fake = _service(session)

        result = service.create_vendor_bill(invoice, user)

        assert result.vendor_bill_id == 1234
        # Aucun appel de création émis vers Odoo (réconciliation idempotente).
        assert fake.calls == []
        logs = AuditLogRepository(session).list_by_invoice(invoice.id)
        assert any("réconciliée" in log.message for log in logs)

    def test_vendor_bill_requires_validated_status(self, session) -> None:
        invoice = _make_invoice(session)  # À vérifier
        user = _make_user(session)
        service, _ = _service(session)

        with pytest.raises(InvalidStatusTransitionError):
            service.create_vendor_bill(invoice, user)
