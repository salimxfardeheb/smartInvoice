"""Modèle « journal d'audit » : trace des actions sur une facture (phase 7).

Chaque passage d'une facture par une étape décisionnelle du comptable
(validation, correction, rejet, création de la Vendor Bill) est enregistré :
qui a agi (``user_id``), quand (``created_at``), quoi (``action``,
``message``) et éventuellement le détail structuré des changements
(``details``, JSON).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AuditAction, enum_values
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice
    from app.models.user import User

# Portabilité : JSONB en production (PostgreSQL), JSON ailleurs (tests SQLite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base, TimestampMixin):
    """Entrée du journal d'audit d'une facture.

    La référence à l'utilisateur est conservée même si son compte est
    supprimé (``user_id`` nullable, ``ondelete=SET NULL``) afin de préserver
    la traçabilité.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JsonType)

    invoice: Mapped[Invoice] = relationship(back_populates="audit_logs")
    user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<AuditLog id={self.id} invoice={self.invoice_id} "
            f"action={self.action!r} user={self.user_id!r}>"
        )
