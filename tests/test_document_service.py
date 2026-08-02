"""Tests unitaires du service de validation des documents (phase 3).

Couvre : détection du format par signatures binaires, rejet des documents
corrompus / non supportés / trop lourds, et graph des transitions de statut.
"""

from __future__ import annotations

import io

import pytest

from app.core.exceptions import InvalidDocumentError
from app.models.enums import InvoiceStatus
from app.services.document_service import DocumentValidator
from app.services.invoice_service import VALID_TRANSITIONS, InvoiceService


def make_pdf() -> bytes:
    """Génère un PDF minimal valide (1 page) via pypdfium2."""
    import pypdfium2 as pdfium

    buf = io.BytesIO()
    doc = pdfium.PdfDocument.new()
    doc.new_page(width=612, height=792)
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def make_image(fmt: str) -> bytes:
    """Génère une image valide (JPEG ou PNG) via Pillow."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format=fmt)
    return buf.getvalue()


class _FakeStorage:
    """Stockage de bouchon : aucune persistance réelle n'est requise."""

    def save(self, content: bytes, *, suffix: str) -> str:
        return "invoices/2026/08/fake" + suffix

    def open(self, relative_path: str) -> bytes:
        raise NotImplementedError

    def exists(self, relative_path: str) -> bool:
        return True

    def delete(self, relative_path: str) -> None:
        return None

    def path(self, relative_path: str):
        raise NotImplementedError


def _make_supplier(session):
    from tests.conftest import make_supplier

    return make_supplier(session, odoo_id=1, name="ACME SAS")


class TestDocumentValidator:
    def test_accepts_pdf(self) -> None:
        suffix, mime = DocumentValidator().validate("facture.pdf", make_pdf())
        assert (suffix, mime) == (".pdf", "application/pdf")

    def test_accepts_jpeg(self) -> None:
        suffix, mime = DocumentValidator().validate("facture.jpg", make_image("JPEG"))
        assert (suffix, mime) == (".jpg", "image/jpeg")

    def test_accepts_png(self) -> None:
        suffix, mime = DocumentValidator().validate("facture.png", make_image("PNG"))
        assert (suffix, mime) == (".png", "image/png")

    def test_detects_format_by_content_not_extension(self) -> None:
        # Un PDF renommé en .png doit être détecté comme PDF.
        suffix, _ = DocumentValidator().validate("trompeur.png", make_pdf())
        assert suffix == ".pdf"

    def test_rejects_empty_document(self) -> None:
        with pytest.raises(InvalidDocumentError):
            DocumentValidator().validate("vide.pdf", b"")

    def test_rejects_unsupported_format(self) -> None:
        with pytest.raises(InvalidDocumentError, match="non supporté"):
            DocumentValidator().validate("notes.txt", b"pas une facture")

    def test_rejects_corrupt_pdf(self) -> None:
        corrupt = b"%PDF-1.4\n%%EOF"
        with pytest.raises(InvalidDocumentError, match="corrompu|illisible"):
            DocumentValidator().validate("casse.pdf", corrupt)

    def test_rejects_truncated_pdf(self) -> None:
        truncated = make_pdf()[:60]
        with pytest.raises(InvalidDocumentError):
            DocumentValidator().validate("tronque.pdf", truncated)

    def test_rejects_corrupt_image(self) -> None:
        corrupt = b"\xff\xd8\xff\xe0" + b"\x00" * 8
        with pytest.raises(InvalidDocumentError):
            DocumentValidator().validate("casse.jpg", corrupt)

    def test_rejects_oversized_document(self, monkeypatch) -> None:
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0.0005)
        with pytest.raises(InvalidDocumentError, match="taille maximale"):
            DocumentValidator().validate("gros.pdf", make_pdf())


class TestStatusTransitions:
    def test_forward_chain_is_valid(self, session) -> None:
        """Déposée → En cours d'analyse → À vérifier → Validée → Vendor Bill."""
        supplier = _make_supplier(session)
        service = InvoiceService(session, _FakeStorage())
        invoice = service.deposit(
            filename="f.pdf", content=make_pdf(),
            invoice_number="F-1", supplier_id=supplier.id,
        )
        for expected in (
            InvoiceStatus.ANALYZING,
            InvoiceStatus.TO_REVIEW,
            InvoiceStatus.VALIDATED,
            InvoiceStatus.VENDOR_BILL_CREATED,
        ):
            service.transition_status(invoice, expected)
            assert invoice.status is expected

    def test_rejection_is_valid_and_stores_reason(self, session) -> None:
        supplier = _make_supplier(session)
        service = InvoiceService(session, _FakeStorage())
        invoice = service.deposit(
            filename="f.pdf", content=make_pdf(),
            invoice_number="F-2", supplier_id=supplier.id,
        )
        service.transition_status(invoice, InvoiceStatus.ANALYZING)
        service.transition_status(invoice, InvoiceStatus.TO_REVIEW)
        service.transition_status(
            invoice, InvoiceStatus.REJECTED, reason="Doublon"
        )
        assert invoice.status is InvoiceStatus.REJECTED
        assert invoice.rejection_reason == "Doublon"

    def test_system_error_reachable_from_any_stage(self) -> None:
        for state in InvoiceStatus:
            if state is not InvoiceStatus.SYSTEM_ERROR:
                assert (
                    InvoiceStatus.SYSTEM_ERROR in VALID_TRANSITIONS[state]
                ), state

    def test_system_error_recovers_to_submitted(self) -> None:
        assert VALID_TRANSITIONS[InvoiceStatus.SYSTEM_ERROR] == {
            InvoiceStatus.SUBMITTED
        }

    def test_invalid_skip_transition_rejected(self, session) -> None:
        from app.core.exceptions import InvalidStatusTransitionError

        supplier = _make_supplier(session)
        service = InvoiceService(session, _FakeStorage())
        invoice = service.deposit(
            filename="f.pdf", content=make_pdf(),
            invoice_number="F-3", supplier_id=supplier.id,
        )
        with pytest.raises(InvalidStatusTransitionError):
            service.transition_status(invoice, InvoiceStatus.TO_REVIEW)

    def test_terminal_states_have_no_forward(self) -> None:
        assert VALID_TRANSITIONS[InvoiceStatus.VENDOR_BILL_CREATED] == {
            InvoiceStatus.SYSTEM_ERROR
        }
        assert VALID_TRANSITIONS[InvoiceStatus.REJECTED] == {
            InvoiceStatus.SYSTEM_ERROR
        }
