"""Tests des migrations Alembic : upgrade, downgrade, parité de schéma et
applicabilité du modèle sur une base migrée."""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base

HEAD = "0001_initial_schema"

EXPECTED_TABLES = {
    "users",
    "suppliers",
    "purchase_orders",
    "invoices",
    "invoice_lines",
    "anomalies",
}


def _fresh_engine() -> Engine:
    eng = create_engine("sqlite://", poolclass=StaticPool)
    return eng


def _run_upgrade(alembic_config, eng: Engine) -> None:
    connection = eng.connect()
    alembic_config.attributes["connection"] = connection
    command.upgrade(alembic_config, "head")
    connection.close()


class TestMigrations:
    def test_upgrade_creates_all_tables(self, migrated_engine) -> None:
        inspector = inspect(migrated_engine)
        assert set(inspector.get_table_names()) >= EXPECTED_TABLES

    def test_upgrade_records_version(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == HEAD

    def test_upgrade_enforces_unique_invoice_constraint(self, migrated_engine) -> None:
        Session = sessionmaker(bind=migrated_engine)
        session = Session()
        session.execute(
            text(
                "INSERT INTO suppliers (odoo_id, name) VALUES (1, 'ACME')"
            )
        )
        session.execute(
            text(
                "INSERT INTO invoices (invoice_number, supplier_id) "
                "VALUES ('FAC-001', 1)"
            )
        )
        session.commit()

        try:
            session.execute(
                text(
                    "INSERT INTO invoices (invoice_number, supplier_id) "
                    "VALUES ('FAC-001', 1)"
                )
            )
            session.commit()
            raise AssertionError("Le doublon (fournisseur, numéro) aurait dû être rejeté")
        except Exception as exc:  # IntegrityError / sqlite3.IntegrityError
            assert "UNIQUE" in str(exc).upper() or "INTEGRITY" in str(exc).upper()
        finally:
            session.close()

    def test_downgrade_removes_all_tables(self, alembic_config, migrated_engine) -> None:
        connection = migrated_engine.connect()
        alembic_config.attributes["connection"] = connection
        command.downgrade(alembic_config, "base")
        connection.close()

        inspector = inspect(migrated_engine)
        remaining = set(inspector.get_table_names()) - {"alembic_version"}
        assert remaining == set()

    def test_upgrade_then_upgrade_is_noop(self, alembic_config, migrated_engine) -> None:
        connection = migrated_engine.connect()
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
        connection.close()

    def test_schema_parity_create_all_vs_migration(self, alembic_config) -> None:
        """Le schéma produit par la migration doit être identique à celui des
        modèles (``Base.metadata.create_all``), colonne par colonne."""
        eng_models = _fresh_engine()
        Base.metadata.create_all(eng_models)

        eng_migration = _fresh_engine()
        _run_upgrade(alembic_config, eng_migration)

        def describe(eng: Engine) -> dict[str, list[tuple[str, str]]]:
            inspector = inspect(eng)
            out: dict[str, list[tuple[str, str]]] = {}
            for table in sorted(inspector.get_table_names()):
                if table == "alembic_version":
                    continue
                out[table] = sorted(
                    (c["name"], str(c["type"])) for c in inspector.get_columns(table)
                )
            return out

        assert describe(eng_models) == describe(eng_migration)
