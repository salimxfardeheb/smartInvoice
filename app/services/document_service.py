"""Validation et détection des documents de factures (phase 3).

Vérifie qu'un fichier déposé est un document supporté (PDF, JPG, JPEG, PNG)
et *lisible* : les signatures binaires (« magic bytes ») sont vérifiées en
priorité sur l'extension ou le ``Content-Type`` déclaré, puis le contenu est
réellement ouvert pour écarter les fichiers corrompus ou tronqués.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.exceptions import InvalidDocumentError

# Formats supportés au MVP : (signature binaire, extension, type MIME).
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Extension (suffixe de stockage) → type MIME canonique.
SUPPORTED_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class DocumentValidator:
    """Valide la forme et la lisibilité d'un document déposé.

    L'instance est sans état : elle peut être instanciée à la demande ou
    partagée. La limite de taille est lue depuis la configuration
    (``max_upload_size_mb``).
    """

    def validate(self, filename: str, content: bytes) -> tuple[str, str]:
        """Valide un document et retourne ``(suffixe, mime_type)``.

        Lève :class:`InvalidDocumentError` si le document est vide, trop
        lourd, d'un format non supporté ou corrompu/illisible.

        Arguments:
            filename: nom original du fichier (utile pour les messages).
            content: contenu binaire du document.

        Retour:
            L'extension à utiliser pour le stockage et le type MIME détecté.
        """
        if not content:
            raise InvalidDocumentError("Le document déposé est vide.")

        max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise InvalidDocumentError(
                f"Le document dépasse la taille maximale autorisée "
                f"({get_settings().max_upload_size_mb} Mo)."
            )

        suffix, mime_type = self._detect_format(content)
        self._ensure_readable(suffix, content)
        return suffix, mime_type

    def _detect_format(self, content: bytes) -> tuple[str, str]:
        """Détecte le format par signatures binaires (aucune confiance dans
        l'extension ou le type MIME déclaré)."""
        if content.startswith(_PDF_MAGIC):
            return ".pdf", SUPPORTED_MIME_TYPES[".pdf"]
        if content.startswith(_JPEG_MAGIC):
            return ".jpg", SUPPORTED_MIME_TYPES[".jpg"]
        if content.startswith(_PNG_MAGIC):
            return ".png", SUPPORTED_MIME_TYPES[".png"]
        raise InvalidDocumentError(
            "Format de document non supporté. Formats acceptés : "
            "PDF, JPG, JPEG, PNG."
        )

    def _ensure_readable(self, suffix: str, content: bytes) -> None:
        """Ouvre réellement le document pour détecter les fichiers corrompus.

        Un fichier qui possède la bonne signature mais un contenu corrompu
        (PDF tronqué, image illisible) est rejeté ici.
        """
        try:
            if suffix == ".pdf":
                self._open_pdf(content)
            else:
                self._open_image(content)
        except InvalidDocumentError:
            raise
        except Exception as exc:  # PDFiumError, UnidentifiedImageError, ...
            raise InvalidDocumentError(
                "Le document est corrompu ou illisible."
            ) from exc

    @staticmethod
    def _open_pdf(content: bytes) -> None:
        """Ouvre un PDF via pypdfium2 (échec si la structure est invalide)."""
        import pypdfium2 as pdfium

        pdfium.PdfDocument(content).close()

    @staticmethod
    def _open_image(content: bytes) -> None:
        """Vérifie une image via Pillow (échec si le fichier est corrompu)."""
        import io

        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(content)) as image:
                image.load()
        except UnidentifiedImageError as exc:
            raise InvalidDocumentError(
                "Le document est corrompu ou illisible."
            ) from exc
