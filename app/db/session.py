"""Moteur et sessions SQLAlchemy.

Fournit un ``engine`` applicatif ainsi qu'une fabrique de sessions. Les tests
ne doivent pas importer ce module directement pour l'exécution (ils créent
leur propre moteur SQLite isolé).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine: Engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    echo=get_settings().echo_sql,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_session() -> Generator[Session, None, None]:
    """Dépendance FastAPI : fournit une session transactionnelle par requête."""
    with SessionLocal() as session:
        yield session
