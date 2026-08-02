"""Tests unitaires de l'extraction des champs et des lignes (phase 4).

Couvre : l'extracteur de champs généraux (fournisseur, numéro, dates, BC),
financiers (HT/TVA/TTC/remise/livraison) et le parseur de lignes de facture
(quantité, prix unitaire, montant, référence produit).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.ocr.cleaners import clean_text
from app.ocr.extractor import FieldExtractor
from app.ocr.lines import InvoiceLineParser
from tests.ocr_fakes import SAMPLE_INVOICE_LINES

SAMPLE_LINES = [clean_text(line) for line in SAMPLE_INVOICE_LINES]


class TestFieldExtractor:
    def test_extracts_general_fields(self) -> None:
        general, _ = FieldExtractor().extract(SAMPLE_LINES)
        assert general.invoice_number == "FAC-2026-001"
        assert general.issue_date == date(2026, 1, 15)
        assert general.due_date == date(2026, 2, 15)
        assert general.purchase_order_reference == "PO-2026-0123"
        assert general.currency == "EUR"

    def test_extracts_financial_fields(self) -> None:
        _, financial = FieldExtractor().extract(SAMPLE_LINES)
        assert financial.total_excl_tax == Decimal("171.90")
        assert financial.tax_amount == Decimal("34.38")
        assert financial.total_incl_tax == Decimal("206.28")
        assert financial.shipping_fees == Decimal("5.90")
        assert financial.discount is None

    def test_extracts_value_on_next_line(self) -> None:
        lines = ["Numéro de facture", "FAC-2026-099", "Total TTC 12,00 €"]
        general, _ = FieldExtractor().extract(lines)
        assert general.invoice_number == "FAC-2026-099"

    def test_unknown_fields_are_none(self) -> None:
        general, financial = FieldExtractor().extract(["texte quelconque"])
        assert general.invoice_number is None
        assert general.issue_date is None
        assert general.due_date is None
        assert financial.total_excl_tax is None

    def test_supplier_extraction(self) -> None:
        lines = [
            "Fournisseur : ACME SAS",
            "12 rue des Lilas",
            "75011 Paris",
            "Facture N° F-1",
        ]
        general, _ = FieldExtractor().extract(lines)
        assert general.supplier_name == "ACME SAS"
        assert general.supplier_address is not None
        assert "rue des Lilas" in general.supplier_address

    def test_supplier_ref_not_mistaken_for_name(self) -> None:
        lines = ["Réf. fournisseur : ABC-123", "Facture N° F-1"]
        general, _ = FieldExtractor().extract(lines)
        assert general.supplier_name is None

    def test_currency_detected(self) -> None:
        general, _ = FieldExtractor().extract(["Total TTC 100,00 €"])
        assert general.currency == "EUR"


class TestInvoiceLineParser:
    def test_parses_three_amount_lines(self) -> None:
        items = InvoiceLineParser().parse(SAMPLE_LINES)
        assert len(items) == 3

        first = items[0]
        assert first.line_number == 1
        assert first.description == "Câble HDMI"
        assert first.quantity == Decimal("2")
        assert first.unit_price == Decimal("8.50")
        assert first.amount == Decimal("17.00")

        second = items[1]
        assert second.quantity == Decimal("1")
        assert second.unit_price == Decimal("149.00")

        third = items[2]
        assert third.product_ref == "XLR-500"
        assert third.description == "Câble audio"
        assert third.quantity == Decimal("3")
        assert third.amount == Decimal("36.00")

    def test_ignores_total_and_header_lines(self) -> None:
        items = InvoiceLineParser().parse(SAMPLE_LINES)
        descriptions = [item.description for item in items]
        assert "Livraison" not in descriptions
        assert "Total HT" not in descriptions

    def test_ignores_address_lines(self) -> None:
        items = InvoiceLineParser().parse(
            ["12 rue des Lilas", "75011 Paris", "Total TTC 100,00 €"]
        )
        assert items == []

    def test_no_amount_line_ignored(self) -> None:
        items = InvoiceLineParser().parse(["Désignation Qté PU"])
        assert items == []

    def test_two_amounts_is_price_and_amount(self) -> None:
        items = InvoiceLineParser().parse(["Clavier 19,99 19,99"])
        assert len(items) == 1
        assert items[0].unit_price == Decimal("19.99")
        assert items[0].amount == Decimal("19.99")
        assert items[0].quantity is None

    def test_tax_rate_extracted(self) -> None:
        items = InvoiceLineParser().parse(["Câble HDMI 2 8,50 17,00 (20%)"])
        assert len(items) == 1
        assert items[0].tax_rate == Decimal("20")

    def test_unit_extracted_after_quantity(self) -> None:
        items = InvoiceLineParser().parse(["Câble HDMI 2 u 8,50 17,00"])
        assert items[0].unit == "u"
