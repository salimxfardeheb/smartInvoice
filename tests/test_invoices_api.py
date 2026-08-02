"""Tests d'intégration de l'API « documents » (phase 3).

Couvre : dépôt (upload valide/invalide, doublon, fournisseur inconnu),
historique (tri, filtres, pagination), consultation, téléchargement du
fichier source et transitions de statut (valides / invalides).
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.enums import InvoiceStatus


def _pdf_bytes() -> bytes:
    """PDF minimal valide (1 page)."""
    import pypdfium2 as pdfium

    buf = io.BytesIO()
    doc = pdfium.PdfDocument.new()
    doc.new_page(width=612, height=792)
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def invoice_client(client, tmp_path):
    """Client de test dont le stockage pointe vers un dossier temporaire."""
    from app.storage import get_storage
    from app.storage.local import LocalStorage

    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield client
    client.app.dependency_overrides.clear()


def _create_supplier(engine, *, odoo_id: int = 1, name: str = "ACME SAS") -> int:
    """Crée un fournisseur dans la base de test et retourne son id."""
    from tests.conftest import make_supplier

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        supplier = make_supplier(session, odoo_id=odoo_id, name=name)
        session.commit()
        return supplier.id
    finally:
        session.close()


def _register_roles(client) -> dict[str, dict[str, str]]:
    """Crée admin + comptable + acheteur (rôles explicites) et retourne leurs
    en-têtes d'authentification. Le premier compte devient Administrateur.
    Idempotent : les appels répétés au sein d'un même test sont tolérés."""
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
        "admin": admin,
        "comptable": auth_headers(client, "comptable"),
        "acheteur": auth_headers(client, "acheteur"),
    }


class TestDeposit:
    def test_upload_valid_pdf(self, invoice_client, engine) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            data={
                "invoice_number": "FAC-001",
                "supplier_id": str(supplier_id),
                "issue_date": "2026-01-15",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["invoice_number"] == "FAC-001"
        assert body["supplier"]["id"] == supplier_id
        assert body["status"] == InvoiceStatus.SUBMITTED.value
        assert body["issue_date"] == "2026-01-15"
        assert body["file_info"] is not None
        assert body["file_info"]["original_filename"] == "facture.pdf"
        assert body["file_info"]["content_type"] == "application/pdf"
        assert body["file_info"]["size"] == len(_pdf_bytes())

    def test_upload_valid_jpeg(self, invoice_client, engine) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("scan.jpg", _jpeg_bytes(), "image/jpeg")},
            data={"invoice_number": "FAC-JPG", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["file_info"]["content_type"] == "image/jpeg"

    def test_upload_corrupt_document_rejected(self, invoice_client, engine) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        corrupt = b"%PDF-1.4\n%%EOF"
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("casse.pdf", corrupt, "application/pdf")},
            data={"invoice_number": "FAC-KO", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    def test_upload_unsupported_format_rejected(
        self, invoice_client, engine
    ) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("notes.txt", b"simple texte", "text/plain")},
            data={"invoice_number": "FAC-TXT", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    def test_upload_empty_document_rejected(self, invoice_client, engine) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("vide.pdf", b"", "application/pdf")},
            data={"invoice_number": "FAC-VIDE", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    def test_upload_oversized_document_rejected(
        self, invoice_client, engine, monkeypatch
    ) -> None:
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0.0005)
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("gros.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-GROS", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    def test_upload_duplicate_rejected(self, invoice_client, engine) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        payload = {
            "files": {"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            "data": {"invoice_number": "FAC-01", "supplier_id": str(supplier_id)},
            "headers": headers,
        }
        assert invoice_client.post("/api/invoices", **payload).status_code == 201
        response = invoice_client.post("/api/invoices", **payload)
        assert response.status_code == 409, response.text

    def test_upload_unknown_supplier_rejected(self, invoice_client) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-X", "supplier_id": "999999"},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    def test_upload_requires_deposit_permission(self, invoice_client, engine) -> None:
        roles = _register_roles(invoice_client)
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-P", "supplier_id": str(supplier_id)},
            headers=roles["acheteur"],
        )
        assert response.status_code == 403, response.text

    def test_upload_requires_authentication(self, invoice_client, engine) -> None:
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-A", "supplier_id": str(supplier_id)},
        )
        assert response.status_code == 401, response.text


class TestHistory:
    def _seed(self, invoice_client, engine, *, status=InvoiceStatus.SUBMITTED):
        from app.repositories import InvoiceRepository, SupplierRepository

        headers = _register_roles(invoice_client)["comptable"]
        Session = sessionmaker(bind=engine)
        session = Session()
        supplier = SupplierRepository(session).create(odoo_id=7, name="ACME SAS")
        session.commit()
        InvoiceRepository(session).create(
            invoice_number="FAC-1", supplier_id=supplier.id, status=status
        )
        session.commit()
        supplier_id = supplier.id
        session.close()
        return headers, supplier_id

    def test_list_history_with_filters(self, invoice_client, engine) -> None:
        headers, supplier_id = self._seed(invoice_client, engine)
        # Un second dépôt « Déposée » via l'API, puis transition de la première.
        invoice_client.post(
            "/api/invoices",
            files={"file": ("f.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-2", "supplier_id": str(supplier_id)},
            headers=headers,
        )
        invoice_client.post(
            "/api/invoices/1/status",
            json={"status": "En cours d'analyse"},
            headers=headers,
        )

        listed = invoice_client.get("/api/invoices", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] == 2

        filtered = invoice_client.get(
            "/api/invoices?status=Déposée", headers=headers
        )
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["invoice_number"] == "FAC-2"

    def test_list_pagination(self, invoice_client, engine) -> None:
        headers, supplier_id = self._seed(invoice_client, engine)
        for i in range(3):
            invoice_client.post(
                "/api/invoices",
                files={"file": ("f.pdf", _pdf_bytes(), "application/pdf")},
                data={
                    "invoice_number": f"FAC-PG-{i}",
                    "supplier_id": str(supplier_id),
                },
                headers=headers,
            )
        page = invoice_client.get("/api/invoices?limit=2", headers=headers)
        assert page.json()["total"] == 4
        assert len(page.json()["items"]) == 2

    def test_read_requires_read_permission(self, invoice_client, engine) -> None:
        headers, supplier_id = self._seed(invoice_client, engine)
        roles = _register_roles(invoice_client)
        assert (
            invoice_client.get("/api/invoices", headers=roles["acheteur"]).status_code
            == 200
        )
        assert invoice_client.get("/api/invoices").status_code == 401


class TestDetail:
    def _deposit(
        self, invoice_client, engine, number: str = "FAC-DET"
    ) -> tuple[int, dict[str, str], bytes]:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        content = _pdf_bytes()
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", content, "application/pdf")},
            data={"invoice_number": number, "supplier_id": str(supplier_id)},
            headers=headers,
        )
        return response.json()["id"], headers, content

    def test_get_detail(self, invoice_client, engine) -> None:
        invoice_id, headers, _ = self._deposit(invoice_client, engine)
        response = invoice_client.get(f"/api/invoices/{invoice_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == invoice_id
        assert response.json()["file_info"]["content_type"] == "application/pdf"

    def test_get_unknown_invoice_404(self, invoice_client) -> None:
        headers = _register_roles(invoice_client)["comptable"]
        assert (
            invoice_client.get("/api/invoices/999999", headers=headers).status_code
            == 404
        )

    def test_download_source_file_roundtrip(self, invoice_client, engine) -> None:
        invoice_id, headers, content = self._deposit(invoice_client, engine)
        response = invoice_client.get(
            f"/api/invoices/{invoice_id}/file", headers=headers
        )
        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"].startswith("application/pdf")
        assert "facture.pdf" in response.headers["content-disposition"]

    def test_download_file_missing_404(self, invoice_client, engine) -> None:
        from app.repositories import InvoiceRepository, SupplierRepository

        headers = _register_roles(invoice_client)["comptable"]
        Session = sessionmaker(bind=engine)
        session = Session()
        supplier = SupplierRepository(session).create(odoo_id=9, name="ACME")
        invoice = InvoiceRepository(session).create(
            invoice_number="FAC-NOFILE", supplier_id=supplier.id
        )
        session.commit()
        invoice_id = invoice.id
        session.close()

        response = invoice_client.get(
            f"/api/invoices/{invoice_id}/file", headers=headers
        )
        assert response.status_code == 404, response.text


class TestStatusTransitions:
    def _deposit(self, invoice_client, engine, number: str) -> int:
        headers = _register_roles(invoice_client)["comptable"]
        supplier_id = _create_supplier(engine)
        response = invoice_client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", _pdf_bytes(), "application/pdf")},
            data={"invoice_number": number, "supplier_id": str(supplier_id)},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["id"], headers

    def test_full_valid_chain(self, invoice_client, engine) -> None:
        invoice_id, headers = self._deposit(invoice_client, engine, "FAC-STATUS")
        steps = ["En cours d'analyse", "À vérifier", "Validée", "Vendor Bill créée"]
        for step in steps:
            response = invoice_client.post(
                f"/api/invoices/{invoice_id}/status",
                json={"status": step},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == step

    def test_invalid_skip_transition_rejected(self, invoice_client, engine) -> None:
        invoice_id, headers = self._deposit(invoice_client, engine, "FAC-SKIP")
        response = invoice_client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": "À vérifier"},
            headers=headers,
        )
        assert response.status_code == 409, response.text

    def test_rejection_with_reason(self, invoice_client, engine) -> None:
        invoice_id, headers = self._deposit(invoice_client, engine, "FAC-REJ")
        invoice_client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": "En cours d'analyse"},
            headers=headers,
        )
        response = invoice_client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": "À vérifier"},
            headers=headers,
        )
        assert response.status_code == 200
        response = invoice_client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": "Rejetée", "reason": "Facture sans BC"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Rejetée"
        assert response.json()["rejection_reason"] == "Facture sans BC"

    def test_status_change_requires_validate_permission(
        self, invoice_client, engine
    ) -> None:
        roles = _register_roles(invoice_client)
        invoice_id, _ = self._deposit(invoice_client, engine, "FAC-PERM")
        response = invoice_client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": "En cours d'analyse"},
            headers=roles["acheteur"],
        )
        assert response.status_code == 403, response.text
