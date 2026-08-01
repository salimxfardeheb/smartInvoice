"""Modèle « utilisateur » : comptes applicatifs SmartInvoice.

La gestion de l'authentification (JWT, hash des mots de passe) relève de la
phase 2 ; ce modèle pose le socle persistant (identité, email, rôle,
activation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole, enum_values
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.refresh_token import RefreshToken


class User(Base, TimestampMixin):
    """Utilisateur de l'application (comptable, acheteur ou administrateur)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Comptable', 'Acheteur', 'Administrateur')", name="role"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=UserRole.ACCOUNTANT,
        server_default=UserRole.ACCOUNTANT.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
