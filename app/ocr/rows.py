"""Reconstruction des lignes de lecture à partir des boîtes englobantes.

Un moteur OCR ne rend pas des « lignes de texte » : il rend des **fragments
positionnés**. Sur une facture tabulaire, une même ligne visuelle est presque
toujours découpée en plusieurs détections (« Câble HDMI 2m », « 8 u 8,50 € »,
« 68,00 € »), et un libellé est fréquemment séparé de sa valeur (« TVA 20% »
d'un côté, « 79,58 € » de l'autre). C'est vrai des deux moteurs : PaddleOCR
détecte par blocs, Tesseract (``image_to_data``) descend même au mot.

L'extracteur de champs et le parseur de lignes raisonnent, eux, sur des lignes
logiques : sans regroupement préalable, la TVA n'est jamais rattachée à son
montant et les lignes d'articles perdent leur désignation.

Ce module regroupe les fragments dont les bandes verticales se recouvrent, en
conservant l'ordre de lecture fourni par le moteur. Il est **indépendant du
moteur** : il n'utilise que le contrat :class:`~app.ocr.base.OcrResult`
(textes, scores, boîtes). Si le moteur ne fournit pas de boîtes, les textes
sont retournés inchangés.
"""

from __future__ import annotations

from statistics import fmean

from app.ocr.base import BBox

# Part du recouvrement vertical (rapportée à la plus petite hauteur) à partir
# de laquelle deux fragments sont considérés sur la même ligne visuelle.
_OVERLAP_RATIO = 0.5


def group_rows(
    texts: list[str],
    scores: list[float],
    boxes: list[BBox],
    *,
    overlap_ratio: float = _OVERLAP_RATIO,
) -> tuple[list[str], list[float]]:
    """Regroupe les fragments OCR en lignes de lecture.

    Retourne ``(textes, scores)`` où chaque texte est une ligne visuelle
    reconstituée (fragments joints par un espace, de gauche à droite) et son
    score la moyenne des confiances des fragments qui la composent.

    Les textes sont retournés **inchangés** lorsque le moteur ne fournit pas
    de boîte pour chaque fragment : le regroupement serait alors arbitraire.
    """
    if not texts or len(boxes) < len(texts):
        return list(texts), list(scores)

    rows: list[list[int]] = []
    band: tuple[float, float] | None = None
    for index in range(len(texts)):
        top, bottom = boxes[index][1], boxes[index][3]
        if band is not None and _same_row(band, (top, bottom), overlap_ratio):
            rows[-1].append(index)
            band = (min(band[0], top), max(band[1], bottom))
            continue
        rows.append([index])
        band = (top, bottom)

    grouped_texts: list[str] = []
    grouped_scores: list[float] = []
    for row in rows:
        ordered = sorted(row, key=lambda index: boxes[index][0])
        grouped_texts.append(" ".join(texts[index] for index in ordered))
        row_scores = [scores[index] for index in ordered if index < len(scores)]
        grouped_scores.append(fmean(row_scores) if row_scores else 0.0)
    return grouped_texts, grouped_scores


def _same_row(
    band: tuple[float, float], other: tuple[float, float], overlap_ratio: float
) -> bool:
    """Indique si deux bandes verticales appartiennent à la même ligne."""
    heights = (band[1] - band[0], other[1] - other[0])
    if min(heights) <= 0:  # boîte absente ou dégénérée : aucun regroupement
        return False
    overlap = min(band[1], other[1]) - max(band[0], other[0])
    return overlap > 0 and overlap >= overlap_ratio * min(heights)
