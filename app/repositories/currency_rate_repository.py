"""Repository de l'entité ``CurrencyRate`` (taux de change synchronisés)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.currency_rate import CurrencyRate
from app.repositories.base import BaseRepository


class CurrencyRateRepository(BaseRepository[CurrencyRate]):
    """Accès aux taux de change."""

    model = CurrencyRate

    def get_rate(
        self, code: str, *, base_currency: str = "EUR"
    ) -> Decimal | None:
        """Retourne le taux de ``code`` vers ``base_currency`` (``None`` si absent).

        La devise de référence vaut, par définition, 1.0 (même si aucun taux
        explicite n'a été synchronisé pour elle).
        """
        code = code.upper()
        base_currency = base_currency.upper()
        if code == base_currency:
            return Decimal("1.0")
        stmt = select(CurrencyRate).where(
            CurrencyRate.code == code,
            CurrencyRate.base_currency == base_currency,
        )
        row = self.session.scalars(stmt).first()
        return row.rate if row is not None else None

    def set_rate(
        self, code: str, rate: Decimal, *, base_currency: str = "EUR"
    ) -> CurrencyRate:
        """Enregistre (crée ou met à jour) le taux courant d'une devise."""
        stmt = select(CurrencyRate).where(
            CurrencyRate.code == code,
            CurrencyRate.base_currency == base_currency,
        )
        row = self.session.scalars(stmt).first()
        if row is None:
            return self.add(
                CurrencyRate(
                    code=code,
                    base_currency=base_currency,
                    rate=rate,
                )
            )
        self.update(row, rate=rate)
        return row
