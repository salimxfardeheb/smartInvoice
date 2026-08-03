"""Schémas de l'API Configuration (CONFIG_READ / CONFIG_WRITE).

La configuration exposée reste volontairement restreinte : les secrets
(mot de passe Odoo, clé JWT) et les paramètres de connexion ne sont jamais
retournés ni modifiables via l'API. Seuls les tolérances de matching et
quelques seuils métier non sensibles sont exposés.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    """Vue publique et « en lecture seule » de la configuration active."""

    environment: str
    max_upload_size_mb: int
    ocr_confidence_threshold: float = Field(ge=0.0, le=1.0)
    matching_quantity_tolerance: float = Field(ge=0.0, le=1.0)
    matching_price_tolerance: float = Field(ge=0.0, le=1.0)
    matching_amount_tolerance: float = Field(ge=0.0, le=1.0)
    matching_tax_tolerance: float = Field(ge=0.0, le=1.0)
    odoo_config_configured: bool


class SettingsUpdate(BaseModel):
    """Champs modifiables via l'API (reposition en mémoire pour la session)."""

    ocr_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    matching_quantity_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)
    matching_price_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)
    matching_amount_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)
    matching_tax_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)