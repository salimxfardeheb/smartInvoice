"""Tests unitaires complémentaires du service d'authentification (phase 2).

Couvre les branches non exercées par l'API : conflit d'email lors de la mise
à jour d'un utilisateur, et les cas d'échec du rafraîchissement des jetons
(mauvais type, jeton révoqué/inconnu, hash différent, utilisateur introuvable
ou désactivé).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.exceptions import (
    InvalidTokenError,
    UserAlreadyExistsError,
    UserInactiveError,
)
from app.models.enums import UserRole
from app.services.auth_service import AuthService


class TestUpdateUser:
    def test_update_user_email_conflict_rejected(self, session) -> None:
        service = AuthService(session)
        first = service.create_user(
            username="alice", email="alice@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )
        service.create_user(
            username="bob", email="bob@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )

        with pytest.raises(UserAlreadyExistsError, match="déjà utilisé"):
            service.update_user(first, email="bob@example.com")

        # Pas de modification partielle appliquée.
        assert first.email == "alice@example.com"

    def test_update_user_same_email_is_idempotent(self, session) -> None:
        service = AuthService(session)
        user = service.create_user(
            username="carol", email="carol@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )

        updated = service.update_user(user, email="carol@example.com")
        assert updated.email == "carol@example.com"


class TestRefreshErrors:
    def _issue(self, session, user) -> tuple[str, str]:
        """Retourne ``(access, refresh)`` pour un utilisateur."""
        service = AuthService(session)
        pair = service.issue_token_pair(user)
        return pair.access_token, pair.refresh_token

    def test_refresh_with_access_token_rejected(self, session) -> None:
        user = AuthService(session).create_user(
            username="dave", email="dave@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )
        access, _ = self._issue(session, user)

        with pytest.raises(InvalidTokenError, match="rafraîchissement"):
            AuthService(session).refresh(access)

    def test_refresh_revoked_token_rejected(self, session) -> None:
        from app.core.security import hash_token
        from app.repositories import RefreshTokenRepository

        service = AuthService(session)
        user = service.create_user(
            username="erin", email="erin@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )
        _, refresh = self._issue(session, user)

        # Révoque manuellement le refresh token stocké.
        repo = RefreshTokenRepository(session)
        for stored in repo.list():
            if stored.token_hash == hash_token(refresh):
                repo.revoke(stored)

        with pytest.raises(InvalidTokenError, match="révoqué ou inconnu"):
            service.refresh(refresh)

    def test_refresh_unknown_token_rejected(self, session) -> None:
        from app.core.security import create_refresh_token, generate_jti

        service = AuthService(session)
        user = service.create_user(
            username="franck", email="franck@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )
        # Jeton jamais stocké : jti inconnu.
        forged = create_refresh_token(
            user.id, user.role.value, generate_jti()
        )

        with pytest.raises(InvalidTokenError, match="révoqué ou inconnu"):
            service.refresh(forged)

    def test_refresh_hash_mismatch_rejected(self, session) -> None:
        from datetime import timedelta

        from app.core.security import (
            create_refresh_token,
            generate_jti,
            hash_token,
        )
        from app.repositories import RefreshTokenRepository

        service = AuthService(session)
        user = service.create_user(
            username="gina", email="gina@example.com", role=UserRole.ACCOUNTANT,
            password="Password123!",
        )
        jti = generate_jti()
        original = create_refresh_token(user.id, user.role.value, jti)
        RefreshTokenRepository(session).create(
            user_id=user.id,
            token_hash=hash_token(original),
            jti=jti,
            expires_at=datetime.now(timezone.utc),
        )

        # Un second jeton avec le même jti mais un contenu différent (durée
        # de vie différente → hash différent).
        duplicate = create_refresh_token(
            user.id, user.role.value, jti, expires_delta=timedelta(minutes=5)
        )

        with pytest.raises(InvalidTokenError, match="invalide"):
            service.refresh(duplicate)

    def test_refresh_deactivated_user_rejected(self, session) -> None:
        service = AuthService(session)
        user = service.create_user(
            username="henri", email="henri@example.com", role=UserRole.ACCOUNTANT, password="Password123!"
        )
        service.deactivate_user(user)
        _, refresh = self._issue(session, user)

        # Le refresh token existe toujours mais l'utilisateur est inactif.
        with pytest.raises(UserInactiveError):
            service.refresh(refresh)

    def test_refresh_missing_user_rejected(self, session, monkeypatch) -> None:
        from app.core.security import create_refresh_token, generate_jti, hash_token
        from app.repositories import RefreshTokenRepository

        service = AuthService(session)
        user = service.create_user(
            username="ivan", email="ivan@example.com", role=UserRole.ACCOUNTANT,
            password="Password123!",
        )
        jti = generate_jti()
        token = create_refresh_token(user.id, user.role.value, jti)
        RefreshTokenRepository(session).create(
            user_id=user.id,
            token_hash=hash_token(token),
            jti=jti,
            expires_at=datetime.now(timezone.utc),
        )

        # L'utilisateur référencé par le jeton a disparu (ligne supprimée
        # hors session) : le service doit le signaler comme introuvable.
        def _missing_user(_user_id):
            return None

        monkeypatch.setattr(service.users, "get", _missing_user)

        with pytest.raises(InvalidTokenError, match="introuvable"):
            service.refresh(token)
