"""Abstraction du stockage des documents de factures.

Définit le contrat minimal (enregistrer, lire, tester, supprimer, localiser)
d'un stockage de fichiers. L'implémentation MVP est un stockage local sur
disque (:mod:`app.storage.local`), mais le contrat est conçu pour être
remplacé par un object storage (S3, GCS, …) sans toucher au reste du code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Storage(ABC):
    """Stockage opaque de documents identifiés par un chemin relatif."""

    @abstractmethod
    def save(self, content: bytes, *, suffix: str) -> str:
        """Persiste un contenu et retourne son chemin relatif.

        ``suffix`` (extension, ex. ``.pdf``) est fourni par l'appelant ;
        le nom de fichier interne est généré par le stockage.
        """

    @abstractmethod
    def open(self, relative_path: str) -> bytes:
        """Retourne le contenu binaire d'un document stocké."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """Indique si un document existe."""

    @abstractmethod
    def delete(self, relative_path: str) -> None:
        """Supprime un document (sans erreur s'il est absent)."""

    @abstractmethod
    def path(self, relative_path: str) -> Path:
        """Chemin local du document (résolution pour l'accès hors API)."""
