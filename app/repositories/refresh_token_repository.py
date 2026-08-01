"""Repository de l'entité ``RefreshToken``."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Accès aux données des jetons de rafraîchissement."""

    model = RefreshToken

    def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        jti: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Enregistre un jeton de rafraîchissement (seul le hash est stocké)."""
        return self.add(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                jti=jti,
                expires_at=expires_at,
            )
        )

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Retourne le jeton correspondant à une empreinte, ou ``None``."""
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.session.scalars(stmt).first()

    def get_by_jti(self, jti: str) -> RefreshToken | None:
        """Retourne le jeton correspondant à un ``jti``, ou ``None``."""
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        return self.session.scalars(stmt).first()

    def revoke(self, token: RefreshToken) -> RefreshToken:
        """Révoque un jeton (horodatage de révocation)."""
        self.update(token, revoked_at=datetime.now(timezone.utc))
        return token

    def revoke_all_for_user(self, user_id: int) -> int:
        """Révoque tous les jetons actifs d'un utilisateur (retourne le compte)."""
        result = self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        return result.rowcount or 0

    def list_active_for_user(self, user_id: int) -> list[RefreshToken]:
        """Retourne les jetons actifs (non révoqués) d'un utilisateur."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        return list(self.session.scalars(stmt))
