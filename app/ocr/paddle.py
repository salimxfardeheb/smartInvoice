"""Implémentation du moteur OCR avec PaddleOCR (v3+).

PaddleOCR est initialisé paresseusement (au premier appel de :meth:`recognize`)
afin de ne pas bloquer l'import du module ni le démarrage de l'application
(le téléchargement des modèles peut être long). L'entrée est une image PIL,
convertie en ``numpy.ndarray`` **BGR** pour ``predict`` : le pipeline OCR de
PaddleX lit les tableaux avec ``ReadImage(format="BGR")`` et suppose donc cet
ordre de canaux (celui d'OpenCV), là où Pillow travaille en RGB.

Structure de sortie réellement observée avec ``paddleocr==3.7.0`` (voir
``tests/paddle_samples.py``) : ``predict`` retourne une **liste** d'objets
``OCRResult`` (sous-classe de ``dict``) dont la propriété ``json`` vaut
``{"res": {...}}``. Les textes, scores et boîtes sont **imbriqués sous la clé
``res``** :

    {"res": {"rec_texts": [...], "rec_scores": [...],
             "rec_boxes": [[x1, y1, x2, y2], ...],
             "rec_polys": [[[x, y], ...], ...], "page_index": None, ...}}

L'adaptateur absorbe cette forme (ainsi que la forme à plat, sans ``res``, des
versions antérieures) et n'expose au pipeline que le contrat :class:`OcrResult`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import OcrEngineError
from app.ocr.base import BBox, OcrEngine, OcrResult

logger = logging.getLogger(__name__)

# Boîte « absente » : convention partagée avec le moteur Tesseract, le
# pipeline (``OcrService._build_layout``) l'interprète comme « pas de boîte ».
_NO_BOX: BBox = (0.0, 0.0, 0.0, 0.0)


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
        """Reconnaît le texte d'une image et retourne textes, confiances, boîtes."""
        try:
            predictor = self._get_predictor()
            results = predictor.predict(self._to_bgr_array(image))
        except OcrEngineError:
            raise
        except Exception as exc:  # tout autre échec d'inférence
            logger.error(
                "PaddleOCR : échec de la reconnaissance : %s", exc, exc_info=True
            )
            raise OcrEngineError(f"Échec de la reconnaissance OCR : {exc}") from exc

        return self._normalize(results)

    # --- Normalisation de la sortie PaddleOCR ---------------------------------

    @classmethod
    def _normalize(cls, results: Any) -> OcrResult:
        """Convertit la sortie brute de ``predict`` en :class:`OcrResult`."""
        texts: list[str] = []
        scores: list[float] = []
        boxes: list[BBox] = []
        page_index: int | None = None

        for page in cls._iter_pages(results):
            payload = cls._payload(page)
            if payload is None:
                continue
            if page_index is None:
                page_index = cls._page_index(payload)
            page_texts = [str(text) for text in _as_list(payload.get("rec_texts"))]
            if not page_texts:
                continue
            texts.extend(page_texts)
            scores.extend(cls._scores(payload, len(page_texts)))
            boxes.extend(cls._boxes(payload, len(page_texts)))

        if not texts:
            logger.warning("PaddleOCR : aucun texte reconnu sur la page.")
        return OcrResult(
            texts=texts,
            scores=scores,
            page_index=page_index or 0,
            boxes=boxes,
        )

    @staticmethod
    def _iter_pages(results: Any) -> list[Any]:
        """Retourne les pages de la sortie (une sortie unique est acceptée)."""
        if results is None:
            return []
        if isinstance(results, Mapping):  # sortie déjà « dépliée »
            return [results]
        if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
            return list(results)
        try:
            return list(results)  # itérable paresseux
        except TypeError:
            return []

    @staticmethod
    def _payload(page: Any) -> Mapping[str, Any] | None:
        """Retourne le dictionnaire porteur de ``rec_texts`` pour une page.

        Deux formes sont acceptées : la forme réelle de PaddleOCR 3.x
        (``page.json["res"]``, ou ``page["res"]``) et la forme à plat, où les
        clés sont à la racine. Toute autre forme est ignorée (``None``).
        """
        for candidate in (getattr(page, "json", None), page):
            if not isinstance(candidate, Mapping):
                continue
            nested = candidate.get("res")
            if isinstance(nested, Mapping) and "rec_texts" in nested:
                return nested
            if "rec_texts" in candidate:
                return candidate
        return None

    @staticmethod
    def _page_index(payload: Mapping[str, Any]) -> int | None:
        """Index de page fourni par PaddleOCR (``None`` pour une image seule)."""
        value = payload.get("page_index")
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _scores(payload: Mapping[str, Any], count: int) -> list[float]:
        """Confiances alignées sur les textes (0.0 pour une valeur manquante)."""
        raw = _as_list(payload.get("rec_scores"))
        scores: list[float] = []
        for index in range(count):
            try:
                scores.append(float(raw[index]))
            except (IndexError, TypeError, ValueError):
                scores.append(0.0)
        if len(raw) != count:
            logger.warning(
                "PaddleOCR : %s score(s) pour %s texte(s), alignement forcé.",
                len(raw),
                count,
            )
        return scores

    @classmethod
    def _boxes(cls, payload: Mapping[str, Any], count: int) -> list[BBox]:
        """Boîtes englobantes alignées sur les textes.

        ``rec_boxes`` fournit directement ``[x1, y1, x2, y2]`` ; à défaut, les
        polygones (``rec_polys`` puis ``dt_polys``) sont réduits à leur boîte
        englobante. Une boîte indisponible vaut ``(0, 0, 0, 0)``.
        """
        rects = _as_list(payload.get("rec_boxes"))
        polys = _as_list(payload.get("rec_polys")) or _as_list(payload.get("dt_polys"))
        boxes: list[BBox] = []
        for index in range(count):
            box = _NO_BOX
            if index < len(rects):
                box = cls._rect(rects[index]) or _NO_BOX
            if box is _NO_BOX and index < len(polys):
                box = cls._polygon(polys[index]) or _NO_BOX
            boxes.append(box)
        return boxes

    @staticmethod
    def _rect(value: Any) -> BBox | None:
        """Convertit ``[x1, y1, x2, y2]`` en boîte (``None`` si inexploitable)."""
        try:
            left, top, right, bottom = (float(coord) for coord in _as_list(value))
        except (TypeError, ValueError):
            return None
        return (min(left, right), min(top, bottom), max(left, right), max(top, bottom))

    @staticmethod
    def _polygon(value: Any) -> BBox | None:
        """Réduit un polygone ``[[x, y], ...]`` à sa boîte englobante."""
        xs: list[float] = []
        ys: list[float] = []
        for point in _as_list(value):
            coords = _as_list(point)
            if len(coords) < 2:
                return None
            try:
                xs.append(float(coords[0]))
                ys.append(float(coords[1]))
            except (TypeError, ValueError):
                return None
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    # --- Entrée ---------------------------------------------------------------

    @staticmethod
    def _to_bgr_array(image: Image.Image) -> np.ndarray:
        """Convertit une image PIL en tableau BGR contigu attendu par PaddleOCR."""
        rgb = image if image.mode == "RGB" else image.convert("RGB")
        return np.ascontiguousarray(np.asarray(rgb)[:, :, ::-1])


def _as_list(value: Any) -> list[Any]:
    """Liste des éléments de ``value`` (``[]`` si absent ou non itérable).

    Tolère les tableaux ``numpy`` renvoyés par PaddleOCR lorsque le résultat
    n'est pas passé par sa sérialisation JSON : un test de vérité direct sur un
    tableau lèverait ``ValueError``, d'où la conversion explicite.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return []
    try:
        return list(value)
    except TypeError:
        return []
