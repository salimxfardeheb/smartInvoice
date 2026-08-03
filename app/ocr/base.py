"""Contrat du moteur OCR et fabrique du moteur configuré.

Le moteur est abstrait (:class:`OcrEngine`) pour que le pipeline puisse être
testé sans instancier un moteur de production (téléchargement de modèles et
exécution GPU/CPU coûteux). La fabrique :func:`get_ocr_engine` retourne
l'implémentation choisie par la configuration ``ocr_engine``
(``paddle`` par défaut, ``tesseract`` en moteur secondaire), instanciée
paresseusement et mise en cache.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image

# Type d'une boîte englobante : (gauche, haut, droite, bas) en pixels.
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class OcrResult:
    """Résultat de reconnaissance d'une page.

    Attributs:
        texts: textes reconnus, dans l'ordre de lecture (bas → haut).
        scores: score de confiance (0..1) de chaque texte (même ordre).
        page_index: index de la page traitée (0-based).
        boxes: boîtes englobantes optionnelles, une par texte (même ordre).
    """

    texts: list[str]
    scores: list[float]
    page_index: int
    boxes: list[BBox] = field(default_factory=list)

    def confidence(self) -> float:
        """Confiance moyenne de la page (0.0 si aucun texte)."""
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)


class OcrEngine(ABC):
    """Interface du moteur de reconnaissance optique de caractères."""

    @abstractmethod
    def recognize(self, image: Image.Image) -> OcrResult:
        """Reconnaît le texte d'une image et retourne textes + confiances."""


@lru_cache
def get_ocr_engine(engine: str | None = None) -> OcrEngine:
    """Retourne le moteur OCR configuré (``paddle`` ou ``tesseract``).

    Le résultat est mis en cache : l'initialisation du moteur (et le
    téléchargement des modèles au premier appel pour PaddleOCR) ne doit avoir
    lieu qu'une seule fois par processus.
    """
    from app.core.config import get_settings

    name = engine or get_settings().ocr_engine
    if name == "tesseract":
        from app.ocr.tesseract import TesseractOcrEngine

        return TesseractOcrEngine()
    from app.ocr.paddle import PaddleOcrEngine

    return PaddleOcrEngine()
