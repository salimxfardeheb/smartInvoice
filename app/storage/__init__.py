"""Point d'entrée de la couche de stockage : fabrique du stockage configuré."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.storage.base import Storage
from app.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    """Retourne le stockage actif (local sur disque pour le MVP).

    Mis en cache car la création est coûteuse (création de la racine) et que
    le stockage est un objet sans état propre.
    """
    return LocalStorage(Path(get_settings().storage_root))


__all__ = ["LocalStorage", "Storage", "get_storage"]
