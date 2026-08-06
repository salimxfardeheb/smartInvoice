"""Configuration du logging applicatif (bibliothèque standard ``logging``).

Point d'entrée unique : :func:`configure_logging`, appelée depuis
``app.main.create_app`` avant tout le reste. Le format texte à plat
(horodatage, niveau, logger, message) suffit à être ingéré par un collecteur
de logs (Docker, journald, etc.) sans dépendance supplémentaire.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


def configure_logging() -> None:
    """Configure le logger racine (idempotent : sans effet si déjà appelée)."""
    global _configured
    if _configured:
        return
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        stream=sys.stdout,
    )
    _configured = True
