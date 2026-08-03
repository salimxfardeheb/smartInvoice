"""Service de configuration (CONFIG_READ / CONFIG_WRITE).

Expose une vue « publique » et restreinte des paramètres applicatifs (jamais
les secrets), et permet de repositionner un nombre réduit de réglages non
sensibles (tolérances matching, seuil de confiance OCR).

Les surcharges sont persistées en base (table ``settings``) afin de survivre
au redémarrage et d'être lues dans le contexte de la requête ; la valeur de
référence reste la configuration applicative
(:func:`app.core.config.get_settings`) lorsqu'aucun réglage n'est défini.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.repositories.setting_repository import SettingRepository

# Champs non sensibles modifiables via l'API.
# (clef de réglage → attribut de configuration de référence dans le pire cas.)
_TUNABLE_KEYS = (
    "ocr_confidence_threshold",
    "matching_quantity_tolerance",
    "matching_price_tolerance",
    "matching_amount_tolerance",
    "matching_tax_tolerance",
)

# Correspondance clef réglage → attribut Settings utilisé comme fallback.
_REFERENCE_KEY_MAP: dict[str, str] = {
    "ocr_confidence_threshold": "ocr_confidence_threshold",
    "matching_quantity_tolerance": "matching_quantity_tolerance",
    "matching_price_tolerance": "matching_price_tolerance",
    "matching_amount_tolerance": "matching_amount_tolerance",
    "matching_tax_tolerance": "matching_tax_tolerance",
}


def _settings_to_public(settings: Settings) -> dict:
    """Vue publique (non sensible) de la configuration de référence."""
    return {
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


class ConfigService:
    """Accès et mise à jour de la configuration, persistée en base."""

    def __init__(self, db: Session) -> None:
        self._repo = SettingRepository(db)

    def get(self) -> dict:
        """Configuration publique fusionnée (réglages stockés par-dessus la base)."""
        base = _settings_to_public(get_settings())
        for key in _TUNABLE_KEYS:
            stored = self._repo.get_typed(key, default=None)
            if stored is not None:
                base[key] = stored
        return base

    def update(self, payload: dict) -> dict:
        """Persiste les surcharges non sensibles fournies, puis retourne la fusion.

        Seuls les champs de ``_TUNABLE_KEYS`` non ``None`` sont retenus ;
        les autres (secrets, connexion) sont ignorés.
        """
        changes = {
            key: float(payload[key])
            for key in _TUNABLE_KEYS
            if key in payload and payload[key] is not None
        }
        if changes:
            self._repo.set_many(changes)
        return self.get()

    def tolerance(self, key: str) -> float:
        """Tolérance effective (réglage stocké prioritaire sur la config)."""
        if key in _REFERENCE_KEY_MAP:
            stored = self._repo.get_typed(key, default=None)
            if stored is not None:
                return float(stored)
            return float(getattr(get_settings(), _REFERENCE_KEY_MAP[key]))
        raise KeyError(key)