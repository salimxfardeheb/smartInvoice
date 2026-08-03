"""Endpoints de configuration (CONFIG_READ / CONFIG_WRITE).

Expose une vue « publique » et non sensible de la configuration et permet,
à un rôle privilégié, de repositionner quelques seuils non sensibles pour la
session en cours (jamais les secrets ni la connexion Odoo).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_config_service, require_permissions
from app.core.permissions import Permission
from app.schemas.config import SettingsRead, SettingsUpdate
from app.services.config_service import ConfigService

router = APIRouter()

ConfigServiceDep = Annotated[ConfigService, Depends(get_config_service)]
ConfigReadPerm = Annotated[object, Depends(require_permissions(Permission.CONFIG_READ))]
ConfigWritePerm = Annotated[
    object, Depends(require_permissions(Permission.CONFIG_WRITE))
]


@router.get(
    "",
    response_model=SettingsRead,
    summary="Lire la configuration publique",
)
def read_config(service: ConfigServiceDep = None, _: ConfigReadPerm = None) -> dict:
    """Retourne la configuration non sensible (lecture seule)."""
    return service.get()


@router.patch(
    "",
    response_model=SettingsRead,
    summary="Mettre à jour des seuils de configuration",
)
def update_config(
    payload: SettingsUpdate,
    service: ConfigServiceDep = None,
    _: ConfigWritePerm = None,
) -> dict:
    """Applique les surcharges fournies et retourne la configuration fusionnée."""
    return service.update(payload.model_dump(exclude_unset=True))