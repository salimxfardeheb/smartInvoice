"""Tests unitaires du stockage local et du service factures (phase 3).

Couvre : le rejet des chemins hors racine (traversal) du stockage local, la
suppression et la résolution de chemin, et les cas d'erreur du service de
factures (fichier source manquant, nettoyage du fichier au dépôt en erreur).
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    DocumentNotFoundError,
    SupplierNotFoundError,
)
from app.services.invoice_service import InvoiceService
from app.storage.local import LocalStorage
from tests.conftest import make_supplier
from tests.ocr_fakes import make_pdf_bytes


class TestLocalStorage:
    def test_save_and_open_roundtrip(self, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        rel = storage.save(b"contenu", suffix=".pdf")
        assert rel.startswith("invoices/")
        assert rel.endswith(".pdf")
        assert storage.exists(rel)
        assert storage.open(rel) == b"contenu"

    def test_save_overwrites_same_path(self, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        first = storage.save(b"a", suffix=".txt")
        storage.save(b"b", suffix=".txt")
        assert storage.open(first) == b"a"

    def test_delete_removes_file(self, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        rel = storage.save(b"a supprimer", suffix=".txt")
        storage.delete(rel)
        assert not storage.exists(rel)

    def test_delete_missing_file_is_noop(self, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        storage.delete("invoices/2026/08/inexistant.txt")

    def test_path_resolves_under_root(self, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        rel = storage.save(b"x", suffix=".txt")
        resolved = storage.path(rel)
        assert resolved.is_file()
        assert str(resolved).startswith(str(storage.root))

    @pytest.mark.parametrize(
        "malicious",
        [
            "../escape.txt",
            "invoices/../../escape.pdf",
            "/etc/passwd",
            "invoices/2026/08/../../../../etc/passwd",
        ],
    )
    def test_path_traversal_rejected(self, tmp_path, malicious) -> None:
        storage = LocalStorage(tmp_path)
        with pytest.raises(ValueError, match="invalide"):
            storage.open(malicious)
        with pytest.raises(ValueError, match="invalide"):
            storage.exists(malicious)
        with pytest.raises(ValueError, match="invalide"):
            storage.path(malicious)
        with pytest.raises(ValueError, match="invalide"):
            storage.delete(malicious)


class TestGetSourceFile:
    def test_missing_file_path_raises(self, session, tmp_path) -> None:

        supplier = make_supplier(session, odoo_id=11, name="ACME")
        from app.repositories import InvoiceRepository

        invoice = InvoiceRepository(session).create(
            invoice_number="FAC-NOFILE", supplier_id=supplier.id
        )
        service = InvoiceService(session, LocalStorage(tmp_path))

        with pytest.raises(DocumentNotFoundError, match="associé à cette facture"):
            service.get_source_file(invoice)

    def test_missing_file_on_disk_raises(self, session, tmp_path) -> None:
        from app.repositories import InvoiceRepository

        supplier = make_supplier(session, odoo_id=12, name="ACME")
        invoice = InvoiceRepository(session).create(
            invoice_number="FAC-ABSENT",
            supplier_id=supplier.id,
            file_path="invoices/2026/08/introuvable.pdf",
        )
        service = InvoiceService(session, LocalStorage(tmp_path))

        with pytest.raises(DocumentNotFoundError, match="introuvable"):
            service.get_source_file(invoice)

    def test_returns_file_content(self, session, tmp_path) -> None:
        from app.repositories import InvoiceRepository

        storage = LocalStorage(tmp_path)
        rel = storage.save(b"source pdf", suffix=".pdf")
        supplier = make_supplier(session, odoo_id=13, name="ACME")
        invoice = InvoiceRepository(session).create(
            invoice_number="FAC-PRESENT",
            supplier_id=supplier.id,
            file_path=rel,
        )
        service = InvoiceService(session, storage)

        assert service.get_source_file(invoice) == b"source pdf"


class TestDepositCleanup:
    def test_storage_file_removed_when_invoice_creation_fails(
        self, session, tmp_path, monkeypatch
    ) -> None:
        """Le fichier est supprimé si la création en base échoue après le stockage."""
        storage = LocalStorage(tmp_path)
        supplier = make_supplier(session, odoo_id=14, name="ACME")
        service = InvoiceService(session, storage)

        saved_paths = []
        original_save = storage.save

        def _tracking_save(content, *, suffix):
            rel = original_save(content, suffix=suffix)
            saved_paths.append(rel)
            return rel

        monkeypatch.setattr(storage, "save", _tracking_save)

        def _boom(**kwargs):
            raise RuntimeError("échec base")

        # Le repository utilisé par le service est celui construit à l'init.
        monkeypatch.setattr(service.invoices, "create", _boom)

        with pytest.raises(RuntimeError, match="échec base"):
            service.deposit(
                filename="f.pdf",
                content=make_pdf_bytes(),
                invoice_number="FAC-CLEANUP",
                supplier_id=supplier.id,
            )

        assert len(saved_paths) == 1
        assert not storage.exists(saved_paths[0])

    def test_unknown_supplier_does_not_save_file(self, session, tmp_path) -> None:
        storage = LocalStorage(tmp_path)
        service = InvoiceService(session, storage)

        with pytest.raises(SupplierNotFoundError):
            service.deposit(
                filename="f.pdf",
                content=make_pdf_bytes(),
                invoice_number="FAC-404",
                supplier_id=999999,
            )

        # Aucun fichier stocké (seul le dossier racine existe).
        assert list(storage.root.rglob("*")) == []
