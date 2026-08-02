"""Schémas de l'extraction OCR (persistés dans ``invoices.extracted_data``).

Ces modèles Pydantic décrivent le résultat structuré du pipeline OCR :
champs généraux, champs financiers et lignes de facture. Ils sont sérialisés
en JSON pour la colonne ``extracted_data`` et utilisés comme référence lors
des phases suivantes (matching, validation).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OcrGeneralFields(BaseModel):
    """Champs généraux d'une facture extraits par l'OCR."""

    model_config = ConfigDict(extra="allow")

    supplier_name: str | None = None
    supplier_address: str | None = None
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    purchase_order_reference: str | None = None
    supplier_reference: str | None = None


class OcrFinancialFields(BaseModel):
    """Champs financiers d'une facture extraits par l'OCR."""

    model_config = ConfigDict(extra="allow")

    total_excl_tax: Decimal | None = None
    tax_amount: Decimal | None = None
    total_incl_tax: Decimal | None = None
    discount: Decimal | None = None
    shipping_fees: Decimal | None = None


class OcrLineItem(BaseModel):
    """Ligne de facture extraite par l'OCR."""

    line_number: int
    description: str
    product_ref: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    amount: Decimal | None = None


class OcrExtraction(BaseModel):
    """Résultat complet de l'extraction OCR d'une facture."""

    general: OcrGeneralFields
    financial: OcrFinancialFields
    lines: list[OcrLineItem] = []
