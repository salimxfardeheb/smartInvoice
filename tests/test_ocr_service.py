"""Tests unitaires du service OCR (phase 4).

Couvre le pipeline complet sur une base SQLite en mémoire et un stockage
local temporaire : extraction/persistance, document illisible, confiance
faible, fichier manquant, transition invalide et reprise après erreur.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import InvalidStatusTransitionError
from app.models.enums import AnomalySeverity, InvoiceStatus
from app.repositories import (
    AnomalyRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from app.services.invoice_service import InvoiceService
from app.services.ocr_service import OcrService
from app.storage.local import LocalStorage
from tests.conftest import make_supplier
from tests.ocr_fakes import (
    fake_engine_empty,
    fake_engine_low_confidence,
    fake_engine_ok,
    make_pdf_bytes,
)


@pytest.fixture()
def storage(tmp_path) -> LocalStorage:
    """Stockage local temporaire par test."""
    return LocalStorage(tmp_path)


@pytest.fixture()
def service(session, storage) -> OcrService:
    """Service OCR branché sur la session et le stockage de test."""
    return OcrService(session, storage)


def _deposit(service: OcrService, session, *, number: str = "FAC-OCR-001"):
    """Dépose une facture PDF et retourne l'entité."""
    supplier = make_supplier(session, odoo_id=1, name="ACME SAS")
    invoice_service = InvoiceService(session, service.storage)
    return invoice_service.deposit(
        filename="facture.pdf",
        content=make_pdf_bytes(),
        invoice_number=number,
        supplier_id=supplier.id,
    )


class TestProcess:
    def test_extracts_and_persists(self, session, service) -> None:
        invoice = _deposit(service, session)
        service.engine = fake_engine_ok()

        result = service.process(invoice)

        assert result.status is InvoiceStatus.TO_REVIEW
        assert result.ocr_confidence_score == pytest.approx(0.95, abs=1e-6)
        assert result.error_message is None

        data = result.extracted_data
        assert data["general"]["invoice_number"] == "FAC-2026-001"
        assert data["financial"]["total_incl_tax"] == "206.28"
        assert len(data["lines"]) == 3

        # Colonnes métier mises à jour.
        assert result.total_incl_tax is not None
        assert str(result.total_incl_tax) == "206.28"

        # Lignes persistées en base.
        lines = InvoiceLineRepository(session).list_by_invoice(result.id)
        assert len(lines) == 3
        assert lines[0].description == "Câble HDMI"

        # Aucune anomalie avec une confiance élevée.
        anomalies = AnomalyRepository(session).list_by_invoice(result.id)
        assert anomalies == []

    def test_illegible_document_sets_system_error(self, session, service) -> None:
        invoice = _deposit(service, session)
        service.engine = fake_engine_empty()

        result = service.process(invoice)

        assert result.status is InvoiceStatus.SYSTEM_ERROR
        assert result.error_message is not None
        assert result.ocr_confidence_score is None

    def test_low_confidence_creates_anomaly(self, session, service) -> None:
        invoice = _deposit(service, session)
        service.engine = fake_engine_low_confidence()

        result = service.process(invoice)

        assert result.status is InvoiceStatus.TO_REVIEW
        anomalies = AnomalyRepository(session).list_by_invoice(result.id)
        assert len(anomalies) == 1
        assert anomalies[0].severity is AnomalySeverity.WARNING
        assert "confiance" in anomalies[0].message

    def test_missing_file_sets_system_error(self, session, service) -> None:
        supplier = make_supplier(session, odoo_id=2, name="ACME")
        invoice = InvoiceRepository(session).create(
            invoice_number="FAC-OCR-NOFILE", supplier_id=supplier.id
        )
        service.engine = fake_engine_ok()

        result = service.process(invoice)

        assert result.status is InvoiceStatus.SYSTEM_ERROR
        assert result.error_message is not None

    def test_invalid_state_rejected(self, session, service) -> None:
        invoice = _deposit(service, session)
        invoice_service = InvoiceService(session, service.storage)
        invoice_service.transition_status(invoice, InvoiceStatus.ANALYZING)
        invoice_service.transition_status(invoice, InvoiceStatus.TO_REVIEW)

        with pytest.raises(InvalidStatusTransitionError):
            service.process(invoice)

    def test_reprocess_after_system_error(self, session, service) -> None:
        invoice = _deposit(service, session)
        service.engine = fake_engine_empty()
        service.process(invoice)
        assert invoice.status is InvoiceStatus.SYSTEM_ERROR

        service.engine = fake_engine_ok()
        result = service.process(invoice)

        assert result.status is InvoiceStatus.TO_REVIEW
        assert result.extracted_data is not None

    def test_reprocess_does_not_duplicate_lines(self, session, service) -> None:
        invoice = _deposit(service, session)
        service.engine = fake_engine_ok()
        service.process(invoice)

        invoice_service = InvoiceService(session, service.storage)
        invoice_service.transition_status(invoice, InvoiceStatus.SYSTEM_ERROR)
        service.process(invoice)

        lines = InvoiceLineRepository(session).list_by_invoice(invoice.id)
        assert len(lines) == 3
