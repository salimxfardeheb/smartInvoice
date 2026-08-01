"""Modèle « anomalie » : écart détecté lors du matching."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AnomalyCategory, AnomalySeverity, enum_values
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.invoice import Invoice


class Anomaly(Base, TimestampMixin):
    """Anomalie associée à une facture (écart de montant, de TVA, doublon...).

    Une anomalie peut être « résolue » (``resolved``) une fois traitée par le
    comptable.
    """

    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint(
            "category IN ('montant', 'tva', 'quantite', 'produit_absent', "
            "'doublon', 'fournisseur', 'bon_commande', 'autre')",
            name="category",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="severity"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[AnomalyCategory] = mapped_column(
        Enum(
            AnomalyCategory,
            name="anomaly_category",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    severity: Mapped[AnomalySeverity] = mapped_column(
        Enum(
            AnomalySeverity,
            name="anomaly_severity",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=AnomalySeverity.WARNING,
        server_default=AnomalySeverity.WARNING.value,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(Text)
    actual_value: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[Invoice] = relationship(back_populates="anomalies")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<Anomaly id={self.id} category={self.category!r} "
            f"severity={self.severity!r}>"
        )
