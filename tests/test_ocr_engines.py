"""Tests unitaires des moteurs/chargeurs OCR (phase 4).

Couvre la conversion de la sortie **réelle** de PaddleOCR vers le contrat
:class:`~app.ocr.base.OcrResult` — sans instancier le vrai moteur, coûteux —
ainsi que le chargement des documents (rendu PDF, image, fichiers
manquants/corrompus).

Les échantillons de ``tests/paddle_samples.py`` sont **capturés sur le vrai
moteur** (``paddleocr==3.7.0``) : ils reproduisent l'imbrication sous la clé
``res`` que la version installée renvoie réellement. Un test d'intégration
optionnel (``SMARTINVOICE_REAL_OCR=1``) revérifie cette structure contre la
bibliothèque installée.
"""

from __future__ import annotations

import os
import sys
import types

import pytest
from PIL import Image

from app.core.exceptions import (
    DocumentNotFoundError,
    OcrEngineError,
)
from app.ocr.base import get_ocr_engine
from app.ocr.document import DocumentLoader
from app.ocr.paddle import PaddleOcrEngine
from tests.paddle_samples import (
    REAL_REC_BOXES,
    REAL_REC_POLYS,
    REAL_REC_SCORES,
    REAL_REC_TEXTS,
    FakeOcrResultObject,
    real_page_payload,
)


class _FakePredictor:
    """Prédicteur PaddleOCR factice piloté par le test."""

    def __init__(self, results: list[object] = None) -> None:
        self.results = list(results or [])
        self.predict_calls = 0
        self.last_array = None

    def predict(self, array) -> list[object]:
        self.predict_calls += 1
        self.last_array = array
        return self.results


def _install_fake_paddleocr(monkeypatch, predictor) -> None:
    """Injecte un faux module ``paddleocr`` dans ``sys.modules``.

    Le module expose ``PaddleOCR``, constructeur retournant le prédicteur.
    """
    fake_module = types.ModuleType("paddleocr")

    class _FakePaddleOCR:
        def __init__(self, *args, **kwargs) -> None:
            pass

    fake_module.PaddleOCR = lambda *a, **k: predictor  # noqa: E731
    monkeypatch.setitem(sys.modules, "paddleocr", fake_module)


def _image() -> Image.Image:
    """Retourne une image RGB minimale."""
    return Image.new("RGB", (8, 8), "white")


class TestPaddleOcrEngine:
    def test_get_predictor_is_lazy_and_cached(self, monkeypatch) -> None:
        calls = {"count": 0}

        class _CountingPredictor:
            def __init__(self) -> None:
                calls["count"] += 1

        _install_fake_paddleocr(monkeypatch, _CountingPredictor())
        engine = PaddleOcrEngine(lang="fr")

        assert engine._ocr is None  # aucun téléchargement à l'import
        first = engine._get_predictor()
        second = engine._get_predictor()
        assert first is second
        assert calls["count"] == 1
        assert engine._ocr is not None

    def test_initialization_failure_raises_ocr_error(self, monkeypatch) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("réseau indisponible")

        fake_module = types.ModuleType("paddleocr")
        fake_module.PaddleOCR = _boom
        monkeypatch.setitem(sys.modules, "paddleocr", fake_module)

        engine = PaddleOcrEngine(lang="fr")
        with pytest.raises(OcrEngineError, match="initialiser PaddleOCR"):
            engine._get_predictor()

    # --- Structure réelle de PaddleOCR 3.x (résultats sous la clé « res ») ---

    def test_recognize_parses_real_paddle_structure(self, monkeypatch) -> None:
        """Test 1 : l'adaptateur convertit la structure réelle en OcrResult."""
        predictor = _FakePredictor(results=[FakeOcrResultObject()])
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        # Test 2 : les textes de ``rec_texts`` sont réellement exploitables.
        assert result.texts == REAL_REC_TEXTS
        assert "Numéro de facture : FAC-2026-0042" in result.texts
        # Test 3 : les scores sont récupérés et alignés sur les textes.
        assert result.scores == pytest.approx(REAL_REC_SCORES)
        assert len(result.scores) == len(result.texts)
        # Test 4 : les boîtes sont conservées, une par texte.
        assert len(result.boxes) == len(result.texts)
        assert result.boxes[0] == tuple(float(v) for v in REAL_REC_BOXES[0])
        assert result.page_index == 0

    def test_recognize_reads_nested_res_not_root(self, monkeypatch) -> None:
        """Garde-fou du bug corrigé : ``rec_texts`` n'est pas à la racine.

        ``page.json`` vaut ``{"res": {...}}`` : lire ``rec_texts`` à la racine
        renvoyait systématiquement zéro texte, quelle que soit la facture.
        """
        payload = FakeOcrResultObject().json

        assert "rec_texts" not in payload
        assert "rec_texts" in payload["res"]

        predictor = _FakePredictor(results=[FakeOcrResultObject()])
        _install_fake_paddleocr(monkeypatch, predictor)

        assert PaddleOcrEngine(lang="fr").recognize(_image()).texts

    def test_recognize_accepts_plain_mapping_page(self, monkeypatch) -> None:
        """Une page dict (sans propriété ``json``) reste exploitable."""
        predictor = _FakePredictor(results=[{"res": real_page_payload()}])
        _install_fake_paddleocr(monkeypatch, predictor)

        result = PaddleOcrEngine(lang="fr").recognize(_image())

        assert result.texts == REAL_REC_TEXTS

    def test_recognize_falls_back_to_polygons_for_boxes(self, monkeypatch) -> None:
        """Test 4 bis : sans ``rec_boxes``, les polygones donnent les boîtes."""
        payload = real_page_payload()
        payload.pop("rec_boxes")
        predictor = _FakePredictor(results=[{"res": payload}])
        _install_fake_paddleocr(monkeypatch, predictor)

        result = PaddleOcrEngine(lang="fr").recognize(_image())

        xs = [point[0] for point in REAL_REC_POLYS[0]]
        ys = [point[1] for point in REAL_REC_POLYS[0]]
        assert result.boxes[0] == (min(xs), min(ys), max(xs), max(ys))

    def test_recognize_without_boxes_yields_placeholder_boxes(
        self, monkeypatch
    ) -> None:
        """Aucune position disponible : boîtes neutres, alignées sur les textes."""
        payload = real_page_payload()
        payload.pop("rec_boxes")
        payload.pop("rec_polys")
        payload.pop("dt_polys")
        predictor = _FakePredictor(results=[{"res": payload}])
        _install_fake_paddleocr(monkeypatch, predictor)

        result = PaddleOcrEngine(lang="fr").recognize(_image())

        assert result.texts == REAL_REC_TEXTS
        assert result.boxes == [(0.0, 0.0, 0.0, 0.0)] * len(REAL_REC_TEXTS)

    def test_recognize_handles_missing_scores(self, monkeypatch) -> None:
        """Test 3 bis : des scores incomplets n'amputent pas les textes."""
        payload = real_page_payload()
        payload["rec_scores"] = payload["rec_scores"][:2]
        predictor = _FakePredictor(results=[{"res": payload}])
        _install_fake_paddleocr(monkeypatch, predictor)

        result = PaddleOcrEngine(lang="fr").recognize(_image())

        assert len(result.scores) == len(result.texts)
        assert result.scores[-1] == 0.0

    def test_recognize_page_without_text(self, monkeypatch) -> None:
        """Test 5 : une page vide donne un résultat vide, sans exception."""
        payload = real_page_payload()
        payload.update({"rec_texts": [], "rec_scores": [], "rec_boxes": []})
        predictor = _FakePredictor(results=[{"res": payload}])
        _install_fake_paddleocr(monkeypatch, predictor)

        result = PaddleOcrEngine(lang="fr").recognize(_image())

        assert result.texts == []
        assert result.scores == []
        assert result.boxes == []
        assert result.confidence() == 0.0

    def test_recognize_skips_non_dict_payload(self, monkeypatch) -> None:
        predictor = _FakePredictor(results=[["texte brut"]])
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        assert result.texts == []
        assert result.scores == []

    def test_recognize_accepts_legacy_flat_payload(self, monkeypatch) -> None:
        """Forme à plat (PaddleOCR antérieur) : tolérée, sans clé ``res``."""
        predictor = _FakePredictor(
            results=[
                types.SimpleNamespace(
                    json={
                        "rec_texts": ["Total HT", "100,00 €"],
                        "rec_scores": [0.99, 0.95],
                    }
                )
            ]
        )
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        assert result.texts == ["Total HT", "100,00 €"]
        assert result.scores == [0.99, 0.95]
        assert result.page_index == 0

    def test_recognize_aggregates_multiple_pages(self, monkeypatch) -> None:
        predictor = _FakePredictor(
            results=[
                types.SimpleNamespace(
                    json={"res": {"rec_texts": ["a"], "rec_scores": [0.9]}}
                ),
                types.SimpleNamespace(
                    json={"res": {"rec_texts": ["b"], "rec_scores": [0.8]}}
                ),
            ]
        )
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        assert result.texts == ["a", "b"]
        assert result.scores == [0.9, 0.8]

    def test_recognize_inference_failure_raises_ocr_error(self, monkeypatch) -> None:
        """Test 6 : une erreur du moteur remonte proprement au pipeline."""
        class _BoomPredictor:
            def predict(self, array) -> list[object]:
                raise ValueError("mauvaise entrée")

        _install_fake_paddleocr(monkeypatch, _BoomPredictor())
        engine = PaddleOcrEngine(lang="fr")

        with pytest.raises(OcrEngineError, match="reconnaissance OCR"):
            engine.recognize(_image())

    def test_image_is_passed_as_bgr_array(self, monkeypatch) -> None:
        """PaddleX lit les tableaux en BGR (``ReadImage(format="BGR")``)."""
        predictor = _FakePredictor(results=[])
        _install_fake_paddleocr(monkeypatch, predictor)
        image = Image.new("RGB", (2, 2), (10, 20, 30))  # R=10, G=20, B=30

        PaddleOcrEngine(lang="fr").recognize(image)

        array = predictor.last_array
        assert array.shape == (2, 2, 3)
        assert tuple(int(v) for v in array[0][0]) == (30, 20, 10)

    def test_non_rgb_image_is_converted(self, monkeypatch) -> None:
        predictor = _FakePredictor(results=[])
        _install_fake_paddleocr(monkeypatch, predictor)

        PaddleOcrEngine(lang="fr").recognize(Image.new("L", (3, 3), 128))

        assert predictor.last_array.shape == (3, 3, 3)


@pytest.mark.skipif(
    not os.environ.get("SMARTINVOICE_REAL_OCR"),
    reason=(
        "Intégration avec le vrai moteur PaddleOCR (modèles à télécharger, "
        "plusieurs secondes) : activer avec SMARTINVOICE_REAL_OCR=1."
    ),
)
class TestRealPaddleOcrEngine:
    """Vérifie la structure de la bibliothèque réellement installée.

    Ces tests sont la contrepartie des échantillons figés : ils échouent si une
    montée de version de PaddleOCR change la forme de la sortie (c'est
    exactement ce qui avait rendu le moteur muet).
    """

    def test_real_engine_returns_texts_scores_and_boxes(self) -> None:
        from pathlib import Path

        from tests.conftest import ROOT

        image = Image.open(Path(ROOT) / "datasets" / "fr_invoice.png")
        result = PaddleOcrEngine(lang="fr").recognize(image)

        assert result.texts, "le moteur réel ne doit pas renvoyer zéro texte"
        assert len(result.scores) == len(result.texts)
        assert len(result.boxes) == len(result.texts)
        assert result.confidence() > 0.5
        assert any("FAC-2026-0042" in text for text in result.texts)
        assert any(box != (0.0, 0.0, 0.0, 0.0) for box in result.boxes)
        # Les libellés français accentués doivent être lus tels quels : la
        # police du jeu de données doit couvrir « é/è/à/ç » (sinon l'extraction
        # par libellé ne trouve plus « Date d'émission », « Échéance »...).
        joined = " ".join(result.texts)
        assert "Numéro de facture" in joined
        assert "Échéance" in joined

    def test_real_engine_feeds_the_full_pipeline(self, session, tmp_path) -> None:
        """Un vrai document, un vrai moteur : la facture doit être analysable."""
        from app.models.enums import InvoiceStatus
        from app.services.ocr_service import OcrService
        from app.storage.local import LocalStorage
        from tests.conftest import ROOT, make_invoice, make_supplier

        storage = LocalStorage(tmp_path)
        with open(f"{ROOT}/datasets/fr_invoice.png", "rb") as handle:
            relative = storage.save(handle.read(), suffix=".png")

        supplier = make_supplier(session)
        session.flush()
        invoice = make_invoice(session, supplier.id, invoice_number="REAL-OCR-1")
        invoice.file_path = relative
        invoice.content_type = "image/png"
        session.flush()

        result = OcrService(session, storage).process(invoice)

        assert result.status is InvoiceStatus.TO_REVIEW, result.error_message
        data = result.extracted_data
        assert data["general"]["invoice_number"] == "FAC-2026-0042"
        assert data["general"]["issue_date"] == "2026-03-15"
        assert data["financial"]["total_incl_tax"] == "477.48"
        assert data["financial"]["tax_amount"] == "79.58"
        assert len(data["lines"]) == 3
        assert result.ocr_confidence_score > 0.9

    def test_real_output_still_nests_results_under_res(self) -> None:
        """La forme figée dans ``tests/paddle_samples.py`` est toujours exacte."""
        import numpy as np
        from paddleocr import PaddleOCR

        predictor = PaddleOCR(
            lang="fr",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        array = np.zeros((64, 256, 3), dtype="uint8")
        pages = predictor.predict(array)

        payload = pages[0].json
        assert set(payload) == {"res"}
        assert "rec_texts" in payload["res"]
        assert "rec_scores" in payload["res"]


class TestDocumentLoader:
    def _invoice(self, session, *, content_type: str = "application/pdf"):
        """Facture sans fichier réel : le chemin est librement contrôlé."""
        from app.models.invoice import Invoice

        return Invoice(
            file_path="invoices/2026/08/test" + (".pdf" if content_type == "application/pdf" else ".jpg"),
            content_type=content_type,
            invoice_number="FAC-LOAD",
            supplier_id=None,
        )

    def test_missing_file_path_raises(self, session) -> None:
        from app.storage.local import LocalStorage

        invoice = self._invoice(session)
        invoice.file_path = None
        loader = DocumentLoader(LocalStorage("/tmp"))

        with pytest.raises(DocumentNotFoundError):
            loader.load_images(invoice)

    def test_missing_file_on_disk_raises(self, session, tmp_path) -> None:
        from app.storage.local import LocalStorage

        invoice = self._invoice(session)
        loader = DocumentLoader(LocalStorage(tmp_path))

        with pytest.raises(DocumentNotFoundError):
            loader.load_images(invoice)

    def test_renders_pdf_to_images(self, session, tmp_path) -> None:
        import io

        import pypdfium2 as pdfium
        from app.storage.local import LocalStorage

        buf = io.BytesIO()
        doc = pdfium.PdfDocument.new()
        doc.new_page(width=612, height=792)
        doc.save(buf)
        doc.close()

        storage = LocalStorage(tmp_path)
        rel = storage.save(buf.getvalue(), suffix=".pdf")
        invoice = self._invoice(session)
        invoice.file_path = rel

        images = DocumentLoader(storage).load_images(invoice)

        assert len(images) == 1
        assert images[0].mode == "RGB"

    def test_corrupt_pdf_raises(self, session, tmp_path) -> None:
        from app.storage.local import LocalStorage

        storage = LocalStorage(tmp_path)
        rel = storage.save(b"%PDF-1.4\n%%EOF", suffix=".pdf")
        invoice = self._invoice(session)
        invoice.file_path = rel

        with pytest.raises(OcrEngineError, match="ouvrir le PDF"):
            DocumentLoader(storage).load_images(invoice)

    def test_pdf_render_failure_raises(self, session, tmp_path, monkeypatch) -> None:
        from app.storage.local import LocalStorage

        storage = LocalStorage(tmp_path)
        rel = storage.save(b"%PDF-mock", suffix=".pdf")
        invoice = self._invoice(session)
        invoice.file_path = rel

        class _FakeDocument:
            def __init__(self, content) -> None:
                pass

            def __iter__(self):
                return iter([_FakePage()])

            def close(self) -> None:
                pass

        class _FakePage:
            def render(self, **kwargs):
                raise RuntimeError("échec rendu")

        fake_pdfium = types.SimpleNamespace(PdfDocument=_FakeDocument)
        monkeypatch.setitem(sys.modules, "pypdfium2", fake_pdfium)

        with pytest.raises(OcrEngineError, match="rendre le PDF"):
            DocumentLoader(storage).load_images(invoice)

    def test_loads_single_image(self, session, tmp_path) -> None:
        import io

        from PIL import Image as PILImage
        from app.storage.local import LocalStorage

        buf = io.BytesIO()
        PILImage.new("RGB", (10, 10), "white").save(buf, format="JPEG")

        storage = LocalStorage(tmp_path)
        rel = storage.save(buf.getvalue(), suffix=".jpg")
        invoice = self._invoice(session, content_type="image/jpeg")
        invoice.file_path = rel

        images = DocumentLoader(storage).load_images(invoice)

        assert len(images) == 1

    def test_corrupt_image_raises(self, session, tmp_path) -> None:
        from app.storage.local import LocalStorage

        storage = LocalStorage(tmp_path)
        rel = storage.save(b"\xff\xd8\xff\xe0" + b"\x00" * 16, suffix=".jpg")
        invoice = self._invoice(session, content_type="image/jpeg")
        invoice.file_path = rel

        with pytest.raises(OcrEngineError, match="image du document"):
            DocumentLoader(storage).load_images(invoice)


class TestGetOcrEngine:
    def test_returns_paddle_engine(self) -> None:
        from app.ocr.paddle import PaddleOcrEngine

        engine = get_ocr_engine()
        assert isinstance(engine, PaddleOcrEngine)
