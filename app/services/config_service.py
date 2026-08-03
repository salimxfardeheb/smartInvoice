"""Service de configuration (CONFIG_READ / CONFIG_WRITE).

Expose une vue « publique » et restreinte des paramètres applicatifs (jamais
les secrets), et permet de repositionner, pour la session en cours, un
nombre volontairement réduit de réglages non sensibles (tolérances matching,
seuil de confiance OCR).

Les surcharges sont conservées en mémoire (par défaut) ; la configuration
sous-jacente reste lue via :func:`app.core.config.get_settings`.
"""

from __future__ import annotations

import threading

from app.core.config import get_settings

# Champs non sensibles modifiables via l'API.
_TUNABLE_KEYS = (
    "ocr_confidence_threshold",
    "matching_quantity_tolerance",
    "matching_price_tolerance",
    "matching_amount_tolerance",
    "matching_tax_tolerance",
)


class ConfigService:
    """Accès et mise à jour de la configuration exposée par l'API."""

    def __init__(self) -> None:
        self._overrides: dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self) -> dict:
        """Configuration publique et non sensible (fusionnée avec les surcharges)."""
        settings = get_settings()
        base: dict = {
            "environment": settings.environment,
            "max_upload_size_mb": settings.max_upload_size_mb,
            "ocr_confidence_threshold": settings.ocr_confidence_threshold,
            "matching_quantity_tolerance": settings.matching_quantity_tolerance,
            "matching_price_tolerance": settings.matching_price_tolerance,
            "matching_amount_tolerance": settings.matching_amount_tolerance,
            "matching_tax_tolerance": settings.matching_tax_tolerance,
            "odoo_config_configured": bool(
                settings.odoo_url and settings.odoo_db and settings.odoo_username
            ),
        }
        with self._lock:
            for key, value in self._overrides.items():
                base[key] = value
        return base

    def update(self, payload: dict) -> dict:
        """Applique les surcharges fournies et retourne la config fusionnée.

        Seuls les champs de ``_TUNABLE_KEYS`` non ``None`` sont retenus ;
        les autres (secrets, connexion) sont ignorés.
        """
        with self._lock:
            for key, value in payload.items():
                if key in _TUNABLE_KEYS and value is not None:
                    self._overrides[key] = float(value)
        return self.get()