"""Service OCR : pipeline complet (chargement → OCR → nettoyage → structuration).

Le pipeline se déroule ainsi :
1. la facture doit être « Déposée » (ou « Erreur système » pour une reprise) ;
2. passage en « En cours d'analyse » ;
3. chargement du document (PDF rendu page à page, image telle quelle) ;
4. reconnaissance par le moteur OCR (PaddleOCR par défaut, Tesseract en
   alternative selon ``ocr_engine``) ;
5. classification des pages (annexes exclues de l'extraction) ;
6. nettoyage et structuration (champs généraux, financiers, lignes) ;
7. persistance (``extracted_data`` avec preuves visuelles : images de pages,
   boîtes englobantes, confiance par champ ; score global, colonnes métier,
   lignes de facture) et éventuelle anomalie de qualité ;
8. passage en « À vérifier ».

En cas de document illisible, de fichier manquant ou d'échec du moteur, la
facture passe en « Erreur système » avec le message conservé, et le statut est
retourné (aucune exception n'est levée pour ces cas attendus).
"""

from __future__ import annotations

import io
import logging
import time

from PIL import Image
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
from app.ocr.confidence import field_confidence, flag_low_confidence, overall
from app.ocr.document import DocumentLoader
from app.ocr.extractor import FIELD_LABELS, FieldExtractor
from app.ocr.lines import InvoiceLineParser
from app.ocr.pages import is_annex
from app.ocr.schema import OcrBox, OcrExtraction, OcrPage, OcrTextBlock
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

logger = logging.getLogger(__name__)


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

        logger.info(
            "OCR : début de l'analyse de la facture %s (moteur %s).",
            invoice.id,
            type(self.engine).__name__,
        )
        started = time.monotonic()
        try:
            result, confidence, images = self._run(invoice)
        except _EXPECTED_ERRORS as exc:
            logger.error(
                "OCR : échec de l'analyse de la facture %s après %.2f s : %s",
                invoice.id,
                time.monotonic() - started,
                exc,
                exc_info=True,
            )
            self.invoice_service.transition_status(
                invoice, InvoiceStatus.SYSTEM_ERROR, reason=str(exc)
            )
            return invoice
        except Exception:
            logger.exception(
                "OCR : erreur inattendue lors de l'analyse de la facture %s "
                "après %.2f s.",
                invoice.id,
                time.monotonic() - started,
            )
            raise

        self._persist(invoice, result, confidence, images)
        self.invoice_service.transition_status(invoice, InvoiceStatus.TO_REVIEW)
        logger.info(
            "OCR : analyse de la facture %s terminée en %.2f s "
            "(%s page(s), %s ligne(s), confiance %.1f%%).",
            invoice.id,
            time.monotonic() - started,
            len(result.pages),
            len(result.lines),
            confidence * 100,
        )
        return invoice

    def _run(self, invoice: Invoice) -> tuple[OcrExtraction, float, list[Image.Image]]:
        """Charge, reconnaît, nettoie et structure un document.

        Les pages annexes (conditions générales, pièces jointes...) sont
        exclues de l'extraction mais conservées comme preuve visuelle.
        """
        images = self.loader.load_images(invoice)
        logger.info(
            "OCR : facture %s, %s page(s) chargée(s) depuis le document.",
            invoice.id,
            len(images),
        )
        deadline = time.monotonic() + get_settings().ocr_pipeline_timeout_seconds
        results: list[OcrResult] = []
        for image in images:
            self._check_deadline(deadline)
            results.append(self.engine.recognize(image))
            self._check_deadline(deadline)

        pages = [
            OcrPage(
                page_index=i,
                texts=result.texts,
                scores=result.scores,
                is_annex=is_annex(result.texts),
                layout=self._build_layout(result),
            )
            for i, result in enumerate(results)
        ]

        main_texts: list[str] = []
        main_scores: list[float] = []
        for result, page in zip(results, pages):
            if page.is_annex:
                continue
            for text, score in zip(result.texts, result.scores):
                cleaned = clean_text(text)
                if cleaned:
                    main_texts.append(cleaned)
                    main_scores.append(score)

        annexes = sum(1 for page in pages if page.is_annex)
        if annexes:
            logger.info(
                "OCR : facture %s, %s page(s) annexe(s) exclue(s) de l'extraction.",
                invoice.id,
                annexes,
            )

        if not main_texts:
            raise DocumentIllegibleError(
                "Aucun texte exploitable n'a été extrait du document."
            )

        general, financial = self.extractor.extract(main_texts)
        items = self.line_parser.parse(main_texts, main_scores)
        per_field = field_confidence(main_texts, main_scores, FIELD_LABELS)
        extraction = OcrExtraction(
            general=general,
            financial=financial,
            lines=items,
            pages=pages,
            confidence=per_field,
        )
        return extraction, overall(main_scores), images

    @staticmethod
    def _build_layout(result: OcrResult) -> list[OcrTextBlock]:
        """Assemble les blocs texte d'une page (texte + confiance + boîte)."""
        blocks: list[OcrTextBlock] = []
        for i, text in enumerate(result.texts):
            box = None
            if i < len(result.boxes):
                left, top, right, bottom = result.boxes[i]
                if left or top or right or bottom:
                    box = OcrBox(left=left, top=top, right=right, bottom=bottom)
            blocks.append(
                OcrTextBlock(
                    text=text,
                    confidence=result.scores[i] if i < len(result.scores) else None,
                    box=box,
                )
            )
        return blocks

    @staticmethod
    def _check_deadline(deadline: float) -> None:
        """Lève OcrEngineError si le délai global du pipeline est dépassé."""
        if time.monotonic() >= deadline:
            raise OcrEngineError(
                "Temps de traitement OCR maximal dépassé "
                f"({get_settings().ocr_pipeline_timeout_seconds:.0f} s)."
            )

    # --- Persistance --------------------------------------------------------------

    def _persist(
        self,
        invoice: Invoice,
        result: OcrExtraction,
        confidence: float,
        images: list[Image.Image],
    ) -> None:
        """Écrit l'extraction, le score, les lignes et les preuves visuelles."""
        # Idempotence : supprime les lignes et anomalies d'une analyse passée.
        existing_lines: list[InvoiceLine] = self.lines.list_by_invoice(invoice.id)
        existing_anomalies: list[Anomaly] = self.anomalies.list_by_invoice(invoice.id)
        for line in existing_lines:
            self.lines.delete(line)
        for anomaly in existing_anomalies:
            self.anomalies.delete(anomaly)
        self.db.flush()

        data = result.model_dump(mode="json")
        for page_meta, image in zip(data["pages"], images):
            page_meta["image_path"] = self._save_page_image(image)

        updates: dict = {
            "extracted_data": data,
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
            self.lines.create(
                invoice_id=invoice.id, **item.model_dump(exclude={"confidence"})
            )

        self._flag_quality(invoice, result, confidence)

    def _save_page_image(self, image: Image.Image) -> str:
        """Encode une page en JPEG et la stocke (chemin relatif retourné)."""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
        return self.storage.save(buffer.getvalue(), suffix=".jpg")

    def _flag_quality(
        self, invoice: Invoice, result: OcrExtraction, confidence: float
    ) -> None:
        """Crée une anomalie de qualité si la confiance est insuffisante.

        Une seule anomalie globale quand la confiance moyenne est sous le
        seuil ; sinon une anomalie ciblée sur les champs critiques douteux
        (champ manquant ou sous le seuil) dès que la confiance globale est
        acceptable.
        """
        threshold = get_settings().ocr_confidence_threshold
        if confidence < threshold:
            logger.warning(
                "OCR : facture %s, confiance globale faible %.1f%% "
                "(seuil %.0f%%) — anomalie qualité créée.",
                invoice.id,
                confidence * 100,
                threshold * 100,
            )
            self.anomalies.create(
                invoice_id=invoice.id,
                category=AnomalyCategory.OTHER,
                severity=AnomalySeverity.WARNING,
                message=(
                    "Score de confiance OCR faible : "
                    f"{confidence:.1%} (seuil {threshold:.0%})."
                ),
                actual_value=f"{confidence:.3f}",
            )
            return
        flagged = flag_low_confidence(result.confidence, confidence, threshold)
        if flagged:
            logger.warning(
                "OCR : facture %s, confiance insuffisante sur les champs "
                "critiques : %s.",
                invoice.id,
                ", ".join(sorted(flagged)),
            )
            self.anomalies.create(
                invoice_id=invoice.id,
                category=AnomalyCategory.OTHER,
                severity=AnomalySeverity.WARNING,
                message=(
                    "Confiance insuffisante sur des champs critiques : "
                    + ", ".join(sorted(flagged))
                    + "."
                ),
                actual_value=", ".join(
                    f"{name}={result.confidence.get(name)}" for name in sorted(flagged)
                ),
            )
