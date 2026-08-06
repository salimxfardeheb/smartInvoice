"""Endpoint de santé : état des dépendances de l'application.

``GET /healthz`` est ouvert (aucune authentification) afin d'être interrogeable
par un orchestrateur (Docker, Kubernetes) ou une sonde externe. Deux
composants sont critiques — la base de données et le stockage des documents :
leur défaillance renvoie un ``503``. La configuration Odoo est purement
informative (une instance sans Odoo configuré reste saine) et n'ouvre aucune
connexion réseau, pour que la sonde reste rapide et sans effet de bord.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.odoo import OdooClient
from app.storage import get_storage
from app.storage.base import Storage

router = APIRouter()

logger = logging.getLogger(__name__)

DbDep = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[Storage, Depends(get_storage)]

# Composants dont la panne rend l'application inapte à servir les requêtes.
_CRITICAL_CHECKS = ("database", "storage")


def _check_database(db: Session) -> dict:
    """Vérifie la base par un ``SELECT 1``."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - toute panne DB doit être rapportée
        # Sans rollback, le commit de fin de requête (``get_db``) échouerait à
        # son tour et masquerait le 503 par une erreur 500.
        db.rollback()
        logger.error("Healthcheck base de données en échec : %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc)}
    return {"status": "ok"}


def _check_storage(storage: Storage) -> dict:
    """Vérifie le stockage par un aller-retour écriture → lecture → suppression."""
    relative_path = None
    try:
        payload = b"healthz"
        relative_path = storage.save(payload, suffix=".healthz")
        if storage.open(relative_path) != payload:
            raise OSError("Le contenu relu diffère du contenu écrit.")
    except Exception as exc:  # noqa: BLE001 - toute panne stockage doit être rapportée
        logger.error("Healthcheck stockage en échec : %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc)}
    finally:
        if relative_path is not None:
            try:
                storage.delete(relative_path)
            except Exception:  # noqa: BLE001 - nettoyage best-effort
                logger.warning(
                    "Fichier de healthcheck non supprimé : %s", relative_path
                )
    return {"status": "ok"}


def _check_odoo() -> dict:
    """Rapporte l'état de la configuration Odoo (sans appel réseau)."""
    if OdooClient().is_configured:
        return {"status": "ok", "detail": "Configuration Odoo complète."}
    return {
        "status": "not_configured",
        "detail": "Synchronisation Odoo désactivée (configuration incomplète).",
    }


@router.get(
    "/healthz",
    summary="État de santé de l'application et de ses dépendances",
    include_in_schema=False,
)
def healthz(db: DbDep, storage: StorageDep, response: Response) -> dict:
    """Retourne l'état des dépendances (``503`` si un composant critique est KO)."""
    checks = {
        "database": _check_database(db),
        "storage": _check_storage(storage),
        "odoo": _check_odoo(),
    }
    degraded = [
        name for name in _CRITICAL_CHECKS if checks[name]["status"] != "ok"
    ]
    if degraded:
        response.status_code = 503
        logger.error(
            "Healthcheck dégradé : composant(s) critique(s) en échec : %s.",
            ", ".join(degraded),
        )
        return {"status": "error", "checks": checks}
    return {"status": "ok", "checks": checks}
