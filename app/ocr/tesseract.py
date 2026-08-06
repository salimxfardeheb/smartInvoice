"""Implémentation du moteur OCR secondaire avec Tesseract.

Tesseract (via ``pytesseract``) est importé paresseusement afin de ne pas
bloquer l'import du module si le binaire Tesseract est absent. La
reconnaissance utilise le mode ``psm 6`` (bloc de texte uniforme), adapté aux
pages de facture. Chaque texte est associé à sa boîte englobante et à sa
confiance, fournis par ``image_to_data``.
"""

from __future__ import annotations

import logging

from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import OcrEngineError
from app.ocr.base import OcrEngine, OcrResult

logger = logging.getLogger(__name__)


class TesseractOcrEngine(OcrEngine):
    """Reconnaissance de texte via Tesseract (langue configurée)."""

    def __init__(self, *, lang: str | None = None) -> None:
        self.lang = lang or get_settings().ocr_tesseract_lang
        self._pytesseract = None
        self._resolved_lang: str | None = None

    def _get_pytesseract(self):
        """Résout ``pytesseract`` une seule fois (échec → OcrEngineError)."""
        if self._pytesseract is None:
            try:
                import pytesseract

                self._pytesseract = pytesseract
            except Exception as exc:  # bibliothèque absente / binaire manquant
                logger.error("Tesseract : indisponible : %s", exc, exc_info=True)
                raise OcrEngineError(
                    f"Tesseract indisponible : {exc}"
                ) from exc
        return self._pytesseract

    def _resolve_lang(self) -> str:
        """Retourne une langue installée (repli sur ``eng`` si besoin).

        La détection via :func:`pytesseract.get_languages` est tolérante : si
        elle échoue ou ne référence pas la langue demandée, on bascule sur
        ``eng`` (ou la première langue installée).
        """
        if self._resolved_lang is not None:
            return self._resolved_lang
        try:
            langs = self._get_pytesseract().get_languages(config="")
        except Exception:
            langs = []
        if self.lang in langs:
            self._resolved_lang = self.lang
        elif langs:
            self._resolved_lang = "eng" if "eng" in langs else langs[0]
            logger.warning(
                "Tesseract : langue « %s » absente, repli sur « %s ».",
                self.lang,
                self._resolved_lang,
            )
        else:
            self._resolved_lang = self.lang
            logger.warning(
                "Tesseract : liste des langues installées indisponible, "
                "utilisation de « %s » telle quelle.",
                self.lang,
            )
        return self._resolved_lang

    def recognize(self, image: Image.Image) -> OcrResult:
        """Reconnaît le texte d'une image et retourne textes, confiances, boîtes."""
        try:
            tess = self._get_pytesseract()
            data = tess.image_to_data(
                image,
                lang=self._resolve_lang(),
                config="--psm 6",
                output_type=tess.Output.DICT,
            )
        except OcrEngineError:
            raise
        except Exception as exc:  # toute erreur d'inférence Tesseract
            logger.error(
                "Tesseract : échec de la reconnaissance : %s", exc, exc_info=True
            )
            raise OcrEngineError(f"Échec de la reconnaissance OCR : {exc}") from exc

        texts: list[str] = []
        scores: list[float] = []
        boxes: list[tuple[float, float, float, float]] = []
        raw_texts = data.get("text") or []
        raw_confs = data.get("conf") or []
        lefts = data.get("left") or []
        tops = data.get("top") or []
        widths = data.get("width") or []
        heights = data.get("height") or []
        for i in range(len(raw_texts)):
            text = (raw_texts[i] or "").strip()
            if not text:
                continue
            texts.append(text)
            try:
                conf = float(raw_confs[i])
            except (TypeError, ValueError):
                conf = -1.0
            scores.append(0.0 if conf < 0 else conf / 100.0)
            try:
                boxes.append(
                    (
                        float(lefts[i]),
                        float(tops[i]),
                        float(lefts[i]) + float(widths[i]),
                        float(tops[i]) + float(heights[i]),
                    )
                )
            except (TypeError, ValueError, IndexError):
                boxes.append((0.0, 0.0, 0.0, 0.0))
        if not texts:
            logger.warning("Tesseract : aucun texte reconnu sur la page.")
        return OcrResult(texts=texts, scores=scores, page_index=0, boxes=boxes)
