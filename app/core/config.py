"""Configuration de l'application via variables d'environnement.

Les valeurs sont lues depuis le fichier ``.env`` à la racine du projet et/ou
depuis les variables d'environnement du système. La variable principale est
``DATABASE_URL`` (URL de connexion PostgreSQL / SQLAlchemy).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres SmartInvoice.

    Attributs:
        database_url: URL de connexion SQLAlchemy (par défaut PostgreSQL local).
        echo_sql: active les logs SQL (utile en développement).
        jwt_secret_key: clé secrète de signature des jetons JWT.
        jwt_algorithm: algorithme de signature JWT.
        access_token_expire_minutes: durée de vie des access tokens.
        refresh_token_expire_days: durée de vie des refresh tokens.
        environment: environnement d'exécution (development/production).
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

    environment: str = "development"
    jwt_secret_key: str = "dev-only-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Stockage des documents
    storage_root: str = "storage"
    max_upload_size_mb: int = 20

    # OCR (phase 4)
    ocr_lang: str = "fr"
    ocr_render_dpi: int = 200
    ocr_confidence_threshold: float = 0.6

    # Odoo (phase 5) : connexion XML-RPC au serveur de production.
    # Laisser les champs vides désactive la synchronisation (le service lève
    # alors :class:`OdooNotConfiguredError`).
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""
    odoo_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def _reject_default_secret_in_production(self) -> Settings:
        """Refuse la clé JWT par défaut en production."""
        if (
            self.environment == "production"
            and self.jwt_secret_key == "dev-only-change-me-0123456789abcdef"
        ):
            raise ValueError(
                "jwt_secret_key ne doit pas être la valeur par défaut en production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Retourne les paramètres (mis en cache pour éviter de relire les envs)."""
    return Settings()
