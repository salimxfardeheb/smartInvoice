"""Service OCR : pipeline complet (chargement → OCR → nettoyage → structuration).

Le pipeline se déroule ainsi :
1. la facture doit être « Déposée » (ou « Erreur système » pour une reprise) ;
2. passage en « En cours d'analyse » ;
3. chargement du document (PDF rendu page à page, image telle quelle) ;
4. reconnaissance par le moteur OCR (PaddleOCR) ;
5. nettoyage et structuration (champs généraux, financiers, lignes) ;
6. persistance (``extracted_data``, score de confiance, colonnes métier,
   lignes de facture) et éventuelle anomalie de qualité ;
7. passage en « À vérifier ».

En cas de document illisible, de fichier manquant ou d'échec du moteur, la
facture passe en « Erreur système » avec le message conservé, et le statut est
retourné (aucune exception n'est levée pour ces cas attendus).
"""

from __future__ import annotations

from statistics import fmean

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    DocumentIllegibleError,
    DocumentNotFoundError,
    InvalidStatusTransitionError,
    OcrEngineError,
)
from app.models.anomaly import Anomaly
from app.models.enums import AnomalyCategory, AnomalySeverity, InvoiceStatus
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.ocr.base import OcrEngine, OcrResult, get_ocr_engine
from app.ocr.cleaners import clean_text
from app.ocr.document import DocumentLoader
from app.ocr.extractor import FieldExtractor
from app.ocr.lines import InvoiceLineParser
from app.ocr.schema import OcrExtraction
from app.repositories import (
    AnomalyRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from app.services.invoice_service import InvoiceService
from app.storage.base import Storage

# Erreurs « attendues » du pipeline : elles marquent la facture en erreur
# système et le pipeline se termine proprement.
_EXPECTED_ERRORS = (DocumentIllegibleError, DocumentNotFoundError, OcrEngineError)


class OcrService:
    """Orchestration du pipeline OCR d'une facture."""

    def __init__(
        self,
        db: Session,
        storage: Storage,
        *,
        engine: OcrEngine | None = None,
        invoice_service: InvoiceService | None = None,
    ) -> None:
        self.db = db
        self.storage = storage
        self.engine = engine or get_ocr_engine()
        self.invoice_service = invoice_service or InvoiceService(db, storage)
        self.invoices: InvoiceRepository = self.invoice_service.invoices
        self.lines: InvoiceLineRepository = InvoiceLineRepository(db)
        self.anomalies: AnomalyRepository = AnomalyRepository(db)
        self.loader = DocumentLoader(storage)
        self.extractor = FieldExtractor()
        self.line_parser = InvoiceLineParser()

    # --- Pipeline ---------------------------------------------------------------

    def process(self, invoice: Invoice) -> Invoice:
        """Exécute le pipeline OCR complet et met à jour la facture.

        Retourne la facture mise à jour : statut « À vérifier » en cas de
        succès, « Erreur système » (avec ``error_message``) en cas d'échec
        attendu. Lève :class:`InvalidStatusTransitionError` si la facture
        n'est pas dans un état analysable.
        """
        if invoice.status not in (
            InvoiceStatus.SUBMITTED,
            InvoiceStatus.SYSTEM_ERROR,
        ):
            raise InvalidStatusTransitionError(
                "La facture doit être « Déposée » ou « Erreur système » pour "
                "être analysée."
            )
        if invoice.status is InvoiceStatus.SYSTEM_ERROR:
            self.invoice_service.transition_status(invoice, InvoiceStatus.SUBMITTED)
        self.invoice_service.transition_status(invoice, InvoiceStatus.ANALYZING)

        try:
            result, confidence = self._run(invoice)
        except _EXPECTED_ERRORS as exc:
            self.invoice_service.transition_status(
                invoice, InvoiceStatus.SYSTEM_ERROR, reason=str(exc)
            )
            return invoice

        self._persist(invoice, result, confidence)
        self.invoice_service.transition_status(invoice, InvoiceStatus.TO_REVIEW)
        return invoice

    def _run(self, invoice: Invoice) -> tuple[OcrExtraction, float]:
        """Charge, reconnaît, nettoie et structure un document."""
        images = self.loader.load_images(invoice)
        results = [self.engine.recognize(image) for image in images]
        texts, confidence = self._aggregate(results)
        if not texts:
            raise DocumentIllegibleError(
                "Aucun texte exploitable n'a été extrait du document."
            )

        lines = [clean_text(text) for text in texts if clean_text(text)]
        general, financial = self.extractor.extract(lines)
        items = self.line_parser.parse(lines)
        return (
            OcrExtraction(general=general, financial=financial, lines=items),
            confidence,
        )

    @staticmethod
    def _aggregate(results: list[OcrResult]) -> tuple[list[str], float]:
        """Concatène les textes des pages et calcule la confiance moyenne."""
        texts = [text for result in results for text in result.texts]
        scores = [score for result in results for score in result.scores]
        confidence = fmean(scores) if scores else 0.0
        return texts, confidence

    # --- Persistance --------------------------------------------------------------

    def _persist(self, invoice: Invoice, result: OcrExtraction, confidence: float) -> None:
        """Écrit l'extraction, le score et les lignes sur la facture."""
        # Idempotence : supprime les lignes et anomalies d'une analyse passée.
        existing_lines: list[InvoiceLine] = self.lines.list_by_invoice(invoice.id)
        existing_anomalies: list[Anomaly] = self.anomalies.list_by_invoice(invoice.id)
        for line in existing_lines:
            self.lines.delete(line)
        for anomaly in existing_anomalies:
            self.anomalies.delete(anomaly)
        self.db.flush()

        updates: dict = {
            "extracted_data": result.model_dump(mode="json"),
            "ocr_confidence_score": confidence,
        }
        general, financial = result.general, result.financial
        if invoice.issue_date is None and general.issue_date is not None:
            updates["issue_date"] = general.issue_date
        if invoice.due_date is None and general.due_date is not None:
            updates["due_date"] = general.due_date
        if invoice.currency is None and general.currency is not None:
            updates["currency"] = general.currency
        if financial.total_excl_tax is not None:
            updates["total_excl_tax"] = financial.total_excl_tax
        if financial.tax_amount is not None:
            updates["tax_amount"] = financial.tax_amount
        if financial.total_incl_tax is not None:
            updates["total_incl_tax"] = financial.total_incl_tax
        if financial.discount is not None:
            updates["discount"] = financial.discount
        if financial.shipping_fees is not None:
            updates["shipping_fees"] = financial.shipping_fees
        self.invoices.update(invoice, **updates)

        for item in result.lines:
            self.lines.create(invoice_id=invoice.id, **item.model_dump())

        if confidence < get_settings().ocr_confidence_threshold:
            self.anomalies.create(
                invoice_id=invoice.id,
                category=AnomalyCategory.OTHER,
                severity=AnomalySeverity.WARNING,
                message=(
                    "Score de confiance OCR faible : "
                    f"{confidence:.1%} (seuil "
                    f"{get_settings().ocr_confidence_threshold:.0%})."
                ),
                actual_value=f"{confidence:.3f}",
            )
