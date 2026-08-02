"""Schémas de l'entité « facture » (phase 3 - documents)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InvoiceStatus


class SupplierBrief(BaseModel):
    """Représentation allégée du fournisseur d'une facture."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class InvoiceRead(BaseModel):
    """Métadonnées d'une facture exposées par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str
    supplier: SupplierBrief
    status: InvoiceStatus
    issue_date: date | None
    due_date: date | None
    currency: str
    total_excl_tax: Decimal | None
    tax_amount: Decimal | None
    total_incl_tax: Decimal | None
    discount: Decimal | None
    shipping_fees: Decimal | None
    ocr_confidence_score: float | None
    matching_score: float | None
    vendor_bill_id: int | None
    file_info: dict | None
    extracted_data: dict | None
    rejection_reason: str | None
    error_message: str | None
    is_duplicate: bool
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    """Résultat paginé de l'historique des factures."""

    items: list[InvoiceRead]
    total: int


class InvoiceStatusUpdate(BaseModel):
    """Transition de statut demandée via l'API."""

    status: InvoiceStatus
    reason: str | None = Field(default=None, max_length=1000)
