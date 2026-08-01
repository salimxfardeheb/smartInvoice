"""Schémas de l'entité « utilisateur »."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    """Création d'un utilisateur (mot de passe en clair, hashé côté service)."""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=150)
    role: UserRole = UserRole.ACCOUNTANT


class UserUpdate(BaseModel):
    """Mise à jour partielle d'un utilisateur (tous champs facultatifs)."""

    full_name: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    """Représentation d'un utilisateur exposée par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
