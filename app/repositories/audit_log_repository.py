"""Repository de l'entité ``AuditLog`` (journal d'audit des factures)."""

from __future__ import annotations

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Accès aux données du journal d'audit."""

    model = AuditLog

    def create(
        self,
        *,
        invoice_id: int,
        user_id: int | None,
        action: AuditAction,
        message: str,
        details: dict | None = None,
    ) -> AuditLog:
        """Enregistre une entrée du journal d'audit."""
        return self.add(
            AuditLog(
                invoice_id=invoice_id,
                user_id=user_id,
                action=action,
                message=message,
                details=details,
            )
        )

    def list_by_invoice(self, invoice_id: int) -> list[AuditLog]:
        """Retourne les entrées d'audit d'une facture, de la plus récente à la plus ancienne."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.invoice_id == invoice_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        return list(self.session.scalars(stmt))

    def list_by_invoice_paginated(
        self, invoice_id: int, *, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        """Retourne une page du journal d'audit d'une facture (plus récentes d'abord).

        Permet de paginer un journal potentiellement volumineux
        (``limit``/``offset``) au lieu de renvoyer la liste complète.
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.invoice_id == invoice_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def count_by_invoice(self, invoice_id: int) -> int:
        """Compte les entrées d'audit d'une facture."""
        from sqlalchemy import func

        stmt = (
            select(func.count(AuditLog.id))
            .select_from(AuditLog)
            .where(AuditLog.invoice_id == invoice_id)
        )
        return int(self.session.scalar(stmt) or 0)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        """Retourne les dernières entrées du journal (toutes factures)."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))
