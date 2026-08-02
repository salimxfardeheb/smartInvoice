"""Schémas de l'API Matching (phase 6 - rapprochement facture / bon de commande)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import AnomalyCategory, AnomalySeverity


class MatchingLineRead(BaseModel):
    """Résultat du rapprochement d'une ligne de facture (pour l'API)."""

    line_number: int
    description: str
    product_ref: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    purchase_order_line_odoo_id: int | None = None
    quantity_matched: bool = False
    unit_price_matched: bool = False
    quantity_delta: float | None = None
    unit_price_delta: float | None = None


class MatchingAnomalyRead(BaseModel):
    """Anomalie détectée lors du matching (pour l'API)."""

    category: AnomalyCategory
    severity: AnomalySeverity
    message: str
    expected_value: str | None = None
    actual_value: str | None = None


class MatchingRead(BaseModel):
    """Résultat complet d'un passage de matching (pour l'API)."""

    invoice_id: int
    purchase_order_reference: str | None = None
    supplier_match: bool = False
    duplicate_found: bool = False
    score: float = 0.0
    lines: list[MatchingLineRead] = []
    anomalies: list[MatchingAnomalyRead] = []
