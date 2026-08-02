"""Tests unitaires du service de matching facture ↔ bon de commande (phase 6).

Couvre : le cas conforme (score parfait, aucune anomalie), les écarts
(quantité, prix, montants, TVA → anomalies enregistrées), la détection de
doublon, le BC introuvable, le produit absent, la discordance de fournisseur,
l'idempotence des passages et la persistance du score. Un test d'intégration
API valide le endpoint ``POST /api/invoices/{id}/match``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.enums import AnomalyCategory
from app.repositories import (
    AnomalyRepository,
    InvoiceLineRepository,
    InvoiceRepository,
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
)
from app.services.matching_service import MatchingService

from tests.conftest import make_supplier


def _build_context(
    session,
    *,
    invoice_number: str = "FAC-2026-001",
    supplier_name: str = "ACME SAS",
    extracted_supplier_name: str | None = None,
    supplier: object | None = None,
    po_reference: str = "PO-2026-001",
    po_total: str | None = "461.25",
    create_po: bool = True,
    totals: tuple[str, str, str] | None = ("385.00", "76.25", "461.25"),
    invoice_lines: list[dict] | None = None,
    po_lines: list[dict] | None = None,
    extracted_invoice_number: str | None = None,
) -> tuple:
    """Construit un contexte conforme (fournisseur, BC, facture) pour les tests.

    Retourne ``(supplier, purchase_order, invoice)``. Par défaut, la facture
    est parfaitement alignée sur le bon de commande (2 lignes, montants et
    TVA cohérents), ce qui donne un score de matching de 1.0.
    """
    supplier = supplier or make_supplier(session, odoo_id=42, name=supplier_name)

    purchase_order = None
    if create_po:
        if po_lines is None:
            po_lines = [
                {
                    "odoo_id": 1, "line_number": 10, "product_ref": "CBL-001",
                    "name": "Câble HDMI", "quantity": "10.0",
                    "unit_price": "8.50", "amount": "85.00",
                },
                {
                    "odoo_id": 2, "line_number": 20, "product_ref": "SCR-24",
                    "name": "Écran LED", "quantity": "2.0",
                    "unit_price": "150.00", "amount": "300.00",
                },
            ]
        purchase_order = PurchaseOrderRepository(session).create(
            odoo_id=100,
            reference=po_reference,
            supplier_id=supplier.id,
            state="purchase",
            total_amount=po_total,
        )
        for data in po_lines:
            PurchaseOrderLineRepository(session).create(
                purchase_order_id=purchase_order.id, **data
            )

    if invoice_lines is None:
        invoice_lines = [
            {
                "line_number": 1, "description": "Câble HDMI",
                "product_ref": "CBL-001", "quantity": "10.0",
                "unit_price": "8.50", "tax_rate": "0.20", "amount": "85.00",
            },
            {
                "line_number": 2, "description": "Écran LED",
                "product_ref": "SCR-24", "quantity": "2.0",
                "unit_price": "150.00", "tax_rate": "0.20", "amount": "300.00",
            },
        ]

    total_excl, tax_amount, total_incl = totals or (None, None, None)
    extracted_general = {
        "supplier_name": (
            extracted_supplier_name
            if extracted_supplier_name is not None
            else supplier_name
        ),
        "invoice_number": extracted_invoice_number or invoice_number,
        "purchase_order_reference": po_reference,
    }
    invoice = InvoiceRepository(session).create(
        invoice_number=invoice_number,
        supplier_id=supplier.id,
        total_excl_tax=total_excl,
        tax_amount=tax_amount,
        total_incl_tax=total_incl,
        extracted_data={"general": extracted_general, "financial": {}, "lines": []},
    )
    for data in invoice_lines:
        InvoiceLineRepository(session).create(invoice_id=invoice.id, **data)

    session.commit()
    return supplier, purchase_order, invoice


class TestConformingMatch:
    """Cas conforme : la facture est parfaitement alignée sur le BC."""

    def test_score_is_perfect_and_no_anomaly(self, session) -> None:
        _, _, invoice = _build_context(session)
        result = MatchingService(session).match(invoice)

        assert result.score == 1.0
        assert result.supplier_match is True
        assert result.duplicate_found is False
        assert result.purchase_order is not None
        assert result.matched_line_count == 2
        assert all(m.quantity_matched and m.unit_price_matched for m in result.line_matches)
        assert result.anomalies == []

    def test_lines_are_linked_to_po_lines(self, session) -> None:
        _, po, invoice = _build_context(session)
        MatchingService(session).match(invoice)

        lines = InvoiceLineRepository(session).list_by_invoice(invoice.id)
        assert [l.purchase_order_line_odoo_id for l in lines] == [1, 2]

    def test_invoice_links_and_score_are_persisted(self, session) -> None:
        _, po, invoice = _build_context(session)
        MatchingService(session).match(invoice)
        session.commit()
        session.refresh(invoice)

        assert invoice.purchase_order_id == po.id
        assert invoice.matching_score == 1.0
        assert invoice.is_duplicate is False


class TestGaps:
    """Cas avec écarts : anomalies enregistrées et score dégradé."""

    def test_quantity_price_and_tax_gaps_are_recorded(self, session) -> None:
        _, _, invoice = _build_context(
            session,
            invoice_lines=[
                {
                    "line_number": 1, "description": "Câble HDMI",
                    "product_ref": "CBL-001", "quantity": "12.0",
                    "unit_price": "9.50", "tax_rate": "0.20", "amount": "114.00",
                },
                {
                    "line_number": 2, "description": "Écran LED",
                    "product_ref": "SCR-24", "quantity": "2.0",
                    "unit_price": "150.00", "tax_rate": "0.20", "amount": "300.00",
                },
            ],
            totals=("414.00", "80.00", "494.00"),
        )
        result = MatchingService(session).match(invoice)

        categories = {a.category for a in result.anomalies}
        assert AnomalyCategory.QUANTITY in categories
        assert AnomalyCategory.AMOUNT in categories
        assert AnomalyCategory.TAX in categories
        assert result.score < 1.0

        quantity = [
            a for a in result.anomalies if a.category is AnomalyCategory.QUANTITY
        ][0]
        assert Decimal(quantity.expected_value) == Decimal("10")
        assert Decimal(quantity.actual_value) == Decimal("12")

    def test_anomalies_are_persisted(self, session) -> None:
        _, _, invoice = _build_context(
            session,
            invoice_lines=[
                {
                    "line_number": 1, "description": "Câble HDMI",
                    "product_ref": "CBL-001", "quantity": "12.0",
                    "unit_price": "9.50", "amount": "114.00",
                },
            ],
            totals=("114.00", "22.80", "136.80"),
        )
        MatchingService(session).match(invoice)

        anomalies = AnomalyRepository(session).list_by_invoice(invoice.id)
        categories = {a.category for a in anomalies}
        assert AnomalyCategory.QUANTITY in categories
        assert AnomalyCategory.AMOUNT in categories


class TestProductMissing:
    def test_unmatched_line_raises_product_missing(self, session) -> None:
        _, _, invoice = _build_context(
            session,
            invoice_lines=[
                {
                    "line_number": 1, "description": "Câble HDMI",
                    "product_ref": "CBL-001", "quantity": "10.0",
                    "unit_price": "8.50", "amount": "85.00",
                },
                {
                    "line_number": 2, "description": "Vignette inconnue",
                    "product_ref": "XYZ-999", "quantity": "1.0",
                    "unit_price": "5.00", "amount": "5.00",
                },
            ],
            totals=("90.00", "18.00", "108.00"),
        )
        result = MatchingService(session).match(invoice)

        assert result.matched_line_count == 1
        categories = {a.category for a in result.anomalies}
        assert AnomalyCategory.PRODUCT_MISSING in categories
        assert result.line_matches[1].matched is False


class TestPurchaseOrderNotFound:
    def test_missing_po_raises_anomaly_and_low_score(self, session) -> None:
        _, _, invoice = _build_context(
            session, po_reference="PO-NOPE", create_po=False
        )
        # Le BC local n'existe pas pour cette référence.
        result = MatchingService(session).match(invoice)

        assert result.purchase_order is None
        assert [a.category for a in result.anomalies] == [
            AnomalyCategory.PURCHASE_ORDER
        ]
        assert result.score < 0.5


class TestSupplierMismatch:
    def test_supplier_mismatch_is_recorded(self, session) -> None:
        _, _, invoice = _build_context(
            session, extracted_supplier_name="Betasoft Inc"
        )
        result = MatchingService(session).match(invoice)

        assert result.supplier_match is False
        assert [a.category for a in result.anomalies] == [
            AnomalyCategory.SUPPLIER
        ]
        assert result.score < 1.0


class TestDuplicate:
    def test_duplicate_via_extracted_number_is_detected(self, session) -> None:
        supplier, _, first = _build_context(
            session,
            invoice_number="FAC-2026-001",
            po_reference="PO-2026-001",
        )
        # Deuxième facture : numéro différent au dépôt, mais l'OCR extrait le
        # même numéro que la première → doublon pour ce fournisseur.
        _, _, second = _build_context(
            session,
            supplier=supplier,
            invoice_number="FAC-2026-002",
            po_reference="PO-2026-001",
            extracted_invoice_number=first.invoice_number,
            create_po=False,
        )

        result = MatchingService(session).match(second)
        session.commit()
        session.refresh(second)

        assert result.duplicate_found is True
        duplicate = [
            a for a in result.anomalies if a.category is AnomalyCategory.DUPLICATE
        ]
        assert len(duplicate) == 1
        assert duplicate[0].severity.value == "critical"
        assert second.is_duplicate is True

    def test_own_number_does_not_self_match(self, session) -> None:
        _, _, invoice = _build_context(session)
        result = MatchingService(session).match(invoice)
        assert result.duplicate_found is False


class TestIdempotence:
    def test_running_match_twice_does_not_duplicate_anomalies(self, session) -> None:
        _, _, invoice = _build_context(
            session,
            invoice_lines=[
                {
                    "line_number": 1, "description": "Câble HDMI",
                    "product_ref": "CBL-001", "quantity": "12.0",
                    "unit_price": "9.50", "amount": "114.00",
                },
            ],
            totals=("114.00", "22.80", "136.80"),
        )
        service = MatchingService(session)
        service.match(invoice)
        first_pass = len(AnomalyRepository(session).list_by_invoice(invoice.id))

        service.match(invoice)
        second_pass = len(AnomalyRepository(session).list_by_invoice(invoice.id))

        assert first_pass == second_pass
        assert first_pass > 0

    def test_ocr_anomaly_is_preserved(self, session) -> None:
        _, _, invoice = _build_context(session)
        from app.models.enums import AnomalySeverity

        AnomalyRepository(session).create(
            invoice_id=invoice.id,
            category=AnomalyCategory.OTHER,
            severity=AnomalySeverity.WARNING,
            message="Score de confiance OCR faible.",
        )
        session.commit()

        MatchingService(session).match(invoice)
        categories = {
            a.category for a in AnomalyRepository(session).list_by_invoice(invoice.id)
        }
        assert AnomalyCategory.OTHER in categories


class TestMatchingApi:
    """Test d'intégration du endpoint ``POST /api/invoices/{id}/match``."""

    @pytest.fixture()
    def match_client(self, client, tmp_path):
        from app.storage import get_storage
        from app.storage.local import LocalStorage

        client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
        yield client
        client.app.dependency_overrides.clear()

    def test_match_endpoint_returns_score_and_anomalies(
        self, match_client, engine
    ) -> None:
        from tests.conftest import auth_headers, register_user

        register_user(match_client, username="admin", email="admin@example.com")
        headers = auth_headers(match_client, "admin")

        Session = sessionmaker(bind=engine)
        with Session() as db:
            _, _, invoice = _build_context(db)
            invoice_id = invoice.id

        response = match_client.post(
            f"/api/invoices/{invoice_id}/match", headers=headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["invoice_id"] == invoice_id
        assert body["score"] == 1.0
        assert body["supplier_match"] is True
        assert body["duplicate_found"] is False
        assert body["purchase_order_reference"] == "PO-2026-001"
        assert len(body["lines"]) == 2
        assert len(body["anomalies"]) == 0

    def test_match_endpoint_requires_authentication(self, match_client, engine) -> None:
        response = match_client.post("/api/invoices/1/match")
        assert response.status_code == 401

    def test_match_endpoint_unknown_invoice_404(self, match_client, engine) -> None:
        from tests.conftest import auth_headers, register_user

        register_user(match_client, username="admin", email="admin@example.com")
        headers = auth_headers(match_client, "admin")
        response = match_client.post("/api/invoices/999999/match", headers=headers)
        assert response.status_code == 404, response.text

    def test_match_endpoint_reports_gaps(self, match_client, engine) -> None:
        from tests.conftest import auth_headers, register_user

        register_user(match_client, username="admin", email="admin@example.com")
        headers = auth_headers(match_client, "admin")

        Session = sessionmaker(bind=engine)
        with Session() as db:
            _, _, invoice = _build_context(
                db,
                invoice_lines=[
                    {
                        "line_number": 1, "description": "Câble HDMI",
                        "product_ref": "CBL-001", "quantity": "12.0",
                        "unit_price": "9.50", "amount": "114.00",
                    },
                ],
                totals=("114.00", "22.80", "136.80"),
            )
            invoice_id = invoice.id

        response = match_client.post(
            f"/api/invoices/{invoice_id}/match", headers=headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        categories = {a["category"] for a in body["anomalies"]}
        assert "quantite" in categories
        assert "montant" in categories
        assert body["score"] < 1.0
