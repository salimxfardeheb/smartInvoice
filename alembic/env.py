"""Environnement Alembic : connecte les migrations à la base et à la metadata.

La cible de comparaison est ``app.db.base.Base.metadata`` : les modèles sont
importés (effet de bord) afin d'enregistrer toutes les tables.

L'URL est résolue dans l'ordre :
1. ``config.attributes["connection"]`` (connexion fournie par l'appelant, ex. tests) ;
2. la valeur de ``sqlalchemy.url`` dans ``alembic.ini`` ;
3. la variable d'environnement / paramètre ``DATABASE_URL`` (app.core.config).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (enregistre les tables dans Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """URL de connexion, dans l'ordre alembic.ini puis paramètres de l'app."""
    url = config.get_main_option("sqlalchemy.url")
    return url if url else get_settings().database_url


def run_migrations_offline() -> None:
    """Exécute les migrations en mode « offline » (génération de SQL)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécute les migrations en mode « online » (connexion réelle)."""
    connection = config.attributes.get("connection")
    if connection is not None:
        # Connexion fournie par l'appelant (tests) : on ne la ferme pas.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
