"""Tests de compatibilité PostgreSQL (sans serveur PostgreSQL).

La suite s'exécute sur SQLite : ces tests compilent le schéma et les requêtes
sensibles contre le dialecte PostgreSQL pour vérifier que la production ne
diverge pas silencieusement du comportement observé en test.

Deux points sont couverts :
- le repli ``JSONB`` (PostgreSQL) → ``JSON`` (SQLite) des colonnes de données
  extraites et du journal d'audit ;
- la requête de verrou optimiste (compare-and-swap sur ``version``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.models.audit_log import AuditLog
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice

PG = postgresql.dialect()
SQLITE = sqlite.dialect()

# Colonnes JSON portables : (modèle, nom de colonne).
JSON_COLUMNS = [
    (Invoice, "extracted_data"),
    (AuditLog, "details"),
]


class TestJsonbFallback:
    @pytest.mark.parametrize("model, column", JSON_COLUMNS)
    def test_column_is_jsonb_on_postgresql(self, model, column) -> None:
        rendered = model.__table__.c[column].type.compile(dialect=PG)
        assert rendered == "JSONB"

    @pytest.mark.parametrize("model, column", JSON_COLUMNS)
    def test_column_falls_back_to_json_on_sqlite(self, model, column) -> None:
        rendered = model.__table__.c[column].type.compile(dialect=SQLITE)
        assert rendered == "JSON"

    @pytest.mark.parametrize("model, column", JSON_COLUMNS)
    def test_create_table_ddl_matches_dialect(self, model, column) -> None:
        pg_ddl = str(CreateTable(model.__table__).compile(dialect=PG))
        sqlite_ddl = str(CreateTable(model.__table__).compile(dialect=SQLITE))
        assert f"{column} JSONB" in pg_ddl
        assert f"{column} JSON" in sqlite_ddl
        # Le repli ne doit pas fuiter dans l'autre sens.
        assert "JSONB" not in sqlite_ddl

    def test_enums_are_portable_check_constraints(self) -> None:
        """``native_enum=False`` : pas de ``CREATE TYPE`` à gérer côté PostgreSQL."""
        pg_ddl = str(CreateTable(Invoice.__table__).compile(dialect=PG))
        assert "CREATE TYPE" not in pg_ddl.upper()
        assert "VARCHAR" in pg_ddl.upper()


class TestOptimisticLockQuery:
    def _cas_statement(self):
        """Reproduit la requête émise par ``InvoiceRepository.update_cas``."""
        return (
            update(Invoice)
            .where(Invoice.id == 42, Invoice.version == 3)
            .values(error_message="boom", version=Invoice.version + 1)
        )

    @pytest.mark.parametrize("dialect", [PG, SQLITE], ids=["postgresql", "sqlite"])
    def test_cas_compiles_on_both_dialects(self, dialect) -> None:
        sql = str(
            self._cas_statement().compile(
                dialect=dialect, compile_kwargs={"literal_binds": True}
            )
        )
        normalized = " ".join(sql.split())
        assert normalized.startswith("UPDATE invoices SET")
        # Le garde de concurrence porte bien sur la version lue…
        assert "WHERE invoices.id = 42 AND invoices.version = 3" in normalized
        # …et l'incrément est calculé par la base, pas par l'application
        # (sinon deux transactions concurrentes écriraient la même version).
        assert "invoices.version + 1" in normalized

    def test_version_column_is_not_null_with_default(self) -> None:
        """Une facture existante reste comparable après migration."""
        version = Invoice.__table__.c.version
        assert not version.nullable
        assert version.server_default.arg == "0"

    @pytest.mark.parametrize("dialect", [PG, SQLITE], ids=["postgresql", "sqlite"])
    def test_cas_refreshes_updated_at(self, dialect) -> None:
        """``updated_at`` est rafraîchi par l'UPDATE bulk (``onupdate``).

        Le rendu diffère selon le dialecte (``now()`` sur PostgreSQL,
        ``CURRENT_TIMESTAMP`` sur SQLite) : seule la présence de l'affectation
        est vérifiée.
        """
        sql = " ".join(str(self._cas_statement().compile(dialect=dialect)).split())
        assert "updated_at=" in sql


class TestOptimisticLockBehaviour:
    def test_stale_version_is_rejected_and_fresh_one_wins(self, session) -> None:
        """Sémantique du CAS, vérifiée réellement (ici sur SQLite)."""
        from app.repositories import InvoiceRepository, SupplierRepository

        supplier = SupplierRepository(session).create(odoo_id=77, name="ACME")
        session.flush()
        invoices = InvoiceRepository(session)
        invoice = invoices.create(
            invoice_number="FAC-CAS-1",
            supplier_id=supplier.id,
            status=InvoiceStatus.SUBMITTED,
        )
        session.flush()

        stale_version = invoice.version
        assert invoices.update_cas(
            invoice.id, stale_version, status=InvoiceStatus.ANALYZING
        )
        assert invoices.current_version(invoice.id) == stale_version + 1
        # La même version relue une seconde fois est désormais périmée.
        assert not invoices.update_cas(
            invoice.id, stale_version, status=InvoiceStatus.VALIDATED
        )
