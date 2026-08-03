"""Schémas de l'API Anomalies (liste globale, résolution)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AnomalyCategory, AnomalySeverity


class AnomalyRead(BaseModel):
    """Anomalie exposée par l'API (avec contexte de la facture)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    invoice_number: str | None = None
    supplier_name: str | None = None
    category: AnomalyCategory
    severity: AnomalySeverity
    message: str
    expected_value: str | None = None
    actual_value: str | None = None
    resolved: bool
    resolved_at: datetime | None = None
    created_at: datetime


class AnomalyListResponse(BaseModel):
    """Résultat paginé de la liste globale des anomalies."""

    items: list[AnomalyRead]
    total: int