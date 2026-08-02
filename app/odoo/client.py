"""Client XML-RPC vers le serveur Odoo.

Gère l'authentification (endpoint ``/xmlrpc/2/common``), les appels de modèle
(endpoint ``/xmlrpc/2/object``), la configuration via variables
d'environnement (:mod:`app.core.config`) et la traduction des erreurs réseau,
de timeout et de protocole en exceptions métier (:mod:`app.core.exceptions`).

Le client est volontairement indépendant de la couche service : les tests
peuvent le remplacer par un bouchon implémentant la même interface
(``authenticate``, ``search_read``, ``search``, ``read``).
"""

from __future__ import annotations

import socket
import xmlrpc.client

from app.core.config import get_settings
from app.core.exceptions import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooError,
    OdooModelError,
    OdooNotConfiguredError,
)


class _TimeoutMixin:
    """Applique un délai maximal (connect + lecture) à la connexion créée."""

    timeout: float

    def make_connection(self, host: str):
        connection = super().make_connection(host)  # type: ignore[misc]
        connection.timeout = self.timeout
        return connection


class _HttpTimeoutTransport(_TimeoutMixin, xmlrpc.client.Transport):
    """Transport XML-RPC HTTP avec timeout."""

    def __init__(self, *, timeout: float) -> None:
        xmlrpc.client.Transport.__init__(
            self, use_datetime=True, use_builtin_types=True
        )
        self.timeout = timeout


class _HttpsTimeoutTransport(_TimeoutMixin, xmlrpc.client.SafeTransport):
    """Transport XML-RPC HTTPS avec timeout."""

    def __init__(self, *, timeout: float) -> None:
        xmlrpc.client.SafeTransport.__init__(
            self, use_datetime=True, use_builtin_types=True
        )
        self.timeout = timeout


# Erreurs réseau / protocole traduites en :class:`OdooConnectionError`.
_NETWORK_ERRORS = (
    OSError,  # TimeoutError, connexion refusée, DNS, reset...
    xmlrpc.client.ProtocolError,  # réponses HTTP 4xx/5xx
    xmlrpc.client.ResponseError,  # réponse XML-RPC mal formée
)


class OdooClient:
    """Client de connexion à Odoo (endpoints XML-RPC commun et objet).

    La configuration provient des variables d'environnement par défaut, mais
    peut être surchargée par paramètres pour faciliter les tests.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        db: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.url = (url or settings.odoo_url).rstrip("/")
        self.db = db or settings.odoo_db
        self.username = username or settings.odoo_username
        self.password = password or settings.odoo_password
        self.timeout = timeout if timeout is not None else settings.odoo_timeout_seconds

        self._uid: int | None = None
        self._common: xmlrpc.client.ServerProxy | None = None
        self._models: xmlrpc.client.ServerProxy | None = None

    # --- Configuration -------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """Indique si les paramètres de connexion sont complets."""
        return all((self.url, self.db, self.username, self.password))

    # --- Authentification ------------------------------------------------------

    def authenticate(self) -> int:
        """Authentifie l'utilisateur et retourne son identifiant Odoo.

        L'identifiant est mis en cache pour les appels suivants. Lève
        :class:`OdooNotConfiguredError` si la configuration est incomplète et
        :class:`OdooAuthenticationError` si les identifiants sont refusés.
        """
        if self._uid is not None:
            return self._uid
        if not self.is_configured:
            raise OdooNotConfiguredError(
                "La configuration Odoo (URL, base, utilisateur, mot de passe) "
                "est incomplète."
            )

        common = self._get_common()
        uid = self._call(
            lambda: common.authenticate(
                self.db, self.username, self.password, {}
            )
        )
        if not uid:
            raise OdooAuthenticationError(
                "Authentification Odoo refusée : vérifiez la base, "
                "l'utilisateur et le mot de passe."
            )
        self._uid = int(uid)
        return self._uid

    # --- Appels de modèle --------------------------------------------------------

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Recherche et lit les enregistrements d'un modèle Odoo.

        Retourne une liste de dictionnaires contenant les ``fields`` demandés
        (les champs relationnels sont des tuples ``(id, nom)``).
        """
        uid = self.authenticate()
        models = self._get_models()
        kwargs: dict = {"fields": fields, "offset": offset}
        if limit is not None:
            kwargs["limit"] = limit
        return self._call(
            lambda: models.execute_kw(
                self.db, uid, self.password, model, "search_read", [domain], kwargs
            )
        )

    def search(self, model: str, domain: list, *, limit: int | None = None) -> list[int]:
        """Recherche les identifiants d'enregistrements d'un modèle Odoo."""
        uid = self.authenticate()
        models = self._get_models()
        kwargs: dict = {}
        if limit is not None:
            kwargs["limit"] = limit
        return self._call(
            lambda: models.execute_kw(
                self.db, uid, self.password, model, "search", [domain], kwargs
            )
        )

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        """Lit les enregistrements d'un modèle Odoo par identifiants."""
        uid = self.authenticate()
        models = self._get_models()
        return self._call(
            lambda: models.execute_kw(
                self.db,
                uid,
                self.password,
                model,
                "read",
                [ids],
                {"fields": fields},
            )
        )

    # --- Internes -----------------------------------------------------------------

    def _get_common(self) -> xmlrpc.client.ServerProxy:
        """Proxy du endpoint commun (authentification)."""
        if self._common is None:
            self._common = self._proxy(f"{self.url}/xmlrpc/2/common")
        return self._common

    def _get_models(self) -> xmlrpc.client.ServerProxy:
        """Proxy du endpoint objet (appels de modèle)."""
        if self._models is None:
            self._models = self._proxy(f"{self.url}/xmlrpc/2/object")
        return self._models

    def _proxy(self, endpoint: str) -> xmlrpc.client.ServerProxy:
        """Crée un ``ServerProxy`` avec transport HTTP(S) et timeout."""
        if endpoint.startswith("https://"):
            transport = _HttpsTimeoutTransport(timeout=self.timeout)
        else:
            transport = _HttpTimeoutTransport(timeout=self.timeout)
        return xmlrpc.client.ServerProxy(
            endpoint,
            transport=transport,
            use_datetime=True,
            use_builtin_types=True,
        )

    def _call(self, fn):
        """Exécute un appel et traduit les erreurs XML-RPC/réseau en métier.

        En cas d'erreur réseau, l'identifiant authentifié est réinitialisé
        afin qu'un prochain appel tente une nouvelle authentification.
        """
        try:
            return fn()
        except xmlrpc.client.Fault as exc:
            raise self._map_fault(exc) from exc
        except _NETWORK_ERRORS as exc:
            self._uid = None
            raise OdooConnectionError(
                f"Impossible de joindre le serveur Odoo : {exc}"
            ) from exc
        except OdooError:
            raise
        except Exception as exc:  # pragma: no cover - filet de sécurité
            self._uid = None
            raise OdooConnectionError(f"Appel Odoo inattendu : {exc}") from exc

    @staticmethod
    def _map_fault(fault: xmlrpc.client.Fault) -> OdooError:
        """Traduit une ``Fault`` Odoo en exception métier."""
        code = getattr(fault, "faultCode", None)
        message = getattr(fault, "faultString", str(fault))
        # Codes Odoo : 100 = identifiants/base invalides, 200 = droits insuffisants,
        # 404 = modèle/champ inconnu, 400 = domaine ou valeurs invalides.
        if code in (100, 200):
            return OdooAuthenticationError(f"Odoo a refusé l'accès : {message}")
        if code in (400, 404):
            return OdooModelError(f"Odoo a rejeté l'appel : {message}")
        return OdooError(f"Erreur Odoo (code {code}) : {message}")
