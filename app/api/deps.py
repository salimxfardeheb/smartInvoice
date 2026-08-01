"""Dépendances FastAPI : utilisateur courant et contrôle des permissions."""

from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidTokenError,
    PermissionDeniedError,
    UserInactiveError,
)
from app.core.permissions import Permission, permissions_for
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.repositories import UserRepository
from app.services.auth_service import AuthService

# URL du endpoint de connexion (formulaire OAuth2) pour l'UI Swagger.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_db() -> Generator[Session, None, None]:
    """Session de base de données par requête (commit/rollback automatiques)."""
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    """Résout l'utilisateur authentifié à partir de l'access token JWT."""
    payload = decode_token(token)
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise InvalidTokenError("Un jeton d'accès est attendu.")

    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("Jeton invalide : sujet manquant.")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise InvalidTokenError("Jeton invalide : sujet illisible.") from None

    user = UserRepository(db).get(user_id)
    if user is None:
        raise InvalidTokenError("Utilisateur introuvable.")
    if not user.is_active:
        raise UserInactiveError("Ce compte est désactivé.")
    return user


def require_permissions(*permissions: Permission) -> Callable[[User], User]:
    """Fabrique une dépendance exigeant toutes les permissions données.

    Utilisation : ``Depends(require_permissions(Permission.USER_WRITE))``.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        granted = permissions_for(user.role)
        missing = set(permissions) - granted
        if missing:
            raise PermissionDeniedError(
                "Permission requise : "
                + ", ".join(sorted(p.value for p in missing))
                + "."
            )
        return user

    return dependency


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Fabrique une dépendance exigeant que l'utilisateur ait un des rôles."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "Rôle requis : " + ", ".join(role.value for role in roles) + "."
            )
        return user

    return dependency


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Fabrique le service d'authentification lié à la session courante."""
    return AuthService(db)
