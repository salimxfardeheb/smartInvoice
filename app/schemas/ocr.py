"""Schémas de l'API OCR (phase 4 - analyse automatique)."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import InvoiceStatus


class OcrResultRead(BaseModel):
    """Résultat d'une analyse OCR d'une facture.

    ``extracted_data`` reproduit le contenu persistant stocké sur la facture
    (``invoices.extracted_data``) : champs généraux, financiers et lignes.
    """

    invoice_id: int
    status: InvoiceStatus
    ocr_confidence_score: float | None = None
    error_message: str | None = None
    extracted_data: dict | None = None
