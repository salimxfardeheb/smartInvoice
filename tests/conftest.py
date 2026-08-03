"""Fixtures partagées des tests SmartInvoice.

Les tests utilisent une base SQLite en mémoire isolée (``StaticPool``) et les
contraintes d'intégrité référentielle sont activées via ``PRAGMA foreign_keys``
afin de reproduire fidèlement le comportement PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (enregistre les modèles dans Base.metadata)
from app.db.base import Base

ROOT = Path(__file__).resolve().parents[1]

STATUS_INVOICE = "Déposée"


def _enable_foreign_keys(dbapi_connection, _record) -> None:  # pragma: no cover
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_db, get_task_manager
    from app.main import create_app
    from app.services.task_manager import InlineExecutor, TaskManager

    app = create_app()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

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
