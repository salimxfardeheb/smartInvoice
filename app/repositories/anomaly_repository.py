"""Repository de l'entité ``Anomaly`` (anomalie détectée lors du matching)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.anomaly import Anomaly
from app.models.enums import AnomalyCategory, AnomalySeverity
from app.repositories.base import BaseRepository


class AnomalyRepository(BaseRepository[Anomaly]):
    """Accès aux données des anomalies."""

    model = Anomaly

    def create(
        self,
        *,
        invoice_id: int,
        category: AnomalyCategory,
        message: str,
        severity: AnomalySeverity = AnomalySeverity.WARNING,
        expected_value: str | None = None,
        actual_value: str | None = None,
    ) -> Anomaly:
        """Crée une anomalie liée à une facture."""
        return self.add(
            Anomaly(
                invoice_id=invoice_id,
                category=category,
                severity=severity,
                message=message,
                expected_value=expected_value,
                actual_value=actual_value,
            )
        )

    def list_by_invoice(self, invoice_id: int) -> list[Anomaly]:
        """Retourne les anomalies d'une facture."""
        stmt = (
            select(Anomaly)
            .where(Anomaly.invoice_id == invoice_id)
            .order_by(Anomaly.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_unresolved(self, *, limit: int = 100) -> list[Anomaly]:
        """Retourne les anomalies non résolues (dashboard de suivi)."""
        stmt = (
            select(Anomaly)
            .where(Anomaly.resolved.is_(False))
            .order_by(Anomaly.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def resolve(self, anomaly: Anomaly) -> Anomaly:
        """Marque une anomalie comme résolue."""
        self.update(
            anomaly, resolved=True, resolved_at=datetime.now(timezone.utc)
        )
        return anomaly
