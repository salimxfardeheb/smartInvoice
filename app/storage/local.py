"""Stockage local des documents sur disque (implémentation MVP).

Les fichiers sont rangés sous ``{storage_root}/invoices/{AAAA}/{MM}/{uuid}{ext}``.
Le chemin relatif retourné par :meth:`LocalStorage.save` est la seule valeur
persistée en base (colonne ``invoices.file_path``).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.storage.base import Storage


class LocalStorage(Storage):
    """Stockage sur disque sous une racine configurable."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, *, suffix: str) -> str:
        now = datetime.now()
        rel = f"invoices/{now:%Y}/{now:%m}/{uuid4().hex}{suffix}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return rel

    def _safe_path(self, relative_path: str) -> Path:
        """Résout un chemin relatif en vérifiant qu'il reste sous la racine."""
        path = (self.root / relative_path).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("Chemin de stockage invalide.")
        return path

    def open(self, relative_path: str) -> bytes:
        return self._safe_path(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        return self._safe_path(relative_path).is_file()

    def delete(self, relative_path: str) -> None:
        self._safe_path(relative_path).unlink(missing_ok=True)

    def path(self, relative_path: str) -> Path:
        return self._safe_path(relative_path)
