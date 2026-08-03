"""Politique de confiance par champ de l'extraction OCR.

Associe à chaque champ extrait la confiance du texte OCR qui l'a produit.
La confiance d'un champ est celle de la ligne contenant son libellé (la même
règle que :class:`app.ocr.extractor.FieldExtractor`). Un champ non localisé
se voit attribuer ``None`` : il est réputé « incertain » et peut être signalé
par la politique si le champ est critique.
"""

from __future__ import annotations

from statistics import fmean

CRITICAL_FIELDS = (
    "invoice_number",
    "total_incl_tax",
    "total_excl_tax",
    "tax_amount",
)


def overall(scores: list[float]) -> float:
    """Confiance moyenne des textes (0.0 si aucun score)."""
    if not scores:
        return 0.0
    return fmean(scores)


def _best_line_index(line_texts: list[str], labels: tuple[str, ...]) -> int | None:
    """Index de la première ligne contenant un libellé du champ."""
    for i, line in enumerate(line_texts):
        lowered = line.lower()
        if any(label in lowered for label in labels):
            return i
    return None


def field_confidence(
    line_texts: list[str],
    scores: list[float],
    field_labels: dict[str, tuple[str, ...]],
) -> dict[str, float | None]:
    """Confiance par champ : score de la ligne contenant son libellé.

    Retourne un dictionnaire champ → confiance (``None`` si le champ n'a pas
    pu être localisé).
    """
    result: dict[str, float | None] = {}
    for field, labels in field_labels.items():
        index = _best_line_index(line_texts, labels)
        result[field] = scores[index] if index is not None and index < len(scores) else None
    return result


def flag_low_confidence(
    per_field: dict[str, float | None],
    overall_score: float,
    threshold: float,
) -> list[str]:
    """Champs critiques sous le seuil (ou non localisés) qui méritent alerte.

    Retourne la liste des champs à signaler. Un champ critique non localisé
    (``None``) est toujours signalé ; sinon il est signalé si sa confiance
    tombe sous le seuil. La confiance globale sous le seuil signale également
    les champs critiques.
    """
    flagged = [
        field
        for field in CRITICAL_FIELDS
        if (per_field.get(field) is None or per_field.get(field) < threshold)
    ]
    if overall_score < threshold:
        for field in CRITICAL_FIELDS:
            if field not in flagged:
                flagged.append(field)
    return flagged
