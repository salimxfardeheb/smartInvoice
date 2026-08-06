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
    ocr_engine: str = "paddle"  # moteur OCR : "paddle" ou "tesseract"
    ocr_lang: str = "fr"
    ocr_tesseract_lang: str = "fra"  # langue Tesseract (ex. "fra", "eng", "fra+eng")
    ocr_render_dpi: int = 200
    ocr_confidence_threshold: float = 0.6
    # Limites de robustesse (PPTX / timeout global du pipeline).
    ocr_max_pages: int = 50
    ocr_pipeline_timeout_seconds: float = 300.0

    # Odoo (phase 5) : connexion XML-RPC au serveur de production.
    # Laisser les champs vides désactive la synchronisation (le service lève
    # alors :class:`OdooNotConfiguredError`).
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""
    # Clé API d'un utilisateur applicatif dédié (droits restreints). Si
    # renseignée, elle prime sur ``odoo_password`` lors de l'authentification
    # (Odoo 14+ accepte une clé API en lieu et place du mot de passe).
    odoo_api_key: str = ""
    odoo_timeout_seconds: float = 30.0

    # Matching (phase 6) : tolérances des écarts acceptés (ratios relatifs).
    # Un écart (quantité, prix, montant, TVA) est toléré tant qu'il reste
    # sous son seuil ; au-delà, une anomalie est enregistrée.
    matching_quantity_tolerance: float = 0.05
    matching_price_tolerance: float = 0.02
    matching_amount_tolerance: float = 0.02
    matching_tax_tolerance: float = 0.02
    # Devise de référence pour le matching multi-devises : les montants d'une
    # facture sont convertis dans cette devise pour être comparés au BC si les
    # devises diffèrent (taux fournis par la table ``currency_rates``).
    fx_base_currency: str = "EUR"

    # Sécurité / infrastructure
    # --- CORS (liste d'origines séparées par des virgules ; vide = désactivé)
    cors_origins: str = ""
    # --- Rotation des secrets : clés encore acceptées en décodage (transition)
    jwt_legacy_secrets: str = ""

    # --- Rate limiting de l'authentification (brute force)
    #
    # Actif par défaut : une instance exposée sans limitation laisse ``/login``
    # et ``/refresh`` ouverts au bourrinage. Se désactive explicitement par
    # ``RATE_LIMIT_ENABLED=false`` (utile en test de charge ou en local).
    #
    # ATTENTION — compteur **en mémoire du processus** (voir ``core/ratelimit``) :
    # avec plusieurs workers Uvicorn, chaque worker tient son propre compteur et
    # la limite effective est multipliée par le nombre de workers. Lancer l'API
    # avec ``--workers 1`` (cf. README, « Démarrage ») tant que le limiteur n'est
    # pas déporté sur un stockage partagé (Redis).
    rate_limit_enabled: bool = True
    rate_limit_max: int = 20
    rate_limit_window_seconds: int = 60

    # --- File asynchrone des jobs OCR
    #
    # ATTENTION — pool de threads **in-process** (voir ``services/task_manager``) :
    # les jobs vivent dans le processus qui a reçu la requête et ne survivent pas
    # à un redémarrage (les tâches orphelines sont neutralisées au démarrage par
    # ``services/startup_recovery``). Monter en charge via ce réglage, pas via le
    # nombre de workers Uvicorn.
    task_queue_workers: int = 2

    # --- Logging applicatif
    #
    # Niveau du logger racine (DEBUG/INFO/WARNING/ERROR/CRITICAL). ``INFO`` par
    # défaut : trace le déroulement du pipeline OCR, des tâches asynchrones et
    # de la synchronisation Odoo sans le bruit des requêtes SQL (``echo_sql``
    # les active séparément).
    log_level: str = "INFO"

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

    @property
    def cors_origin_list(self) -> list[str]:
        """Origines CORS autorisées (séparées par des virgules)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwt_legacy_secret_list(self) -> list[str]:
        """Clés (anciennes) encore valides en décodage, hors clé principale."""
        return [s.strip() for s in self.jwt_legacy_secrets.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    """Retourne les paramètres (mis en cache pour éviter de relire les envs)."""
    return Settings()
