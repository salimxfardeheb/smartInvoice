"""Chargement d'un document stocké vers des images (une par page).

Un PDF est rendu page par page via pypdfium2 à la résolution configurée
(``ocr_render_dpi``) ; un PDF scanné devient donc une série d'images passées
au moteur OCR. Une image (JPG/JPEG/PNG) est utilisée telle quelle.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import DocumentNotFoundError, OcrEngineError
from app.models.invoice import Invoice
from app.storage.base import Storage

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Convertit le fichier d'une facture en images prêtes pour l'OCR."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def load_images(self, invoice: Invoice) -> list[Image.Image]:
        """Retourne les images du document (une par page pour les PDF).

        Lève :class:`DocumentNotFoundError` si le fichier est absent et
        :class:`OcrEngineError` si le rendu échoue.
        """
        if invoice.file_path is None or not self.storage.exists(invoice.file_path):
            logger.error(
                "Document : fichier source introuvable pour la facture %s (%s).",
                invoice.id,
                invoice.file_path,
            )
            raise DocumentNotFoundError(
                "Le fichier source de la facture est introuvable."
            )
        content = self.storage.open(invoice.file_path)
        if invoice.content_type == "application/pdf":
            return self._render_pdf(content)
        return self._load_image(content)

    def _render_pdf(self, content: bytes) -> list[Image.Image]:
        """Rend chaque page d'un PDF en image RGB à ``ocr_render_dpi``."""
        import pypdfium2 as pdfium

        dpi = get_settings().ocr_render_dpi
        max_pages = get_settings().ocr_max_pages
        try:
            document = pdfium.PdfDocument(content)
        except Exception as exc:
            logger.error("Document : PDF illisible : %s", exc, exc_info=True)
            raise OcrEngineError("Impossible d'ouvrir le PDF pour l'analyse.") from exc

        try:
            page_count = len(document)
        except TypeError:  # pragma: no cover - fakes/document exotiques sans __len__
            page_count = None
        if page_count is not None and page_count > max_pages:
            document.close()
            logger.warning(
                "Document : PDF refusé, %s pages (maximum %s).",
                page_count,
                max_pages,
            )
            raise OcrEngineError(
                f"Document trop volumineux ({page_count} pages, maximum {max_pages})."
            )

        images: list[Image.Image] = []
        try:
            for page in document:
                bitmap = page.render(scale=dpi / 72)
                images.append(bitmap.to_pil().convert("RGB"))
        except Exception as exc:
            logger.error("Document : rendu du PDF impossible : %s", exc, exc_info=True)
            raise OcrEngineError(
                "Impossible de rendre le PDF en images."
            ) from exc
        finally:
            document.close()
        return images

    @staticmethod
    def _load_image(content: bytes) -> list[Image.Image]:
        """Charge une image (JPG/JPEG/PNG) unique en RGB."""
        try:
            with Image.open(io.BytesIO(content)) as image:
                return [image.convert("RGB")]
        except UnidentifiedImageError as exc:
            logger.error("Document : image illisible : %s", exc, exc_info=True)
            raise OcrEngineError("L'image du document est illisible.") from exc
