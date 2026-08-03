"""Modèle « réglage » : paires clé/valeur persistant des paramètres en base.

Permet d'overrider certains paramètres d'exploitation (ex. tolérances du
matching) sans redéploiement, et de les lire dans le contexte de la requête
(au lieu d'une config chargée une seule fois au démarrage).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


def serialize_value(value: Any) -> str:
    """Sérialise une valeur simple (float/int/bool/str) vers sa forme stockée."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return value


def deserialize_value(raw: str) -> Any:
    """Désérialise une valeur stockée vers un type Python simple."""
    if raw == "true":
        return True
    if raw == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


class Setting(Base, TimestampMixin):
    """Réglage clé/valeur (clé = PK, valeur toujours stockée en chaîne)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<Setting {self.key!r}={self.value!r}>"