"""Repository de l'entité ``User``."""

from __future__ import annotations

from sqlalchemy import select

from app.models.enums import UserRole
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Accès aux données des utilisateurs."""

    model = User

    def create(
        self,
        *,
        username: str,
        email: str,
        hashed_password: str,
        full_name: str | None = None,
        role: UserRole = UserRole.ACCOUNTANT,
        is_active: bool = True,
    ) -> User:
        """Crée un utilisateur (le hash du mot de passe est fourni par l'appelant)."""
        return self.add(
            User(
                username=username,
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                role=role,
                is_active=is_active,
            )
        )

    def get_by_username(self, username: str) -> User | None:
        """Retourne l'utilisateur correspondant au nom, ou ``None``."""
        stmt = select(User).where(User.username == username)
        return self.session.scalars(stmt).first()

    def get_by_email(self, email: str) -> User | None:
        """Retourne l'utilisateur correspondant à l'email, ou ``None``."""
        stmt = select(User).where(User.email == email)
        return self.session.scalars(stmt).first()

    def list_active(self) -> list[User]:
        """Retourne les utilisateurs actifs."""
        stmt = select(User).where(User.is_active.is_(True)).order_by(User.id)
        return list(self.session.scalars(stmt))

    def filter(
        self,
        *,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """Liste paginée des utilisateurs, avec filtre optionnel par état."""
        stmt = select(User).order_by(User.id).limit(limit).offset(offset)
        if active is not None:
            stmt = stmt.where(User.is_active.is_(active))
        return list(self.session.scalars(stmt))
