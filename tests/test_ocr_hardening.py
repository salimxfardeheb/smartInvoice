"""Tests du durcissement OCR (lot : moteurs, multi-pages, preuves, confiance).

Couvre le moteur secondaire Tesseract et sa sélection par config, la
classification des pages annexes (multi-pages), l'agrégation des textes sur
les seules pages principales, la persistance des preuves visuelles (images de
pages + boîtes englobantes dans ``extracted_data``), la politique de confiance
par champ et la robustesse du parseur de lignes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import OcrEngineError
from app.models.enums import AnomalySeverity, InvoiceStatus
from app.ocr.base import OcrResult, get_ocr_engine
from app.ocr.confidence import (
    CRITICAL_FIELDS,
    field_confidence,
    flag_low_confidence,
    overall,
)
from app.ocr.pages import is_annex, main_pages
from app.ocr.schema import OcrBox, OcrTextBlock
from app.ocr.tesseract import TesseractOcrEngine
from app.repositories import AnomalyRepository, InvoiceLineRepository
from app.services.invoice_service import InvoiceService
from app.services.ocr_service import OcrService
from app.storage.local import LocalStorage
from tests.conftest import make_supplier
from tests.ocr_fakes import (
    FakeOcrEngine,
    SAMPLE_INVOICE_LINES,
    make_pdf_bytes_pages,
)


# --- Moteur secondaire (Tesseract) ----------------------------------------


class FakePytesseract:
    """Bouchon de ``pytesseract`` piloté par le test."""

    class Output:
        DICT = "dict"

    def __init__(self, *, texts, confs, boxes=None, langs=None) -> None:
        self._texts = texts
        self._confs = confs
        self._boxes = boxes or [(10, 20, 110, 40) for _ in texts]
        self._langs = langs or ["fra"]

    def get_languages(self, config="") -> list[str]:
        return list(self._langs)

    def image_to_data(self, image, lang=None, config=None, output_type=None) -> dict:
        return {
            "text": self._texts,
            "conf": self._confs,
            "left": [b[0] for b in self._boxes],
            "top": [b[1] for b in self._boxes],
            "width": [b[2] - b[0] for b in self._boxes],
            "height": [b[3] - b[1] for b in self._boxes],
        }


def test_tesseract_recognize_returns_texts_scores_boxes() -> None:
    engine = TesseractOcrEngine(lang="fra")
    fake = FakePytesseract(
        texts=["Total TTC", "206,28 €"],
        confs=["95", "88"],
        boxes=[(10, 20, 120, 40), (130, 20, 240, 40)],
    )
    engine._pytesseract = fake

    result = engine.recognize(Image.new("RGB", (100, 100)))

    assert result.texts == ["Total TTC", "206,28 €"]
    assert result.scores == [0.95, 0.88]
    assert result.boxes == [(10, 20, 120, 40), (130, 20, 240, 40)]


def test_tesseract_blank_words_get_zero_confidence() -> None:
    engine = TesseractOcrEngine(lang="fra")
    fake = FakePytesseract(texts=["Total TTC"], confs=["-1"], boxes=[(0, 0, 0, 0)])
    engine._pytesseract = fake
    result = engine.recognize(Image.new("RGB", (10, 10)))
    assert result.scores == [0.0]


def test_tesseract_falls_back_to_available_language() -> None:
    engine = TesseractOcrEngine(lang="fra")
    fake = FakePytesseract(texts=["Total TTC"], confs=["95"], langs=["eng"])
    engine._pytesseract = fake
    engine.recognize(Image.new("RGB", (10, 10)))
    assert engine._resolve_lang() == "eng"


def test_tesseract_unavailable_raises_ocr_engine_error(monkeypatch) -> None:
    engine = TesseractOcrEngine(lang="fra")

    def boom():
        raise ImportError("No module named 'pytesseract'")

    monkeypatch.setattr(engine, "_get_pytesseract", boom)
    with pytest.raises(OcrEngineError):
        engine.recognize(Image.new("RGB", (10, 10)))


def test_get_ocr_engine_selector() -> None:
    assert get_settings().ocr_engine == "paddle"
    assert isinstance(get_ocr_engine("paddle"), object)
    assert get_ocr_engine("tesseract").__class__.__name__ == "TesseractOcrEngine"


# --- Pages annexes & multi-pages -------------------------------------------


def test_is_annex_detects_markers() -> None:
    assert is_annex(["ANNEXE 1 - CONDITIONS GENERALES", "signature"])
    assert is_annex(["Pièce jointe : plan technique"])
    assert is_annex(["Terms and Conditions of Sale"])
    assert not is_annex(["Câble HDMI", "Total TTC 206,28 €"])
    assert not is_annex([])


def test_main_pages_excludes_annexes() -> None:
    results = [
        OcrResult(texts=["FACTURE", "Total TTC 10,00"], scores=[0.9, 0.9], page_index=0),
        OcrResult(texts=["ANNEXE"], scores=[0.9], page_index=1),
        OcrResult(texts=["Total TTC 12,00"], scores=[0.9], page_index=2),
    ]
    main = main_pages(results)
    assert [i for i, _ in main] == [0, 2]


@pytest.fixture()
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path)


@pytest.fixture()
def service(session, storage) -> OcrService:
    return OcrService(session, storage)


def _deposit_multi(service: OcrService, session, n_pages: int = 2):
    supplier = make_supplier(session, odoo_id=1, name="ACME SAS")
    invoice_service = InvoiceService(session, service.storage)
    return invoice_service.deposit(
        filename="facture_multi.pdf",
        content=make_pdf_bytes_pages(n_pages),
        invoice_number="FAC-MULTI-001",
        supplier_id=supplier.id,
    )


def test_multi_page_annex_excluded_from_extraction(service, session) -> None:
    invoice = _deposit_multi(service, session)
    engine = FakeOcrEngine(
        results=[
            OcrResult(
                texts=SAMPLE_INVOICE_LINES,
                scores=[0.95] * len(SAMPLE_INVOICE_LINES),
                page_index=0,
            ),
            OcrResult(
                texts=["ANNEXE 1", "CONDITIONS GENERALES", "Signature"],
                scores=[0.9, 0.9, 0.9],
                page_index=1,
            ),
        ]
    )
    service.engine = engine

    result = service.process(invoice)

    assert result.status is InvoiceStatus.TO_REVIEW
    data = result.extracted_data
    # La page annexe est conservée comme preuve visuelle mais exclue de l'extraction.
    assert len(data["pages"]) == 2
    assert data["pages"][0]["is_annex"] is False
    assert data["pages"][1]["is_annex"] is True
    assert data["general"]["invoice_number"] == "FAC-2026-001"
    assert len(data["lines"]) == 3
    # Chaque page a son image de preuve stockée et un layout.
    for page in data["pages"]:
        assert page["image_path"]
        assert service.storage.exists(page["image_path"])
        assert isinstance(page["layout"], list)
    # Les lignes persistées ne proviennent que de la page principale.
    lines = InvoiceLineRepository(session).list_by_invoice(result.id)
    assert len(lines) == 3


# --- Layout / boîtes englobantes -------------------------------------------


def test_layout_blocks_capture_boxes_and_confidence() -> None:
    engine = FakeOcrEngine(
        results=[
            OcrResult(
                texts=["Total TTC", "206,28 €"],
                scores=[0.8, 0.95],
                page_index=0,
                boxes=[(10, 20, 120, 40), (130, 20, 260, 40)],
            )
        ]
    )
    result = engine.recognize(Image.new("RGB", (100, 100)))
    layout = OcrService._build_layout(result)

    assert layout[0] == OcrTextBlock(
        text="Total TTC",
        confidence=0.8,
        box=OcrBox(left=10, top=20, right=120, bottom=40),
    )
    assert layout[1].box is not None


# --- Confiance par champ ---------------------------------------------------


def test_field_confidence_maps_fields_to_line_scores() -> None:
    lines = [
        "Facture N° FAC-2026-001",
        "Total HT 100,00",
        "Total TTC 120,00",
    ]
    scores = [0.5, 0.9, 0.98]
    labels = {
        "invoice_number": ("facture n",),
        "total_excl_tax": ("total ht",),
        "total_incl_tax": ("total ttc",),
        "due_date": ("échéance",),
    }
    conf = field_confidence(lines, scores, labels)
    assert conf["invoice_number"] == 0.5
    assert conf["total_excl_tax"] == 0.9
    assert conf["total_incl_tax"] == 0.98
    assert conf["due_date"] is None


def test_flag_low_confidence() -> None:
    conf = {
        "invoice_number": 0.9,
        "total_incl_tax": 0.4,
        "total_excl_tax": 0.9,
        "tax_amount": 0.7,
    }
    assert flag_low_confidence(conf, overall_score=0.9, threshold=0.6) == ["total_incl_tax"]
    # Champ critique non localisé → signalé.
    assert flag_low_confidence(
        {"invoice_number": None, "total_incl_tax": 0.9, "total_excl_tax": 0.9, "tax_amount": 0.9},
        overall_score=0.9,
        threshold=0.6,
    ) == ["invoice_number"]
    # Confiance globale faible → tous les champs critiques signalés.
    assert flag_low_confidence(
        {"invoice_number": 0.9, "total_incl_tax": 0.9, "total_excl_tax": 0.9, "tax_amount": 0.9},
        overall_score=0.3,
        threshold=0.6,
    ) == list(CRITICAL_FIELDS)


def test_service_persists_per_field_confidence_and_flags_critical(service, session) -> None:
    supplier = make_supplier(session, odoo_id=1, name="ACME SAS")
    invoice_service = InvoiceService(session, service.storage)
    invoice = invoice_service.deposit(
        filename="facture.pdf",
        content=make_pdf_bytes_pages(1),
        invoice_number="FAC-001",
        supplier_id=supplier.id,
    )
    service.engine = FakeOcrEngine(
        results=[
            OcrResult(
                texts=[
                    "Facture N° FAC-2026-001",
                    "Total HT 100,00",
                    "Total TTC 120,00",
                    "TVA 20% 20,00",
                ],
                scores=[0.9, 0.95, 0.95, 0.95],
                page_index=0,
            )
        ]
    )

    result = service.process(invoice)

    data = result.extracted_data
    assert data["confidence"]["invoice_number"] == pytest.approx(0.9)
    assert data["confidence"]["total_incl_tax"] == pytest.approx(0.95)

    # Confiance globale acceptable mais numéro de facture non localisé → anomalie.
    invoice2 = invoice_service.deposit(
        filename="facture2.pdf",
        content=make_pdf_bytes_pages(1),
        invoice_number="FAC-002",
        supplier_id=supplier.id,
    )
    service.engine = FakeOcrEngine(
        results=[
            OcrResult(
                texts=["Total HT 100,00", "Total TTC 120,00", "TVA 20% 20,00"],
                scores=[0.95, 0.95, 0.95],
                page_index=0,
            )
        ]
    )
    service.process(invoice2)
    anomalies = AnomalyRepository(session).list_by_invoice(invoice2.id)
    assert len(anomalies) == 1
    assert anomalies[0].severity is AnomalySeverity.WARNING
    assert "invoice_number" in anomalies[0].message


def test_overall_confidence() -> None:
    assert overall([0.5, 1.0]) == pytest.approx(0.75)
    assert overall([]) == 0.0


# --- Robustesse parseur de lignes ------------------------------------------


def test_parser_excludes_date_and_phone_lines(service) -> None:
    from app.ocr.lines import InvoiceLineParser

    parser = InvoiceLineParser()
    items = parser.parse(
        [
            "15/01/2026",
            "+33 1 23 45 67 89",
            "Câble HDMI 2  8,50  17,00",
        ]
    )
    assert len(items) == 1
    assert items[0].description == "Câble HDMI"


def test_parser_attaches_confidence(service) -> None:
    from app.ocr.lines import InvoiceLineParser

    items = InvoiceLineParser().parse(
        ["Câble HDMI 2  8,50  17,00", "Total TTC 20,40"],
        scores=[0.87, 0.99],
    )
    assert items[0].confidence == pytest.approx(0.87)


# --- Normalisation des montants --------------------------------------------


def test_amount_magnitude_guard(service) -> None:
    from app.ocr.cleaners import find_amounts, normalize_amount

    assert normalize_amount("0123456789012345") is None  # identifiant long
    assert normalize_amount("(99999999999999999999)") is None  # parenthèse exagérée
    assert normalize_amount("1 234 567 890,00") == Decimal("1234567890.00")
    assert find_amounts("Facture N° FAC-2026-0042") == []


# --- Jeux de données d'exemple ---------------------------------------------


def test_sample_datasets_exist_and_are_valid() -> None:
    import os

    import pypdfium2 as pdfium

    from tests.conftest import ROOT

    dataset_dir = os.path.join(ROOT, "datasets")
    for name in (
        "fr_invoice.png",
        "en_invoice.jpg",
        "multi_currency_invoice.jpg",
        "fr_invoice_multi.pdf",
        "en_invoice.pdf",
    ):
        assert os.path.exists(os.path.join(dataset_dir, name)), name

    with open(os.path.join(dataset_dir, "fr_invoice_multi.pdf"), "rb") as fh:
        doc = pdfium.PdfDocument(fh.read())
        assert len(doc) == 2  # page principale + annexe
        doc.close()
