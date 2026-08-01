"""Endpoint d'authentification : inscription, connexion, jetons, mot de passe."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_auth_service, get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=201,
    summary="Créer un compte (le premier compte devient Administrateur)",
)
def register(payload: UserCreate, service: AuthServiceDep) -> TokenPair:
    """Crée un compte et le connecte (retourne access + refresh tokens)."""
    return service.register(**payload.model_dump())


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Se connecter (formulaire OAuth2 username/password)",
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthServiceDep,
) -> TokenPair:
    """Authentifie par nom d'utilisateur ou email + mot de passe."""
    user = service.authenticate(username=form.username, password=form.password)
    return service.issue_token_pair(user)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rafraîchir l'access token (rotation du refresh token)",
)
def refresh(payload: RefreshRequest, service: AuthServiceDep) -> TokenPair:
    """Échange un refresh token valide contre une nouvelle paire de jetons."""
    return service.refresh(payload.refresh_token)


@router.post(
    "/logout",
    status_code=204,
    summary="Révoquer un refresh token",
)
def logout(payload: LogoutRequest, service: AuthServiceDep) -> None:
    """Révoque le refresh token fourni (déconnexion)."""
    service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Profil de l'utilisateur connecté",
)
def me(user: CurrentUser) -> User:
    """Retourne l'utilisateur authentifié par l'access token."""
    return user


@router.post(
    "/change-password",
    status_code=204,
    summary="Changer son mot de passe",
)
def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    service: AuthServiceDep,
) -> None:
    """Change le mot de passe et révoque les autres sessions."""
    service.change_password(
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
