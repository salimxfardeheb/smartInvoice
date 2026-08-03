"""Repository de l'entité ``Anomaly`` (anomalie détectée lors du matching)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

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

    def filter(
        self,
        *,
        resolved: bool | None = None,
        severity: AnomalySeverity | None = None,
        category: AnomalyCategory | None = None,
        invoice_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Anomaly]:
        """Liste paginée et filtrée des anomalies (toutes factures).

        ``resolved`` permet de filtrer par statut (``True`` résolues,
        ``False`` en attente, ``None`` les deux). Les filtres de sévérité,
        de catégorie et de facture sont combinables.
        """
        stmt = self._filtered_stmt(
            resolved=resolved, severity=severity, category=category, invoice_id=invoice_id
        )
        stmt = (
            stmt.order_by(Anomaly.created_at.desc(), Anomaly.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        resolved: bool | None = None,
        severity: AnomalySeverity | None = None,
        category: AnomalyCategory | None = None,
        invoice_id: int | None = None,
    ) -> int:
        """Compte les anomalies correspondant aux mêmes filtres que ``filter``."""
        subq = self._filtered_stmt(
            resolved=resolved, severity=severity, category=category, invoice_id=invoice_id
        ).subquery()
        return int(self.session.scalar(select(func.count()).select_from(subq)) or 0)

    def _filtered_stmt(
        self,
        *,
        resolved: bool | None,
        severity: AnomalySeverity | None,
        category: AnomalyCategory | None,
        invoice_id: int | None,
    ):
        """Requête de base commune à ``filter`` et ``count`` (filtres combinables)."""
        stmt = select(Anomaly)
        if resolved is not None:
            stmt = stmt.where(Anomaly.resolved.is_(resolved))
        if severity is not None:
            stmt = stmt.where(Anomaly.severity == severity)
        if category is not None:
            stmt = stmt.where(Anomaly.category == category)
        if invoice_id is not None:
            stmt = stmt.where(Anomaly.invoice_id == invoice_id)
        return stmt

    def resolve(self, anomaly: Anomaly) -> Anomaly:
        """Marque une anomalie comme résolue."""
        self.update(
            anomaly, resolved=True, resolved_at=datetime.now(timezone.utc)
        )
        return anomaly
