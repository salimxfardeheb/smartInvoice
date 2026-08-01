"""Modèle « refresh token » : stockage haché et révocation des jetons."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.user import User


class RefreshToken(Base, TimestampMixin):
    """Jeton de rafraîchissement émis pour un utilisateur.

    Le jeton brut n'est jamais stocké : seule son empreinte SHA-256
    (``token_hash``) est persistée. ``jti`` est la revendication unique du
    jeton, utilisée pour retrouver et révoquer une session.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    jti: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"revoked_at={self.revoked_at}>"
        )
