"""Modèle « taux de change » : montant d'une devise, exprimé dans une référence.

Un taux stocke combien d'unités de la devise de référence (``base_currency``,
par défaut EUR) vaut une unité de la devise ``code``. Ex. pour l'USD vers
l'EUR, ``rate = 0.92`` signifie que 1 USD = 0,92 EUR.

Les taux sont synchronisés depuis Odoo (:class:`app.services.odoo_service`)
et utilisés par le matching pour comparer des montants multi-devises en les
convertissant dans une référence commune.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CurrencyRate(Base, TimestampMixin):
    """Taux de change courant d'une devise vers une devise de référence."""

    __tablename__ = "currency_rates"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    base_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )
    # nb d'unités de ``base_currency`` pour 1 unité de ``code``.
    rate: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<CurrencyRate {self.code}/{self.base_currency}={self.rate}>"
        )