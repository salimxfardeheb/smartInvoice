"""Tests unitaires du client Odoo (phase 5).

Le transport XML-RPC réel est remplacé par de faux proxys : on vérifie
l'authentification (succès, échec, cache), la traduction des erreurs réseau /
timeout / ``Fault`` en exceptions métier et la transmission des arguments.
"""

from __future__ import annotations

import xmlrpc.client

import pytest

from app.core.exceptions import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooModelError,
    OdooNotConfiguredError,
)
from app.odoo import OdooClient


class _FakeCommon:
    """Proxy commun : retourne un uid configurable ou lève une erreur."""

    def __init__(self) -> None:
        self.result = 7
        self.error: Exception | None = None
        self.calls = 0

    def authenticate(self, db, username, password, context):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class _FakeModels:
    """Proxy objet : enregistre les appels et joue une file de résultats."""

    def __init__(self) -> None:
        self.results: list = []
        self.error: Exception | None = None
        self.calls: list = []

    def execute_kw(self, db, uid, password, model, method, args, kwargs=None):
        self.calls.append((db, uid, model, method, args, kwargs))
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return []


def make_client(**overrides) -> tuple[OdooClient, _FakeCommon, _FakeModels]:
    """Construit un client branché sur de faux proxys XML-RPC."""
    defaults = {
        "url": "http://odoo.example.com",
        "db": "prod",
        "username": "api",
        "password": "secret",
        "timeout": 5.0,
    }
    defaults.update(overrides)
    client = OdooClient(**defaults)
    common, models = _FakeCommon(), _FakeModels()

    def proxy(endpoint: str):
        # Reproduit l'interface d'un ``ServerProxy`` : les méthodes sont
        # exposées directement (``authenticate``, ``execute_kw``).
        fake = type("FakeServerProxy", (), {})()
        fake.authenticate = common.authenticate
        fake.execute_kw = models.execute_kw
        return fake

    client._proxy = proxy  # type: ignore[method-assign]
    return client, common, models


class TestAuthentication:
    def test_missing_configuration_raises(self) -> None:
        client, _, _ = make_client(url="", db="", username="", password="")
        with pytest.raises(OdooNotConfiguredError):
            client.authenticate()

    def test_authenticate_success_is_cached(self) -> None:
        client, common, models = make_client()
        assert client.authenticate() == 7
        client.search_read("res.partner", [], ["id"])
        client.search_read("res.partner", [], ["id"])
        # Un seul appel d'authentification malgré plusieurs appels de modèle.
        assert common.calls == 1
        assert len(models.calls) == 2
        assert models.calls[0][1] == 7  # uid transmis aux appels de modèle

    def test_authenticate_rejected_raises(self) -> None:
        client, common, _ = make_client()
        common.result = False
        with pytest.raises(OdooAuthenticationError):
            client.authenticate()

    def test_authenticate_fault_100_raises_auth_error(self) -> None:
        client, common, _ = make_client()
        common.error = xmlrpc.client.Fault(100, "Invalid database")
        with pytest.raises(OdooAuthenticationError):
            client.authenticate()


class TestErrorHandling:
    def test_timeout_mapped_to_connection_error(self) -> None:
        client, _, models = make_client()
        models.error = TimeoutError("le délai est dépassé")
        with pytest.raises(OdooConnectionError):
            client.search_read("res.partner", [], ["id"])

    def test_connection_refused_mapped_to_connection_error(self) -> None:
        client, _, models = make_client()
        models.error = ConnectionRefusedError(61, "refusée")
        with pytest.raises(OdooConnectionError):
            client.search_read("res.partner", [], ["id"])

    def test_protocol_error_mapped_to_connection_error(self) -> None:
        client, _, models = make_client()
        models.error = xmlrpc.client.ProtocolError(
            "http://odoo/xmlrpc/2/object", 500, "Internal Server Error", {}
        )
        with pytest.raises(OdooConnectionError):
            client.search_read("res.partner", [], ["id"])

    def test_fault_404_mapped_to_model_error(self) -> None:
        client, _, models = make_client()
        models.error = xmlrpc.client.Fault(404, "Element res.partner.foo does not exist")
        with pytest.raises(OdooModelError):
            client.search_read("res.partner", [], ["foo"])

    def test_connection_error_resets_uid(self) -> None:
        client, common, models = make_client()
        assert client.authenticate() == 7
        models.error = TimeoutError("timeout")
        with pytest.raises(OdooConnectionError):
            client.search_read("res.partner", [], ["id"])
        assert client._uid is None

        # La reprise ré-authentifie.
        models.error = None
        client.search_read("res.partner", [], ["id"])
        assert common.calls == 2


class TestModelCalls:
    def test_search_read_passes_domain_fields_and_pagination(self) -> None:
        client, _, models = make_client()
        models.results = [[{"id": 1, "name": "ACME"}]]
        rows = client.search_read(
            "res.partner",
            [["name", "ilike", "ACME"]],
            ["id", "name"],
            limit=20,
            offset=5,
        )
        assert rows == [{"id": 1, "name": "ACME"}]
        _, uid, model, method, args, kwargs = models.calls[0]
        assert (model, method) == ("res.partner", "search_read")
        assert uid == 7
        assert args[0] == [["name", "ilike", "ACME"]]
        assert kwargs == {"fields": ["id", "name"], "limit": 20, "offset": 5}

    def test_search_passes_domain(self) -> None:
        client, _, models = make_client()
        client.search("res.partner", [["id", "in", [1, 2]]], limit=10)
        _, _, model, method, args, kwargs = models.calls[0]
        assert (model, method) == ("res.partner", "search")
        assert kwargs == {"limit": 10}

    def test_read_passes_ids(self) -> None:
        client, _, models = make_client()
        client.read("product.product", [1, 2], ["id", "default_code"])
        _, _, model, method, args, kwargs = models.calls[0]
        assert (model, method) == ("product.product", "read")
        assert args[0] == [1, 2]
        assert kwargs == {"fields": ["id", "default_code"]}
