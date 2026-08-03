"""Repository de l'entité ``Setting`` (paires clé/valeur persistantes)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.setting import Setting, deserialize_value, serialize_value
from app.repositories.base import BaseRepository


class SettingRepository(BaseRepository[Setting]):
    """Accès aux réglages persistants (overrides d'exploitation)."""

    model = Setting

    def get(self, key: str) -> str | None:
        """Retourne la valeur brute d'un réglage, ou ``None``."""
        stmt = select(Setting).where(Setting.key == key)
        setting = self.session.scalars(stmt).first()
        return setting.value if setting is not None else None

    def get_typed(self, key: str, default: Any) -> Any:
        """Retourne un réglage désérialisé, ou ``default`` absent."""
        raw = self.get(key)
        if raw is None:
            return default
        return deserialize_value(raw)

    def set(self, key: str, value: Any) -> Setting:
        """Écrit (ou écrase) un réglage et renvoie l'entité en session."""
        raw = serialize_value(value)
        stmt = select(Setting).where(Setting.key == key)
        setting = self.session.scalars(stmt).first()
        if setting is None:
            setting = Setting(key=key, value=raw)
            self.session.add(setting)
        else:
            setting.value = raw
        self.session.flush()
        return setting

    def set_many(self, values: dict[str, Any]) -> None:
        """Écrit plusieurs réglages dans une même transaction."""
        for key, value in values.items():
            self.set(key, value)

    def all(self) -> dict[str, Any]:
        """Retourne la totalité des réglages typés sous forme de mapping."""
        stmt = select(Setting)
        return {
            s.key: deserialize_value(s.value) for s in self.session.scalars(stmt)
        }