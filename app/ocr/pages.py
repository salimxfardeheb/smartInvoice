"""Détection des pages d'annexe d'un document multi-pages.

Une « annexe » regroupe le contenu complémentaire d'une facture (conditions
générales, plans, pièces jointes) qui ne porte pas de données de facturation.
Elle est conservée à titre de preuve visuelle mais est exclue de l'extraction
des champs et des lignes (seules les pages « principales » comptent).
"""

from __future__ import annotations

_ANNEX_MARKERS = (
    "annexe",
    "annex",
    "appendix",
    "pièce jointe",
    "piece jointe",
    "pièce(s) jointe(s)",
    "attachment",
    "conditions générales",
    "conditions generales",
    "termes et conditions",
    "terme et condition",
    "terms and conditions",
    "terms & conditions",
    "certificat de conformité",
    "certificat",
    "bon de livraison",
)

# Marqueurs suffisamment génériques pour ne pas rejeter la page principale : on
# traite aussi comme annexe une page récapitulative du DEVIS remplit ces mots.
# Le libellé « page N/M » (facultatif) n'est pas un marqueur d'annexe.


def is_annex(texts: list[str]) -> bool:
    """Indique si une page constitue une annexe (d'après son texte).

    Une page est classée annexe dès qu'elle contient un marqueur d'annexe
    (conditions générales, pièce jointe, bon de livraison...).
    """
    joined = " ".join(texts).lower()
    return any(marker in joined for marker in _ANNEX_MARKERS)


def main_pages(results: list[object]) -> list[tuple[int, object]]:
    """Retourne les pages principales ``[(index, résultat)]`` (hors annexes).

    ``results`` est une liste d'objets exposant ``texts``. Les pages annexes
    sont exclues de l'extraction (champs, lignes) tout en restant conservées
    comme preuve visuelle.
    """
    return [
        (index, page) for index, page in enumerate(results) if not is_annex(page.texts)
    ]