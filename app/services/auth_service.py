"""Service d'authentification et de gestion des utilisateurs.

Regroupe la logique : inscription (avec bootstrap du premier administrateur),
connexion, émission/rotation/révocation des jetons, désactivation et
changement de mot de passe. Les mots de passe ne transitent jamais en clair
vers la base (hash bcrypt).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
    UserInactiveError,
)
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_jti,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.repositories import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenPair


class AuthService:
    """Opérations d'authentification et de gestion des comptes."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    # --- Inscription & connexion --------------------------------------------

    def register(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str | None = None,
        role: UserRole | None = None,
    ) -> TokenPair:
        """Crée un compte et retourne une paire de jetons (auto-login).

        Le tout premier compte créé reçoit le rôle Administrateur (bootstrap) ;
        les comptes suivants prennent le rôle fourni (Comptable par défaut).
        """
        self._ensure_username_and_email_available(username, email)
        effective_role = UserRole.ADMIN if self.users.count() == 0 else (
            role or UserRole.ACCOUNTANT
        )
        user = self.users.create(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=effective_role,
        )
        return self.issue_token_pair(user)

    def authenticate(self, *, username: str, password: str) -> User:
        """Authentifie un utilisateur par nom/email + mot de passe."""
        user = self.users.get_by_username(username) or self.users.get_by_email(
            username
        )
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Identifiants incorrects.")
        if not user.is_active:
            raise UserInactiveError("Ce compte est désactivé.")
        return user

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str | None = None,
        role: UserRole = UserRole.ACCOUNTANT,
    ) -> User:
        """Crée un utilisateur (sans émission de jetons) — usage administrateur."""
        self._ensure_username_and_email_available(username, email)
        return self.users.create(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )

    def update_user(
        self,
        user: User,
        *,
        full_name: str | None = None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Met à jour un utilisateur en vérifiant l'unicité de l'email."""
        fields: dict = {}
        if full_name is not None:
            fields["full_name"] = full_name
        if email is not None:
            existing = self.users.get_by_email(email)
            if existing is not None and existing.id != user.id:
                raise UserAlreadyExistsError("Cet email est déjà utilisé.")
            fields["email"] = email
        if role is not None:
            fields["role"] = role
        if is_active is not None:
            fields["is_active"] = is_active
        return self.users.update(user, **fields)

    def deactivate_user(self, user: User) -> User:
        """Désactive un compte et révoque l'ensemble de ses refresh tokens."""
        self.refresh_tokens.revoke_all_for_user(user.id)
        return self.users.update(user, is_active=False)

    def change_password(
        self, user: User, *, current_password: str, new_password: str
    ) -> None:
        """Change le mot de passe et révoque les sessions existantes."""
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError("Le mot de passe actuel est incorrect.")
        self.users.update(user, hashed_password=hash_password(new_password))
        self.refresh_tokens.revoke_all_for_user(user.id)

    # --- Jetons ---------------------------------------------------------------

    def issue_token_pair(self, user: User) -> TokenPair:
        """Émet un access + refresh token, et persiste le refresh token (haché)."""
        settings = get_settings()
        jti = generate_jti()
        access = create_access_token(user.id, user.role.value)
        refresh = create_refresh_token(user.id, user.role.value, jti)
        self.refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(refresh),
            jti=jti,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
        return TokenPair(access_token=access, refresh_token=refresh)

    def refresh(self, refresh_token: str) -> TokenPair:
        """Rafraîchit un access token via un refresh token (rotation)."""
        payload = decode_token(refresh_token)
        if payload.get("type") != TOKEN_TYPE_REFRESH:
            raise InvalidTokenError("Un jeton de rafraîchissement est attendu.")

        stored = self.refresh_tokens.get_by_jti(payload.get("jti", ""))
        if stored is None or stored.revoked_at is not None:
            raise InvalidTokenError("Jeton de rafraîchissement révoqué ou inconnu.")
        if stored.token_hash != hash_token(refresh_token):
            raise InvalidTokenError("Jeton de rafraîchissement invalide.")

        user = self.users.get(stored.user_id)
        if user is None:
            raise InvalidTokenError("Utilisateur introuvable.")
        if not user.is_active:
            raise UserInactiveError("Ce compte est désactivé.")

        self.refresh_tokens.revoke(stored)
        return self.issue_token_pair(user)

    def logout(self, refresh_token: str) -> None:
        """Révoque un refresh token (déconnexion)."""
        stored = self.refresh_tokens.get_by_token_hash(hash_token(refresh_token))
        if stored is not None and stored.revoked_at is None:
            self.refresh_tokens.revoke(stored)

    # --- Helpers ---------------------------------------------------------------

    def _ensure_username_and_email_available(
        self, username: str, email: str
    ) -> None:
        if self.users.get_by_username(username) or self.users.get_by_email(email):
            raise UserAlreadyExistsError(
                "Un utilisateur avec ce nom ou cet email existe déjà."
            )
