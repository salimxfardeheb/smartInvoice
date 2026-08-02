"""Schémas du tableau de bord (phase 8 - synthèse)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AnomalyCategory, AnomalySeverity


class PendingAnomaly(BaseModel):
    """Anomalie non résolue liée à une facture (vue tableau de bord)."""

    id: int
    invoice_id: int
    invoice_number: str
    supplier_name: str | None
    category: AnomalyCategory
    severity: AnomalySeverity
    message: str
    expected_value: str | None
    actual_value: str | None
    created_at: datetime


class DashboardSummary(BaseModel):
    """Synthèse du tableau de bord : comptes par statut et anomalies en attente."""

    by_status: dict[str, int]
    pending_anomalies: list[PendingAnomaly]
