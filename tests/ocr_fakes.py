"""Bouchons et échantillons partagés des tests OCR (phase 4).

Le moteur OCR de production (PaddleOCR) télécharge et exécute des modèles
coûteux : les tests injectent un :class:`FakeOcrEngine` dont le comportement
est contrôlé par le test (textes, scores, boîtes, voire résultats par page).

Ce bouchon implémente le **contrat** :class:`~app.ocr.base.OcrEngine` — il ne
reproduit *pas* l'API interne de PaddleOCR. La conversion de la sortie réelle
de PaddleOCR vers ce contrat est testée séparément, à partir d'échantillons
capturés sur le vrai moteur (``tests/paddle_samples.py``).
"""

from __future__ import annotations

from app.ocr.base import BBox, OcrEngine, OcrResult

SAMPLE_INVOICE_LINES = [
    "ACME SAS",
    "12 rue des Lilas",
    "75011 Paris",
    "Facture N° FAC-2026-001",
    "Date d'émission : 15/01/2026",
    "Échéance : 15/02/2026",
    "Bon de commande : PO-2026-0123",
    "Désignation     Qté    PU      Montant",
    "Câble HDMI 2   8,50    17,00",
    "Écran LED 1    149,00  149,00",
    "XLR-500 Câble audio 3    12,00   36,00",
    "Livraison  5,90 €",
    "Total HT  171,90 €",
    "TVA 20%  34,38 €",
    "Total TTC  206,28 €",
]

# Textes alignés colonne par colonne pour le parseur de lignes.
SAMPLE_LINE_ITEMS = [
    "Câble HDMI 2   8,50    17,00",
    "Écran LED 1    149,00  149,00",
    "XLR-500 Câble audio 3    12,00   36,00",
]


def stacked_boxes(texts: list[str]) -> list[BBox]:
    """Boîtes englobantes plausibles : une ligne de texte par bande horizontale.

    Le contrat :class:`OcrResult` prévoit une boîte par texte ; un bouchon qui
    n'en fournit aucune ne représenterait qu'une partie du contrat (le vrai
    moteur en fournit toujours).
    """
    return [
        (60.0, 60.0 + index * 46, 60.0 + 22 * max(len(text), 1), 100.0 + index * 46)
        for index, text in enumerate(texts)
    ]


class FakeOcrEngine(OcrEngine):
    """Moteur OCR de bouchon dont la sortie est pilotée par le test."""

    def __init__(
        self,
        *,
        texts: list[str] | None = None,
        scores: list[float] | None = None,
        boxes: list[BBox] | None = None,
        results: list[OcrResult] | None = None,
    ) -> None:
        self._texts = list(texts or [])
        self._scores = list(scores or [])
        self._boxes = list(boxes) if boxes is not None else stacked_boxes(self._texts)
        self._results = list(results or [])
        self.calls: list[OcrResult] = []

    def recognize(self, image) -> OcrResult:
        """Retourne un résultat figé (ou le ``i``-ème résultat fourni)."""
        if self._results:
            result = self._results[min(len(self.calls), len(self._results) - 1)]
        else:
            result = OcrResult(
                texts=list(self._texts),
                scores=list(self._scores),
                page_index=0,
                boxes=list(self._boxes),
            )
        self.calls.append(result)
        return result


def fake_engine_ok() -> FakeOcrEngine:
    """Moteur dont l'OCR « reconnaît » une facture type."""
    return FakeOcrEngine(
        texts=SAMPLE_INVOICE_LINES,
        scores=[0.95] * len(SAMPLE_INVOICE_LINES),
    )


def fake_engine_empty() -> FakeOcrEngine:
    """Moteur dont l'OCR ne reconnaît aucun texte (document illisible)."""
    return FakeOcrEngine(texts=[], scores=[])


def fake_engine_low_confidence() -> FakeOcrEngine:
    """Moteur reconnaissant un texte mais avec une confiance faible."""
    return FakeOcrEngine(
        texts=["Total HT 10,00", "Total TTC 12,00"],
        scores=[0.35, 0.35],
    )


def make_pdf_bytes() -> bytes:
    """Génère un PDF minimal valide (1 page) via pypdfium2."""
    import io

    import pypdfium2 as pdfium

    buf = io.BytesIO()
    doc = pdfium.PdfDocument.new()
    doc.new_page(width=612, height=792)
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def make_pdf_bytes_pages(n_pages: int = 2) -> bytes:
    """Génère un PDF minimal valide de ``n_pages`` pages."""
    import io

    import pypdfium2 as pdfium

    buf = io.BytesIO()
    doc = pdfium.PdfDocument.new()
    for _ in range(n_pages):
        doc.new_page(width=612, height=792)
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def fake_engine_pages(results: list[OcrResult]) -> FakeOcrEngine:
    """Moteur renvoyant un résultat par page (multi-pages)."""
    return FakeOcrEngine(results=results)
