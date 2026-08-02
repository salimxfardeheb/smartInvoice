"""Tests unitaires des moteurs/chargeurs OCR (phase 4).

Couvre les chemins d'erreur et le parsing des résultats du moteur PaddleOCR
sans jamais instancier le vrai PaddleOCR (coûteux), ainsi que le chargement
des documents (rendu PDF, image, fichiers manquants/corrompus).
"""

from __future__ import annotations

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


class _FakePredictor:
    """Prédicteur PaddleOCR factice piloté par le test."""

    def __init__(self, results: list[object] = None) -> None:
        self.results = list(results or [])
        self.predict_calls = 0

    def predict(self, array) -> list[object]:
        self.predict_calls += 1
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

    def test_recognize_parses_dict_payload(self, monkeypatch) -> None:
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

    def test_recognize_skips_non_dict_payload(self, monkeypatch) -> None:
        predictor = _FakePredictor(results=[["texte brut"]])
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        assert result.texts == []
        assert result.scores == []

    def test_recognize_aggregates_multiple_pages(self, monkeypatch) -> None:
        predictor = _FakePredictor(
            results=[
                types.SimpleNamespace(
                    json={"rec_texts": ["a"], "rec_scores": [0.9]}
                ),
                types.SimpleNamespace(
                    json={"rec_texts": ["b"], "rec_scores": [0.8]}
                ),
            ]
        )
        _install_fake_paddleocr(monkeypatch, predictor)
        engine = PaddleOcrEngine(lang="fr")

        result = engine.recognize(_image())

        assert result.texts == ["a", "b"]
        assert result.scores == [0.9, 0.8]

    def test_recognize_inference_failure_raises_ocr_error(self, monkeypatch) -> None:
        class _BoomPredictor:
            def predict(self, array) -> list[object]:
                raise ValueError("mauvaise entrée")

        _install_fake_paddleocr(monkeypatch, _BoomPredictor())
        engine = PaddleOcrEngine(lang="fr")

        with pytest.raises(OcrEngineError, match="reconnaissance OCR"):
            engine.recognize(_image())


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
