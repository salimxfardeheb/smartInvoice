"""Implémentation du moteur OCR avec PaddleOCR (v3+).

PaddleOCR est initialisé paresseusement (au premier appel de :meth:`recognize`)
afin de ne pas bloquer l'import du module ni le démarrage de l'application
(le téléchargement des modèles peut être long). L'entrée est une image PIL,
convertie en ``numpy.ndarray`` pour ``predict``.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import OcrEngineError
from app.ocr.base import OcrEngine, OcrResult

logger = logging.getLogger(__name__)


class PaddleOcrEngine(OcrEngine):
    """Reconnaissance de texte via PaddleOCR (langue configurée)."""

    def __init__(self, *, lang: str | None = None) -> None:
        self.lang = lang or get_settings().ocr_lang
        self._ocr = None

    def _get_predictor(self):
        """Instancie PaddleOCR une seule fois (coûteux)."""
        if self._ocr is None:
            logger.info("PaddleOCR : initialisation du moteur (langue %s).", self.lang)
            try:
                from paddleocr import PaddleOCR

                self._ocr = PaddleOCR(
                    lang=self.lang,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except Exception as exc:  # échec d'initialisation / téléchargement
                logger.error(
                    "PaddleOCR : initialisation impossible : %s", exc, exc_info=True
                )
                raise OcrEngineError(
                    f"Impossible d'initialiser PaddleOCR : {exc}"
                ) from exc
            logger.info("PaddleOCR : moteur initialisé.")
        return self._ocr

    def recognize(self, image: Image.Image) -> OcrResult:
        """Reconnaît le texte d'une image et retourne textes + confiances."""
        try:
            predictor = self._get_predictor()
            array = np.asarray(image)
            results = predictor.predict(array)
        except OcrEngineError:
            raise
        except Exception as exc:  # tout autre échec d'inférence
            logger.error(
                "PaddleOCR : échec de la reconnaissance : %s", exc, exc_info=True
            )
            raise OcrEngineError(f"Échec de la reconnaissance OCR : {exc}") from exc

        texts: list[str] = []
        scores: list[float] = []
        for page in results:
            payload = page.json if hasattr(page, "json") else page
            if not isinstance(payload, dict):
                continue
            texts.extend(str(t) for t in payload.get("rec_texts", []))
            scores.extend(float(s) for s in payload.get("rec_scores", []))
        if not texts:
            logger.warning("PaddleOCR : aucun texte reconnu sur la page.")
        return OcrResult(texts=texts, scores=scores, page_index=0)
