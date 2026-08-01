"""Configuration de l'application via variables d'environnement.

Les valeurs sont lues depuis le fichier ``.env`` à la racine du projet et/ou
depuis les variables d'environnement du système. La variable principale est
``DATABASE_URL`` (URL de connexion PostgreSQL / SQLAlchemy).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres SmartInvoice.

    Attributs:
        database_url: URL de connexion SQLAlchemy (par défaut PostgreSQL local).
        echo_sql: active les logs SQL (utile en développement).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg2://smartinvoice:smartinvoice@localhost:5432/smartinvoice"
    )
    echo_sql: bool = False


@lru_cache
def get_settings() -> Settings:
    """Retourne les paramètres (mis en cache pour éviter de relire les envs)."""
    return Settings()
