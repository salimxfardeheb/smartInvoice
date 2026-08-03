"""Sécurité : hash des mots de passe (bcrypt) et jetons JWT.

Les access tokens (courte durée) et refresh tokens (longue durée) partagent
la même implémentation de signature, différenciés par la revendication
``type`` (``access`` / ``refresh``). Les refresh tokens sont stockés hachés
en base (SHA-256) pour permettre révocation et rotation.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import ExpiredTokenError, InvalidTokenError

# Types de jetons.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _now() -> int:
    """Horodatage courant (epoch secondes)."""
    return int(datetime.now(timezone.utc).timestamp())


def hash_password(password: str) -> str:
    """Hache un mot de passe en clair avec bcrypt (salt aléatoire)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe en clair contre un hash bcrypt."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def generate_jti() -> str:
    """Génère un identifiant unique de jeton (jeton ID)."""
    return uuid.uuid4().hex


def hash_token(token: str) -> str:
    """Hache un jeton brut (SHA-256) pour le stockage en base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(payload: dict[str, Any]) -> str:
    """Signe un payload JWT avec la configuration courante."""
    settings = get_settings()
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _default_expires(token_type: str) -> timedelta:
    settings = get_settings()
    if token_type == TOKEN_TYPE_ACCESS:
        return timedelta(minutes=settings.access_token_expire_minutes)
    return timedelta(days=settings.refresh_token_expire_days)


def create_access_token(
    subject: str | int,
    role: str,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """Crée un access token JWT pour l'utilisateur ``subject``.

    ``expires_delta`` permet de surcharger la durée de vie (tests).
    """
    payload = {
        "sub": str(subject),
        "role": role,
        "type": TOKEN_TYPE_ACCESS,
        "jti": generate_jti(),
        "iat": _now(),
        "exp": _now() + int(
            (expires_delta or _default_expires(TOKEN_TYPE_ACCESS)).total_seconds()
        ),
    }
    return _encode(payload)


def create_refresh_token(
    subject: str | int,
    role: str,
    jti: str,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """Crée un refresh token JWT pour l'utilisateur ``subject`` avec le ``jti`` donné."""
    payload = {
        "sub": str(subject),
        "role": role,
        "type": TOKEN_TYPE_REFRESH,
        "jti": jti,
        "iat": _now(),
        "exp": _now() + int(
            (expires_delta or _default_expires(TOKEN_TYPE_REFRESH)).total_seconds()
        ),
    }
    return _encode(payload)


def decode_token(token: str) -> dict[str, Any]:
    """Décode et valide un jeton JWT (signature + expiration).

    Accepte la clé principale ainsi que les clés héritées (rotation) définies
    par ``jwt_legacy_secrets`` ; la clé principale reste celle utilisée pour
    signer (``_encode``).
    """
    settings = get_settings()
    secrets = [settings.jwt_secret_key, *settings.jwt_legacy_secret_list]
    last_error: Exception | None = None
    for secret in secrets:
        try:
            return jwt.decode(
                token, secret, algorithms=[settings.jwt_algorithm]
            )
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError("Le jeton a expiré.") from exc
        except jwt.InvalidTokenError as exc:  # noqa: PERF203 - essai des clés suivantes
            last_error = exc
    if isinstance(last_error, jwt.InvalidTokenError):
        raise InvalidTokenError("Jeton invalide.") from last_error
    raise InvalidTokenError("Jeton invalide.") from last_error
