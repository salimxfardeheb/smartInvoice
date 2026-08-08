"""Tests de la reconstruction des lignes de lecture (``app.ocr.rows``).

Les moteurs OCR rendent des fragments positionnés : une ligne de tableau est
découpée en plusieurs détections, et un libellé est souvent séparé de sa
valeur. Ces tests figent le comportement attendu du regroupement, y compris
son effet sur l'extraction (TVA rattachée à son montant, lignes de totaux
correctement exclues des articles).
"""

from __future__ import annotations

from decimal import Decimal

from app.ocr.extractor import FieldExtractor
from app.ocr.lines import InvoiceLineParser
from app.ocr.rows import group_rows

# Fragments tels que PaddleOCR les rend réellement sur une facture tabulaire :
# la désignation, les colonnes chiffrées et le montant sont trois détections.
FRAGMENTS = [
    ("Câble HDMI 2m", 0.99, (60.0, 700.0, 320.0, 740.0)),
    ("8 u 8,50 €", 0.90, (400.0, 702.0, 560.0, 738.0)),
    ("68,00 €", 0.95, (620.0, 701.0, 740.0, 739.0)),
    ("TVA 20%", 1.00, (60.0, 800.0, 200.0, 840.0)),
    ("79,58 €", 0.98, (620.0, 802.0, 740.0, 838.0)),
]


def _split(fragments):
    texts = [text for text, _, _ in fragments]
    scores = [score for _, score, _ in fragments]
    boxes = [box for _, _, box in fragments]
    return texts, scores, boxes


class TestGroupRows:
    def test_merges_fragments_sharing_a_vertical_band(self) -> None:
        texts, scores, boxes = _split(FRAGMENTS)

        rows, row_scores = group_rows(texts, scores, boxes)

        assert rows == ["Câble HDMI 2m 8 u 8,50 € 68,00 €", "TVA 20% 79,58 €"]
        assert len(row_scores) == 2
        assert row_scores[0] == (0.99 + 0.90 + 0.95) / 3

    def test_orders_fragments_left_to_right(self) -> None:
        """L'ordre de lecture est rétabli même si le moteur les rend inversés."""
        texts = ["68,00 €", "Câble HDMI 2m"]
        boxes = [(620.0, 701.0, 740.0, 739.0), (60.0, 700.0, 320.0, 740.0)]

        rows, _ = group_rows(texts, [0.9, 0.9], boxes)

        assert rows == ["Câble HDMI 2m 68,00 €"]

    def test_separate_bands_stay_separate(self) -> None:
        texts = ["Total HT", "397,90 €"]
        boxes = [(60.0, 900.0, 200.0, 940.0), (620.0, 1000.0, 740.0, 1040.0)]

        rows, _ = group_rows(texts, [0.9, 0.9], boxes)

        assert rows == ["Total HT", "397,90 €"]

    def test_without_boxes_texts_are_unchanged(self) -> None:
        """Un moteur sans layout ne doit subir aucun regroupement arbitraire."""
        texts = ["Total HT", "397,90 €"]

        rows, scores = group_rows(texts, [0.9, 0.8], [])

        assert rows == texts
        assert scores == [0.9, 0.8]

    def test_degenerate_boxes_are_not_merged(self) -> None:
        """Une boîte ``(0, 0, 0, 0)`` signale une position inconnue."""
        texts = ["Total HT", "397,90 €"]
        boxes = [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)]

        rows, _ = group_rows(texts, [0.9, 0.9], boxes)

        assert rows == texts

    def test_empty_input(self) -> None:
        assert group_rows([], [], []) == ([], [])

    def test_missing_scores_do_not_break_grouping(self) -> None:
        texts, _, boxes = _split(FRAGMENTS[:3])

        rows, scores = group_rows(texts, [], boxes)

        assert rows == ["Câble HDMI 2m 8 u 8,50 € 68,00 €"]
        assert scores == [0.0]


class TestGroupingEnablesExtraction:
    """Sans regroupement, ces extractions échouent sur une sortie réelle."""

    def test_tax_amount_is_recovered(self) -> None:
        texts, scores, boxes = _split(FRAGMENTS)
        rows, _ = group_rows(texts, scores, boxes)

        _, financial = FieldExtractor().extract(rows)

        assert financial.tax_amount == Decimal("79.58")

    def test_tax_amount_is_lost_without_grouping(self) -> None:
        """Comportement de référence : le libellé « TVA 20% » est isolé."""
        texts, _, _ = _split(FRAGMENTS)

        _, financial = FieldExtractor().extract(texts)

        assert financial.tax_amount is None

    def test_item_line_keeps_its_description(self) -> None:
        texts, scores, boxes = _split(FRAGMENTS)
        rows, row_scores = group_rows(texts, scores, boxes)

        items = InvoiceLineParser().parse(rows, row_scores)

        assert len(items) == 1
        item = items[0]
        assert item.description == "Câble HDMI 2m"
        assert item.quantity == Decimal("8")
        assert item.unit == "u"
        assert item.unit_price == Decimal("8.50")
        assert item.amount == Decimal("68.00")

    def test_total_rows_are_not_taken_for_items(self) -> None:
        """Un montant orphelin (« 397,90 € ») serait pris pour un article."""
        texts = ["Total HT", "397,90 €"]
        boxes = [(60.0, 900.0, 200.0, 940.0), (620.0, 902.0, 740.0, 938.0)]
        rows, row_scores = group_rows(texts, [0.99, 0.99], boxes)

        assert InvoiceLineParser().parse(rows, row_scores) == []


class TestPipelineGroupsFragments:
    """Le service OCR applique le regroupement avant l'extraction."""

    def test_service_extracts_from_fragmented_engine_output(
        self, session, tmp_path
    ) -> None:
        from app.models.enums import InvoiceStatus
        from app.ocr.base import OcrResult
        from app.services.ocr_service import OcrService
        from app.storage.local import LocalStorage
        from tests.conftest import make_invoice, make_supplier
        from tests.ocr_fakes import FakeOcrEngine, make_pdf_bytes

        storage = LocalStorage(tmp_path)
        supplier = make_supplier(session)
        session.flush()
        invoice = make_invoice(session, supplier.id, invoice_number="FRAG-001")
        invoice.file_path = storage.save(make_pdf_bytes(), suffix=".pdf")
        invoice.content_type = "application/pdf"
        session.flush()

        fragments = FRAGMENTS + [
            ("Total TTC", 0.99, (60.0, 900.0, 200.0, 940.0)),
            ("477,48 €", 0.99, (620.0, 902.0, 740.0, 938.0)),
        ]
        texts, scores, boxes = _split(fragments)
        engine = FakeOcrEngine(
            results=[OcrResult(texts=texts, scores=scores, page_index=0, boxes=boxes)]
        )

        result = OcrService(session, storage, engine=engine).process(invoice)

        assert result.status is InvoiceStatus.TO_REVIEW
        data = result.extracted_data
        assert data["financial"]["tax_amount"] == "79.58"
        assert data["financial"]["total_incl_tax"] == "477.48"
        assert [line["description"] for line in data["lines"]] == ["Câble HDMI 2m"]
        # Les détections brutes restent la preuve visuelle de la page.
        assert data["pages"][0]["texts"] == texts
        assert len(data["pages"][0]["layout"]) == len(texts)
