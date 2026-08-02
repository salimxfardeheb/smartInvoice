"""Bouchons et échantillons partagés des tests OCR (phase 4).

Le moteur OCR de production (PaddleOCR) télécharge et exécute des modèles
coûteux : les tests injectent un :class:`FakeOcrEngine` dont le comportement
est contrôlé par le test (textes, scores, voire résultats par page).
"""

from __future__ import annotations

from app.ocr.base import OcrEngine, OcrResult

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


class FakeOcrEngine(OcrEngine):
    """Moteur OCR de bouchon dont la sortie est pilotée par le test."""

    def __init__(
        self,
        *,
        texts: list[str] | None = None,
        scores: list[float] | None = None,
        results: list[OcrResult] | None = None,
    ) -> None:
        self._texts = list(texts or [])
        self._scores = list(scores or [])
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
