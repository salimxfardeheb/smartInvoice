"""Fixtures partagées des tests SmartInvoice.

Les tests utilisent une base SQLite en mémoire isolée (``StaticPool``) et les
contraintes d'intégrité référentielle sont activées via ``PRAGMA foreign_keys``
afin de reproduire fidèlement le comportement PostgreSQL.

La configuration est isolée dès l'import de ce module, **avant tout import
applicatif** : ni le fichier ``.env`` du poste ni les variables
d'environnement de la machine ne doivent influencer les tests. C'est une
contrainte d'import et pas seulement de fixture, car ``app.db.session``
construit son moteur au moment de l'import à partir de ``DATABASE_URL``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings

# --- Isolation de la configuration ------------------------------------------

# Valeurs fictives appliquées à toute la suite.
_FAKE_ENV: dict[str, str] = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "sqlite://",
    "JWT_SECRET_KEY": "test-only-secret-0123456789abcdef",
    # Odoo est volontairement laissé « non configuré » : aucun test ne doit
    # joindre un serveur réel, et les cas « configuration incomplète » (client
    # Odoo, ``/healthz``) doivent être reproductibles sur tous les postes. Les
    # tests qui ont besoin d'un Odoo configuré utilisent la fixture
    # ``odoo_env`` ou passent les valeurs au constructeur.
    "ODOO_URL": "",
    "ODOO_DB": "",
    "ODOO_USERNAME": "",
    "ODOO_PASSWORD": "",
    "ODOO_API_KEY": "",
}


def _isolate_settings() -> None:
    """Neutralise le ``.env`` local et l'environnement hérité de la machine."""
    # 1. Le fichier .env du poste ne doit pas être lu.
    Settings.model_config["env_file"] = None
    # 2. Toute variable d'environnement correspondant à un réglage est purgée
    #    (pydantic-settings résout les noms sans tenir compte de la casse).
    for field in Settings.model_fields:
        os.environ.pop(field.upper(), None)
        os.environ.pop(field.lower(), None)
    # 3. Valeurs fictives déterministes, identiques d'un poste à l'autre.
    os.environ.update(_FAKE_ENV)
    # Les documents écrits par défaut atterrissent hors du dépôt.
    os.environ["STORAGE_ROOT"] = tempfile.mkdtemp(prefix="smartinvoice-tests-")
    get_settings.cache_clear()


_isolate_settings()

import app.models  # noqa: E402,F401  (enregistre les modèles dans Base.metadata)
from app.db.base import Base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

STATUS_INVOICE = "Déposée"


def _enable_foreign_keys(dbapi_connection, _record) -> None:  # pragma: no cover
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Repart d'une configuration fraîche à chaque test.

    ``get_settings`` est mémoïsée (``lru_cache``) et plusieurs tests modifient
    l'instance retournée (``monkeypatch.setattr(get_settings(), ...)``) ou les
    variables d'environnement. Sans cette réinitialisation, le réglage modifié
    fuiterait vers les tests suivants, dans un ordre dépendant de la collecte.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def odoo_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Settings]]:
    """Fabrique de configuration Odoo fictive, isolée du ``.env``.

    Appeler la fixture applique un jeu complet de variables ``ODOO_*``
    factices et retourne les réglages correspondants ; les valeurs peuvent
    être surchargées une à une (``odoo_env(ODOO_URL="")`` pour simuler une
    configuration incomplète).
    """

    def apply(**overrides: str) -> Settings:
        values = {
            "ODOO_URL": "http://odoo.test.invalid",
            "ODOO_DB": "test-db",
            "ODOO_USERNAME": "test-user",
            "ODOO_PASSWORD": "test-password",
            "ODOO_API_KEY": "",
        }
        values.update(overrides)
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return get_settings()

    yield apply
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Repart d'un limiteur vierge à chaque test.

    Le limiteur anti-brute-force est actif par défaut (``RATE_LIMIT_ENABLED``)
    et vit dans un singleton de processus : sans réinitialisation, les
    tentatives de connexion s'accumuleraient d'un test à l'autre et
    finiraient par déclencher des 429 sans rapport avec le cas testé.
    """
    from app.core.ratelimit import reset_limiter

    reset_limiter()
    yield
    reset_limiter()


@pytest.fixture()
def engine() -> Iterator[Engine]:
    """Moteur SQLite en mémoire avec schéma créé depuis les modèles."""
    eng = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    event.listen(eng, "connect", _enable_foreign_keys)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Session transactionnelle sur le moteur de test."""
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture()
def alembic_config() -> Config:
    """Configuration Alembic pointant vers le dossier de migrations du projet."""
    return Config(str(ROOT / "alembic.ini"))


@pytest.fixture()
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    """Moteur SQLite en mémoire dont le schéma est produit par ``upgrade head``."""
    eng = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    event.listen(eng, "connect", _enable_foreign_keys)
    connection = eng.connect()
    alembic_config.attributes["connection"] = connection
    command.upgrade(alembic_config, "head")
    yield eng
    connection.close()
    eng.dispose()


@pytest.fixture()
def client(engine: Engine):
    """Client HTTP de test branché sur le moteur SQLite en mémoire.

    La dépendance ``get_db`` de l'application est remplacée pour servir des
    sessions sur le moteur de test, avec commit à la fin de chaque requête
    (même comportement que la production). ``get_task_manager`` est également
    remplacé : les jobs asynchrones (OCR) s'exécutent **immédiatement** dans le
    thread d'appel (exécuteur inline) sur le moteur de test, ce qui rend les
    tests déterministes sans réels threads.

    La fabrique de sessions est aussi passée à ``create_app`` : la reprise au
    démarrage (``lifespan``) balaye ainsi le moteur de test et non la base
    définie par ``DATABASE_URL``.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_db, get_task_manager
    from app.main import create_app
    from app.services.task_manager import InlineExecutor, TaskManager

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=session_factory)

    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def override_get_task_manager() -> TaskManager:
        return TaskManager(
            session_factory=session_factory, executor=InlineExecutor()
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_task_manager] = override_get_task_manager
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Helpers d'authentification --------------------------------------------


def register_user(
    client,
    *,
    username: str,
    password: str = "Password123!",
    email: str | None = None,
    role: str | None = None,
):
    """Inscrit un utilisateur via l'API et retourne la réponse HTTP."""
    payload = {
        "username": username,
        "email": email or f"{username}@example.com",
        "password": password,
    }
    if role is not None:
        payload["role"] = role
    return client.post("/api/auth/register", json=payload)


def login(client, username: str, password: str = "Password123!"):
    """Se connecte via l'API (formulaire OAuth2) et retourne la réponse HTTP."""
    return client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )


def auth_headers(client, username: str, password: str = "Password123!") -> dict[str, str]:
    """Retourne l'en-tête Authorization d'un utilisateur connecté."""
    response = login(client, username, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_supplier(session: Session, *, odoo_id: int = 1, name: str = "ACME SAS") -> object:
    """Crée un fournisseur de test via son repository."""
    from app.repositories import SupplierRepository

    return SupplierRepository(session).create(odoo_id=odoo_id, name=name)


def make_invoice(
    session: Session,
    supplier_id: int,
    *,
    invoice_number: str = "FAC-2026-001",
    status: str | None = None,
    issue_date=None,
) -> object:
    """Crée une facture de test via son repository."""
    from app.models.enums import InvoiceStatus
    from app.repositories import InvoiceRepository

    return InvoiceRepository(session).create(
        invoice_number=invoice_number,
        supplier_id=supplier_id,
        status=InvoiceStatus(status) if status else InvoiceStatus.SUBMITTED,
        issue_date=issue_date,
    )
