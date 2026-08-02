"""Contrat du moteur OCR et fabrique du moteur configuré.

Le moteur est abstrait (:class:`OcrEngine`) pour que le pipeline puisse être
testé sans instancier PaddleOCR (téléchargement de modèles et exécution GPU/CPU
coûteux). La fabrique :func:`get_ocr_engine` retourne l'implémentation de
production (:class:`app.ocr.paddle.PaddleOcrEngine`), instanciée paresseusement
et mise en cache.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image


@dataclass(frozen=True)
class OcrResult:
    """Résultat de reconnaissance d'une page.

    Attributs:
        texts: textes reconnus, dans l'ordre de lecture (bas → haut).
        scores: score de confiance (0..1) de chaque texte (même ordre).
        page_index: index de la page traitée (0-based).
    """

    texts: list[str]
    scores: list[float]
    page_index: int

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
def get_ocr_engine() -> OcrEngine:
    """Retourne le moteur OCR de production (instanciation paresseuse).

    Le résultat est mis en cache : l'initialisation de PaddleOCR (et le
    téléchargement des modèles au premier appel) ne doit avoir lieu qu'une
    seule fois par processus.
    """
    from app.ocr.paddle import PaddleOcrEngine

    return PaddleOcrEngine()
