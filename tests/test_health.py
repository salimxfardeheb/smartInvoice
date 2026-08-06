"""Tests de l'endpoint de santé ``GET /healthz``.

Couvre le cas nominal (200 avec tous les composants sains, sans
authentification), la défaillance de chaque composant critique (503) et le
caractère informatif de la configuration Odoo.
"""

from __future__ import annotations

import pytest

from app.api.deps import get_db
from app.storage import get_storage
from app.storage.base import Storage


@pytest.fixture()
def health_client(client, tmp_path):
    """Client avec un stockage local isolé (racine temporaire)."""
    from app.storage.local import LocalStorage

    client.app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield client
    client.app.dependency_overrides.pop(get_storage, None)


class _BrokenStorage(Storage):
    """Stockage dont toute écriture échoue (disque plein / droits manquants)."""

    def save(self, content: bytes, *, suffix: str) -> str:
        raise OSError("Écriture impossible sur le stockage.")

    def open(self, relative_path: str) -> bytes:  # pragma: no cover - jamais atteint
        raise OSError("Lecture impossible.")

    def exists(self, relative_path: str) -> bool:  # pragma: no cover
        return False

    def delete(self, relative_path: str) -> None:  # pragma: no cover
        return None

    def path(self, relative_path: str):  # pragma: no cover
        raise OSError("Chemin indisponible.")


class TestHealthz:
    def test_healthz_ok_without_auth(self, health_client) -> None:
        response = health_client.get("/healthz")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["database"]["status"] == "ok"
        assert body["checks"]["storage"]["status"] == "ok"
        assert "odoo" in body["checks"]

    def test_healthz_reports_odoo_not_configured(self, health_client) -> None:
        # Les tests tournent sans configuration Odoo : l'instance reste saine.
        response = health_client.get("/healthz")
        assert response.status_code == 200, response.text
        assert response.json()["checks"]["odoo"]["status"] == "not_configured"

    def test_healthz_ok_when_odoo_configured(self, health_client, monkeypatch) -> None:
        from app.api.routes import health as health_route

        class _ConfiguredClient:
            is_configured = True

        monkeypatch.setattr(health_route, "OdooClient", _ConfiguredClient)
        response = health_client.get("/healthz")
        assert response.status_code == 200, response.text
        assert response.json()["checks"]["odoo"]["status"] == "ok"

    def test_healthz_503_when_database_down(self, health_client) -> None:
        class _BrokenSession:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError("Base de données injoignable.")

            def rollback(self) -> None:
                return None

            def commit(self) -> None:
                return None

        health_client.app.dependency_overrides[get_db] = lambda: _BrokenSession()
        try:
            response = health_client.get("/healthz")
        finally:
            health_client.app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 503, response.text
        body = response.json()
        assert body["status"] == "error"
        assert body["checks"]["database"]["status"] == "error"
        assert "injoignable" in body["checks"]["database"]["detail"]

    def test_healthz_503_when_storage_unwritable(self, health_client) -> None:
        health_client.app.dependency_overrides[get_storage] = lambda: _BrokenStorage()
        response = health_client.get("/healthz")

        assert response.status_code == 503, response.text
        body = response.json()
        assert body["status"] == "error"
        assert body["checks"]["storage"]["status"] == "error"
        # La base reste saine : seul le stockage est en cause.
        assert body["checks"]["database"]["status"] == "ok"

    def test_healthz_leaves_no_probe_file_behind(self, health_client, tmp_path) -> None:
        assert health_client.get("/healthz").status_code == 200
        assert list(tmp_path.rglob("*.healthz")) == []
