"""Dépendances FastAPI : utilisateur courant et contrôle des permissions."""

from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidTokenError,
    PermissionDeniedError,
    RateLimitExceededError,
    UserInactiveError,
)
from app.core.permissions import Permission, permissions_for
from app.core.ratelimit import get_limiter
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.ocr.base import OcrEngine, get_ocr_engine
from app.repositories import (
    AnomalyRepository,
    AuditLogRepository,
    TaskRepository,
    UserRepository,
)
from app.services.auth_service import AuthService
from app.services.config_service import ConfigService
from app.services.confirmation_service import BuyerConfirmationService
from app.services.invoice_service import InvoiceService
from app.services.matching_service import MatchingService
from app.services.ocr_service import OcrService
from app.services.odoo_service import OdooSyncService
from app.services.task_manager import TaskManager, get_default_task_manager
from app.services.validation_service import ValidationService
from app.storage import get_storage
from app.storage.base import Storage

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


def get_invoice_service(
    db: Session = Depends(get_db), storage: Storage = Depends(get_storage)
) -> InvoiceService:
    """Fabrique le service des factures lié à la session et au stockage."""
    return InvoiceService(db, storage)


def get_ocr_engine_dep() -> OcrEngine:
    """Dépendance FastAPI : moteur OCR (remplaçable dans les tests)."""
    return get_ocr_engine()


def get_ocr_service(
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    engine: OcrEngine = Depends(get_ocr_engine_dep),
) -> OcrService:
    """Fabrique le service OCR lié à la session, au stockage et au moteur."""
    return OcrService(db, storage, engine=engine)


def get_matching_service(db: Session = Depends(get_db)) -> MatchingService:
    """Fabrique le service de matching lié à la session courante."""
    return MatchingService(db)


def get_validation_service(db: Session = Depends(get_db)) -> ValidationService:
    """Fabrique le service de validation comptable lié à la session courante."""
    return ValidationService(db)


def get_audit_log_repository(
    db: Session = Depends(get_db),
) -> AuditLogRepository:
    """Fabrique le repository du journal d'audit lié à la session courante."""
    return AuditLogRepository(db)


def get_anomaly_repository(
    db: Session = Depends(get_db),
) -> AnomalyRepository:
    """Fabrique le repository des anomalies lié à la session courante."""
    return AnomalyRepository(db)


def get_odoo_sync_service(db: Session = Depends(get_db)) -> OdooSyncService:
    """Fabrique le service de synchronisation Odoo lié à la session courante."""
    return OdooSyncService(db)


def get_confirmation_service(db: Session = Depends(get_db)) -> BuyerConfirmationService:
    """Fabrique le service de confirmation acheteur lié à la session courante."""
    return BuyerConfirmationService(db)


def get_config_service(db: Session = Depends(get_db)) -> ConfigService:
    """Fabrique le service de configuration lié à la session courante."""
    return ConfigService(db)


def get_task_manager(db: Session = Depends(get_db)) -> TaskManager:
    """Fabrique le gestionnaire de tâches asynchrones (remplaçable en test)."""
    return get_default_task_manager()


def get_task_repository(db: Session = Depends(get_db)) -> TaskRepository:
    """Fabrique le repository des tâches asynchrones lié à la session courante."""
    return TaskRepository(db)


def rate_limit(key_prefix: str) -> Callable[[Request], None]:
    """Fabrique une dépendance de limitation (clé = adresse IP du client).

    Si le rate limiting est désactivé (config), la dépendance ne fait rien.
    Sélection : ``Depends(rate_limit("login"))``.
    """

    def dependency(request: Request) -> None:
        limiter = get_limiter()
        if limiter is None:
            return
        client = request.client.host if request.client else "unknown"
        allowed, _, _ = limiter.allow(f"{key_prefix}:{client}")
        if not allowed:
            raise RateLimitExceededError(
                "Trop de tentatives. Merci de réessayer plus tard."
            )

    return dependency
