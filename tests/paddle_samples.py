"""Échantillons **capturés sur le vrai moteur** PaddleOCR 3.7.

Ces données ne sont pas inventées : elles proviennent de l'exécution de
``PaddleOCR(lang="fr").predict(...)`` (``paddleocr==3.7.0``,
``paddlepaddle==3.3.1``) sur ``datasets/fr_invoice.png``, réduite aux onze
premières détections utiles (en-tête de la facture + une ligne d'article
fragmentée en trois détections).

Deux caractéristiques de la sortie réelle sont reproduites fidèlement, car ce
sont elles que l'adaptateur doit absorber :

1. ``predict`` retourne une **liste** d'objets
   ``paddlex.inference.pipelines.ocr.result.OCRResult``, **sous-classes de
   ``dict``**, dont la propriété ``json`` vaut ``{"res": {...}}`` : les textes
   ne sont donc **pas** à la racine du JSON, mais sous la clé ``res``. Lire
   ``rec_texts`` à la racine renvoyait systématiquement zéro texte.
2. une ligne visuelle est découpée en plusieurs détections
   (« Câble HDMI 2m », « 8 u 8,50 € », « 68,00 € ») : c'est ce qui justifie la
   reconstruction des lignes de lecture (``app.ocr.rows``).

Le test d'intégration ``TestRealPaddleOcrEngine`` (activé par
``SMARTINVOICE_REAL_OCR=1``) revérifie cette forme contre la bibliothèque
installée : si une montée de version la change, il échoue.
"""

from __future__ import annotations

from typing import Any

REAL_REC_TEXTS: list[str] = [
    "ACME SAS",
    "12 rue des Lilas",
    "75011 Paris",
    "FACTURE",
    "Numéro de facture : FAC-2026-0042",
    "Date d'émission : 15/03/2026",
    "Échéance : 15/04/2026",
    "Bon de commande : PO-2026-0123",
    "Câble HDMI 2m",
    "8 u 8,50 €",
    "68,00 €",
]

REAL_REC_SCORES: list[float] = [
    0.999624,
    0.999674,
    0.991042,
    0.999986,
    0.974775,
    0.997153,
    0.969809,
    0.995145,
    0.999720,
    0.999281,
    0.999838,
]

# ``rec_boxes`` : [x1, y1, x2, y2] en pixels (entiers, comme le moteur les rend).
REAL_REC_BOXES: list[list[int]] = [
    [57, 61, 215, 89],
    [58, 107, 271, 138],
    [57, 152, 220, 183],
    [58, 245, 230, 280],
    [58, 297, 546, 327],
    [58, 343, 448, 373],
    [58, 386, 371, 420],
    [57, 433, 535, 465],
    [59, 574, 273, 602],
    [351, 571, 553, 606],
    [593, 571, 702, 606],
]

# ``rec_polys`` : quadrilatères [[x, y], ...] (non rectangulaires si incliné).
REAL_REC_POLYS: list[list[list[int]]] = [
    [[57, 61], [215, 61], [215, 89], [57, 89]],
    [[58, 107], [271, 107], [271, 138], [58, 138]],
    [[57, 152], [220, 152], [220, 183], [57, 183]],
    [[58, 245], [230, 245], [230, 280], [58, 280]],
    [[58, 297], [546, 297], [546, 327], [58, 327]],
    [[58, 343], [448, 343], [448, 373], [58, 373]],
    [[58, 386], [371, 386], [371, 420], [58, 420]],
    [[57, 435], [535, 433], [535, 464], [57, 465]],
    [[59, 574], [273, 574], [273, 602], [59, 602]],
    [[351, 571], [553, 571], [553, 606], [351, 606]],
    [[593, 571], [702, 571], [702, 606], [593, 606]],
]


def real_page_payload() -> dict[str, Any]:
    """Contenu de ``page.json["res"]`` tel que PaddleOCR 3.7 le renvoie."""
    return {
        "input_path": None,
        "page_index": None,
        "model_settings": {
            "use_doc_preprocessor": False,
            "use_textline_orientation": False,
        },
        "dt_polys": [list(poly) for poly in REAL_REC_POLYS],
        "text_det_params": {
            "limit_side_len": 64,
            "limit_type": "min",
            "thresh": 0.3,
            "max_side_limit": 4000,
            "box_thresh": 0.6,
            "unclip_ratio": 1.5,
        },
        "text_type": "general",
        "textline_orientation_angles": [-1] * len(REAL_REC_TEXTS),
        "text_rec_score_thresh": 0.0,
        "return_word_box": False,
        "rec_texts": list(REAL_REC_TEXTS),
        "rec_scores": list(REAL_REC_SCORES),
        "rec_polys": [list(poly) for poly in REAL_REC_POLYS],
        "rec_boxes": [list(box) for box in REAL_REC_BOXES],
    }


class FakeOcrResultObject(dict):
    """Reproduit ``paddlex...OCRResult`` : un ``dict`` doté d'un ``.json``.

    Le vrai objet est une sous-classe de ``dict`` exposant les clés à plat,
    **et** une propriété ``json`` qui les imbrique sous ``res``. Les deux
    accès doivent mener au même résultat côté adaptateur.
    """

    def __init__(self) -> None:
        super().__init__(real_page_payload())

    @property
    def json(self) -> dict[str, Any]:
        return {"res": real_page_payload()}
