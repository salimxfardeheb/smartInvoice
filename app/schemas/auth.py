"""Schémas d'authentification (jetons, connexion, changement de mot de passe)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenPair(BaseModel):
    """Paire de jetons (access + refresh) retournée à l'authentification."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Demande de rafraîchissement d'un access token."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Révoque un refresh token (déconnexion)."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Changement de mot de passe de l'utilisateur connecté."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
