"""Tests d'intégration du workflow complet (phase 9).

Valide la chaîne complète, du dépôt de la facture jusqu'à la création de la
Vendor Bill Odoo, via l'API HTTP :

    upload → OCR → matching → validation → Vendor Bill

ainsi que les scénarios d'erreur du cahier des charges :

- document illisible (l'OCR ne reconnaît aucun texte) ;
- fournisseur inexistant (dépôt rejeté) ;
- BC introuvable (la référence extraite ne correspond à aucun bon de
  commande) ;
- écarts détectés (quantité / prix / montants / TVA en écart) ;
- doublon (même fournisseur + même numéro de facture).

Les dépendances externes sont bouchonnées : stockage local temporaire, moteur
OCR factice et client Odoo factice (création de l'``account.move``).
"""

from __future__ import annotations


import pytest
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import OdooError
from app.models.enums import AnomalyCategory, InvoiceStatus
from tests.ocr_fakes import FakeOcrEngine, make_pdf_bytes
from tests.conftest import auth_headers, make_supplier

# Référence du bon de commande extraite par les textes OCR « conformes ».
HAPPY_PO_REFERENCE = "PO-2026-0123"


class FakeOdooClient:
    """Bouchon du client Odoo : crée un ``account.move`` et enregistre l'appel."""

    def __init__(
        self,
        *,
        move_id: int = 9001,
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


def happy_texts() -> list[str]:
    """Textes OCR alignés sur le bon de commande (match parfait)."""
    return [
        "ACME SAS",
        "12 rue des Lilas",
        "75011 Paris",
        "Facture N° FAC-2026-001",
        "Date d'émission : 15/01/2026",
        "Échéance : 15/02/2026",
        f"Bon de commande : {HAPPY_PO_REFERENCE}",
        "Désignation     Qté    PU      Montant",
        "Câble HDMI 10  8,50    85,00",
        "Écran LED 2    149,00  298,00",
        "Livraison  5,90 €",
        "Total HT  383,00 €",
        "TVA 20%  76,60 €",
        "Total TTC  459,60 €",
    ]


def unknown_po_texts() -> list[str]:
    """Textes OCR avec une référence de bon de commande introuvable."""
    return [
        "ACME SAS",
        "Facture N° FAC-2026-050",
        "Date d'émission : 15/01/2026",
        "Bon de commande : PO-9999",
        "Câble HDMI 10  8,50    85,00",
        "Total HT  85,00 €",
        "TVA 20%  17,00 €",
        "Total TTC  102,00 €",
    ]


def gaps_texts() -> list[str]:
    """Textes OCR avec des écarts de quantité et de prix unitaire."""
    return [
        "ACME SAS",
        "Facture N° FAC-2026-060",
        "Date d'émission : 15/01/2026",
        f"Bon de commande : {HAPPY_PO_REFERENCE}",
        "Câble HDMI 12  9,50    114,00",
        "Écran LED 2    149,00  298,00",
        "Total HT  412,00 €",
        "TVA 20%  82,40 €",
        "Total TTC  494,40 €",
    ]


def _db_session(engine):
    """Ouvre une session SQLAlchemy sur le moteur de test (fournisseur/BC)."""
    return sessionmaker(bind=engine)()


def _seed_supplier_and_po(session) -> tuple[int, int]:
    """Crée le fournisseur et son bon de commande (2 lignes) en base.

    Retourne ``(supplier_id, purchase_order_id)``.
    """
    from app.repositories import (
        PurchaseOrderLineRepository,
        PurchaseOrderRepository,
    )

    supplier = make_supplier(session, odoo_id=42, name="ACME SAS")
    purchase_order = PurchaseOrderRepository(session).create(
        odoo_id=100,
        reference=HAPPY_PO_REFERENCE,
        supplier_id=supplier.id,
        state="purchase",
        total_amount="459.60",
    )
    PurchaseOrderLineRepository(session).create(
        purchase_order_id=purchase_order.id,
        odoo_id=1,
        line_number=10,
        product_ref="CBL-001",
        name="Câble HDMI",
        quantity="10.0",
        unit_price="8.50",
        amount="85.00",
    )
    PurchaseOrderLineRepository(session).create(
        purchase_order_id=purchase_order.id,
        odoo_id=2,
        line_number=20,
        product_ref="SCR-24",
        name="Écran LED",
        quantity="2.0",
        unit_price="149.00",
        amount="298.00",
    )
    session.commit()
    return supplier.id, purchase_order.id


def _create_supplier_only(session) -> int:
    """Crée un fournisseur sans bon de commande et retourne son id."""
    supplier = make_supplier(session, odoo_id=43, name="Beta SARL")
    session.commit()
    return supplier.id


def _register_accountant(client) -> dict[str, str]:
    """Inscrit un comptable et retourne ses en-têtes d'authentification."""
    from tests.conftest import register_user

    register_user(client, username="comptable", email="comptable@example.com")
    return auth_headers(client, "comptable")


@pytest.fixture()
def workflow_client(client, tmp_path):
    """Client de test branché sur stockage local + OCR + Odoo factices."""
    from fastapi import Depends

    from app.api.deps import (
        get_db,
        get_ocr_engine_dep,
        get_storage,
        get_validation_service,
    )
    from app.services.validation_service import ValidationService
    from app.storage.local import LocalStorage

    holder = {"engine": FakeOcrEngine(), "odoo": FakeOdooClient()}
    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    client.app.dependency_overrides[get_ocr_engine_dep] = lambda: holder["engine"]

    def _override_validation(db=Depends(get_db)):
        return ValidationService(db, odoo_client=holder["odoo"])

    client.app.dependency_overrides[get_validation_service] = _override_validation
    yield client, holder
    client.app.dependency_overrides.clear()


def _deposit(client, headers, supplier_id, *, number: str) -> dict:
    """Dépose une facture PDF valide et retourne le corps JSON de la réponse."""
    response = client.post(
        "/api/invoices",
        files={"file": ("facture.pdf", make_pdf_bytes(), "application/pdf")},
        data={"invoice_number": number, "supplier_id": str(supplier_id)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _process(client, headers, invoice_id: int) -> dict:
    """Lance l'OCR (asynchrone, exécuté inline en test) puis retourne la facture.

    Depuis la migration vers les tâches asynchrones, ``POST /process`` répond
    202 avec un ``task_id`` ; en test l'exécuteur inline l'a déjà terminée.
    On retourne l'état **à jour** de la facture (via ``GET``).
    """
    response = client.post(f"/api/invoices/{invoice_id}/process", headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["state"] == "réussi", response.text
    invoice = client.get(f"/api/invoices/{invoice_id}", headers=headers)
    assert invoice.status_code == 200, invoice.text
    return invoice.json()


class TestHappyPath:
    """Workflow nominal : dépôt → OCR → matching → validation → Vendor Bill."""

    def test_full_workflow_creates_vendor_bill(self, workflow_client, engine) -> None:
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id, _ = _seed_supplier_and_po(db)

        # 1. Dépôt de la facture.
        invoice = _deposit(client, headers, supplier_id, number="FAC-2026-001")
        invoice_id = invoice["id"]
        assert invoice["status"] == InvoiceStatus.SUBMITTED.value

        # 2. Analyse OCR → « À vérifier » avec les données extraites.
        holder["engine"] = FakeOcrEngine(
            texts=happy_texts(), scores=[0.95] * len(happy_texts())
        )
        processed = _process(client, headers, invoice_id)
        assert processed["status"] == InvoiceStatus.TO_REVIEW.value
        assert processed["extracted_data"]["general"]["purchase_order_reference"] == (
            HAPPY_PO_REFERENCE
        )
        assert len(processed["extracted_data"]["lines"]) == 2

        # 3. Matching → score parfait, aucune anomalie.
        response = client.post(f"/api/invoices/{invoice_id}/match", headers=headers)
        assert response.status_code == 200, response.text
        matched = response.json()
        assert matched["score"] == 1.0
        assert matched["supplier_match"] is True
        assert matched["duplicate_found"] is False
        assert matched["purchase_order_reference"] == HAPPY_PO_REFERENCE
        assert matched["anomalies"] == []

        # 4. Validation comptable → « Validée ».
        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == InvoiceStatus.VALIDATED.value

        # 5. Création de la Vendor Bill Odoo → « Vendor Bill créée ».
        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)
        assert response.status_code == 200, response.text
        created = response.json()
        assert created["status"] == InvoiceStatus.VENDOR_BILL_CREATED.value
        assert created["vendor_bill_id"] == holder["odoo"].move_id

        # 6. Le journal d'audit trace validation + création de la Vendor Bill.
        response = client.get(f"/api/invoices/{invoice_id}/audit-logs", headers=headers)
        assert response.status_code == 200, response.text
        actions = [entry["action"] for entry in response.json()["items"]]
        assert actions == ["vendor_bill_créée", "validation"]

        # 7. Les lignes de l'account.move sont construites depuis la facture.
        model, values = holder["odoo"].calls[0]
        assert model == "account.move"
        assert values["ref"] == "FAC-2026-001"
        assert values["partner_id"] == 42
        assert len(values["invoice_line_ids"]) == 2
        assert values["invoice_line_ids"][0][2]["name"] == "Câble HDMI"


class TestIllegibleDocument:
    """Scénario d'erreur : document dont l'OCR ne reconnaît aucun texte."""

    def test_unreadable_document_sets_system_error(self, workflow_client, engine) -> None:
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id = _create_supplier_only(db)

        invoice = _deposit(client, headers, supplier_id, number="FAC-ILLISIBLE")
        invoice_id = invoice["id"]

        holder["engine"] = FakeOcrEngine(texts=[], scores=[])
        body = _process(client, headers, invoice_id)

        assert body["status"] == InvoiceStatus.SYSTEM_ERROR.value
        assert body["error_message"] is not None
        assert "texte" in body["error_message"].lower()

        # La facture n'est pas validable dans cet état.
        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)
        assert response.status_code == 409, response.text


class TestUnknownSupplier:
    """Scénario d'erreur : le fournisseur fourni au dépôt n'existe pas."""

    def test_deposit_with_unknown_supplier_is_rejected(self, workflow_client) -> None:
        client, _ = workflow_client
        headers = _register_accountant(client)

        response = client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", make_pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-404", "supplier_id": "999999"},
            headers=headers,
        )

        assert response.status_code == 404, response.text
        assert "fournisseur" in response.json()["detail"].lower()


class TestPurchaseOrderNotFound:
    """Scénario d'erreur : la référence de BC extraite est introuvable."""

    def test_missing_purchase_order_is_reported_by_matching(self, workflow_client, engine) -> None:
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id = _create_supplier_only(db)

        invoice = _deposit(client, headers, supplier_id, number="FAC-2026-050")
        invoice_id = invoice["id"]

        holder["engine"] = FakeOcrEngine(
            texts=unknown_po_texts(), scores=[0.95] * len(unknown_po_texts())
        )
        processed = _process(client, headers, invoice_id)
        assert processed["status"] == InvoiceStatus.TO_REVIEW.value

        response = client.post(f"/api/invoices/{invoice_id}/match", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        categories = {anomaly["category"] for anomaly in body["anomalies"]}
        assert AnomalyCategory.PURCHASE_ORDER.value in categories
        assert body["purchase_order_reference"] == "PO-9999"
        assert body["score"] < 0.5


class TestDetectedGaps:
    """Scénario d'erreur : écarts de quantité et de prix détectés au matching."""

    def test_gaps_are_detected_and_invoice_goes_to_review(self, workflow_client, engine) -> None:
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id, _ = _seed_supplier_and_po(db)

        invoice = _deposit(client, headers, supplier_id, number="FAC-2026-060")
        invoice_id = invoice["id"]

        holder["engine"] = FakeOcrEngine(
            texts=gaps_texts(), scores=[0.95] * len(gaps_texts())
        )
        processed = _process(client, headers, invoice_id)
        assert processed["status"] == InvoiceStatus.TO_REVIEW.value

        response = client.post(f"/api/invoices/{invoice_id}/match", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        categories = {anomaly["category"] for anomaly in body["anomalies"]}
        assert AnomalyCategory.QUANTITY.value in categories
        assert AnomalyCategory.AMOUNT.value in categories
        assert body["score"] < 1.0

        # La facture reste « À vérifier » : le comptable peut la corriger.
        response = client.post(f"/api/invoices/{invoice_id}/validate", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == InvoiceStatus.VALIDATED.value


class TestDuplicate:
    """Scénario d'erreur : dépôt d'une facture déjà enregistrée."""

    def test_deposit_of_duplicate_invoice_is_rejected(self, workflow_client, engine) -> None:
        client, _ = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id = _create_supplier_only(db)

        _deposit(client, headers, supplier_id, number="FAC-DOUBLON")
        response = client.post(
            "/api/invoices",
            files={"file": ("facture.pdf", make_pdf_bytes(), "application/pdf")},
            data={"invoice_number": "FAC-DOUBLON", "supplier_id": str(supplier_id)},
            headers=headers,
        )

        assert response.status_code == 409, response.text
        assert "déjà" in response.json()["detail"].lower()

    def test_matching_flags_duplicate_via_extracted_number(
        self, workflow_client, engine
    ) -> None:
        """Une facture « en double » détectée au matching est marquée ``is_duplicate``."""
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id = _create_supplier_only(db)

        # Première facture avec le numéro 001.
        _deposit(client, headers, supplier_id, number="FAC-2026-001")

        # Seconde facture, numéro différent au dépôt mais l'OCR lit le numéro
        # de la première → doublon détecté par le matching.
        second = _deposit(client, headers, supplier_id, number="FAC-2026-002")
        invoice_id = second["id"]

        texts = [
            "ACME SAS",
            "Facture N° FAC-2026-001",
            f"Bon de commande : {HAPPY_PO_REFERENCE}",
            "Câble HDMI 10  8,50    85,00",
            "Total HT  85,00 €",
            "TVA 20%  17,00 €",
            "Total TTC  102,00 €",
        ]
        holder["engine"] = FakeOcrEngine(texts=texts, scores=[0.95] * len(texts))
        _process(client, headers, invoice_id)

        response = client.post(f"/api/invoices/{invoice_id}/match", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["duplicate_found"] is True
        categories = {anomaly["category"] for anomaly in body["anomalies"]}
        assert AnomalyCategory.DUPLICATE.value in categories

        detail = client.get(f"/api/invoices/{invoice_id}", headers=headers)
        assert detail.json()["is_duplicate"] is True


class TestVendorBillFailure:
    """La facture reste validée et une nouvelle tentative est possible."""

    def test_vendor_bill_failure_keeps_invoice_validated(
        self, workflow_client, engine
    ) -> None:
        client, holder = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id, _ = _seed_supplier_and_po(db)

        invoice = _deposit(client, headers, supplier_id, number="FAC-VB-KO")
        invoice_id = invoice["id"]
        holder["engine"] = FakeOcrEngine(
            texts=happy_texts(), scores=[0.95] * len(happy_texts())
        )
        _process(client, headers, invoice_id)
        client.post(f"/api/invoices/{invoice_id}/match", headers=headers)
        assert (
            client.post(f"/api/invoices/{invoice_id}/validate", headers=headers).status_code
            == 200
        )

        holder["odoo"].error = OdooError("Odoo indisponible")
        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)
        assert response.status_code == 502, response.text

        current = client.get(f"/api/invoices/{invoice_id}", headers=headers)
        assert current.json()["status"] == InvoiceStatus.VALIDATED.value

        # La seconde tentative réussit une fois Odoo revenu.
        holder["odoo"].error = None
        response = client.post(f"/api/invoices/{invoice_id}/vendor-bill", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == InvoiceStatus.VENDOR_BILL_CREATED.value


class TestStatusTransitionsThroughApi:
    """Les transitions respectent le graphe du cycle de vie via l'API."""

    def test_invoice_cannot_skip_steps(self, workflow_client, engine) -> None:
        client, _ = workflow_client
        headers = _register_accountant(client)

        with _db_session(engine) as db:
            supplier_id = _create_supplier_only(db)

        invoice = _deposit(client, headers, supplier_id, number="FAC-SKIP")
        invoice_id = invoice["id"]

        # Saute de « Déposée » à « Validée » : refusé (409).
        response = client.post(
            f"/api/invoices/{invoice_id}/status",
            json={"status": InvoiceStatus.VALIDATED.value},
            headers=headers,
        )
        assert response.status_code == 409, response.text
