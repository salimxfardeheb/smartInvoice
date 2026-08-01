"""Endpoint de gestion des utilisateurs (réservé à l'Administrateur)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_auth_service, get_db, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.repositories import UserRepository
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserReadPerm = Annotated[User, Depends(require_permissions(Permission.USER_READ))]
UserWritePerm = Annotated[User, Depends(require_permissions(Permission.USER_WRITE))]
UserDeactivatePerm = Annotated[
    User, Depends(require_permissions(Permission.USER_DEACTIVATE))
]


def _get_user_or_404(service: AuthService, user_id: int) -> User:
    user = service.users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return user


@router.get(
    "",
    response_model=list[UserRead],
    summary="Lister les utilisateurs",
)
def list_users(
    active: bool | None = Query(default=None, description="Filtrer par état"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    _: UserReadPerm = None,
) -> list[User]:
    """Liste paginée des utilisateurs (filtre optionnel par état)."""
    return UserRepository(db).filter(active=active, limit=limit, offset=offset)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Consulter un utilisateur",
)
def get_user(
    user_id: int,
    service: AuthServiceDep,
    _: UserReadPerm = None,
) -> User:
    """Retourne le détail d'un utilisateur."""
    return _get_user_or_404(service, user_id)


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    summary="Créer un utilisateur",
)
def create_user(
    payload: UserCreate,
    service: AuthServiceDep,
    _: UserWritePerm = None,
) -> User:
    """Crée un utilisateur (mot de passe hashé côté service)."""
    return service.create_user(**payload.model_dump())


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Mettre à jour un utilisateur",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    service: AuthServiceDep,
    _: UserWritePerm = None,
) -> User:
    """Met à jour les champs fournis (email, rôle, nom, activation)."""
    user = _get_user_or_404(service, user_id)
    return service.update_user(user, **payload.model_dump(exclude_unset=True))


@router.post(
    "/{user_id}/deactivate",
    response_model=UserRead,
    summary="Désactiver un compte",
)
def deactivate_user(
    user_id: int,
    service: AuthServiceDep,
    _: UserDeactivatePerm = None,
) -> User:
    """Désactive le compte et révoque ses jetons de rafraîchissement."""
    user = _get_user_or_404(service, user_id)
    return service.deactivate_user(user)
