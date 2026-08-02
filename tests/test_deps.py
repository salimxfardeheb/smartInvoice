"""Tests unitaires des dépendances FastAPI (phase 2 - auth).

Couvre les chemins d'erreur de :func:`get_current_user` (mauvais type de
jeton, sujet manquant/illisible, utilisateur introuvable ou désactivé), la
règle de rôle :func:`require_roles`, le rollback de :func:`get_db` et les
fabriques de services.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.exceptions import HTTPException

from app.core.exceptions import (
    InvalidTokenError,
    PermissionDeniedError,
    UserInactiveError,
)
from app.api.deps import get_db
from app.core.security import (
    TOKEN_TYPE_ACCESS,
    create_access_token,
    create_refresh_token,
)
from app.models.enums import UserRole
from tests.conftest import make_supplier


def _make_user(session, *, username: str = "user", role: UserRole = UserRole.ACCOUNTANT):
    """Crée un utilisateur actif via le repository (sans hash coûteux)."""
    from app.models.user import User
    from app.repositories import UserRepository

    return UserRepository(session).create(
        username=username,
        email=f"{username}@example.com",
        hashed_password="hash",
        role=role,
    )


class TestGetCurrentUser:
    def _resolve(self, session, token: str):
        from app.api.deps import get_current_user

        return get_current_user(db=session, token=token)

    def test_valid_access_token_returns_user(self, session) -> None:
        user = _make_user(session, username="actif")
        token = create_access_token(user.id, user.role.value)

        resolved = self._resolve(session, token)

        assert resolved.id == user.id
        assert resolved.username == "actif"

    def test_refresh_token_rejected(self, session) -> None:
        token = create_refresh_token(1, UserRole.ACCOUNTANT.value, "jti-test")

        with pytest.raises(InvalidTokenError, match="accès"):
            self._resolve(session, token)

    def test_token_without_subject_rejected(self, session) -> None:
        from app.core.security import TOKEN_TYPE_ACCESS, decode_token

        token = create_access_token(1, UserRole.ACCOUNTANT.value)
        # Ré-émet un jeton sans « sub ».
        payload = decode_token(token)
        del payload["sub"]

        import jwt as jwtlib

        from app.core.config import get_settings

        forged = jwtlib.encode(
            payload, get_settings().jwt_secret_key, algorithm="HS256"
        )
        with pytest.raises(InvalidTokenError, match="sujet"):
            self._resolve(session, forged)

    def test_non_integer_subject_rejected(self, session) -> None:
        import jwt as jwtlib

        from app.core.config import get_settings
        from app.core.security import generate_jti

        payload = {
            "sub": "pas-un-entier",
            "type": TOKEN_TYPE_ACCESS,
            "role": UserRole.ACCOUNTANT.value,
            "jti": generate_jti(),
            "exp": 9999999999,
        }
        token = jwtlib.encode(
            payload, get_settings().jwt_secret_key, algorithm="HS256"
        )

        with pytest.raises(InvalidTokenError, match="illisible"):
            self._resolve(session, token)

    def test_unknown_user_rejected(self, session) -> None:
        token = create_access_token(999999, UserRole.ACCOUNTANT.value)

        with pytest.raises(InvalidTokenError, match="introuvable"):
            self._resolve(session, token)

    def test_inactive_user_rejected(self, session) -> None:
        user = _make_user(session, username="inactif")
        from app.repositories import UserRepository

        UserRepository(session).update(user, is_active=False)
        token = create_access_token(user.id, user.role.value)

        with pytest.raises(UserInactiveError):
            self._resolve(session, token)


class TestRequireRoles:
    def _deps(self, session, *roles):
        from app.api.deps import require_roles

        return require_roles(*roles)(user=session)

    def _user_of(self, role: UserRole):
        from types import SimpleNamespace

        return SimpleNamespace(role=role)

    def test_grants_matching_role(self) -> None:
        from app.api.deps import require_roles

        dependency = require_roles(UserRole.ACCOUNTANT, UserRole.ADMIN)
        user = dependency(user=self._user_of(UserRole.ACCOUNTANT))
        assert user.role is UserRole.ACCOUNTANT

    def test_rejects_other_role(self) -> None:
        from app.api.deps import require_roles

        dependency = require_roles(UserRole.ADMIN)
        with pytest.raises(PermissionDeniedError, match="Rôle requis"):
            dependency(user=self._user_of(UserRole.BUYER))


class TestGetDb:
    def test_commits_on_success(self) -> None:
        from sqlalchemy.orm import sessionmaker

        from app.api.deps import get_db
        from tests.conftest import make_supplier

        import app.models  # noqa: F401

        from app.db.base import Base
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)

        # Remplace SessionLocal (référence de app.api.deps) par notre moteur.
        session_factory = sessionmaker(bind=engine)
        import app.api.deps as deps_module

        original = deps_module.SessionLocal
        deps_module.SessionLocal = session_factory
        try:
            generator = get_db()
            db = next(generator)
            supplier = make_supplier(db, odoo_id=77, name="Commit SAS")
            supplier_id = supplier.id
            # FastAPI fait avancer le générateur après la réponse : le
            # « commit » post-yield s'exécute alors.
            try:
                next(generator)
            except StopIteration:
                pass
        finally:
            deps_module.SessionLocal = original

        # L'entité a bien été commitée : lisible depuis une nouvelle session.
        from app.repositories import SupplierRepository

        with session_factory() as check:
            assert SupplierRepository(check).get(supplier_id) is not None

    def test_rollback_on_exception(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        import app.models  # noqa: F401

        from app.db.base import Base
        from tests.conftest import make_supplier

        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)

        session_factory = sessionmaker(bind=engine)
        import app.api.deps as deps_module

        original = deps_module.SessionLocal
        deps_module.SessionLocal = session_factory
        try:
            generator = get_db()
            db = next(generator)
            make_supplier(db, odoo_id=78, name="Rollback SAS")
            # L'exception remonte dans le générateur : rollback + re-raise.
            with pytest.raises(RuntimeError):
                generator.throw(RuntimeError("boom"))
        finally:
            deps_module.SessionLocal = original

        from app.repositories import SupplierRepository

        with session_factory() as check:
            assert SupplierRepository(check).count() == 0


class TestServiceFactories:
    def test_get_validation_service_builds_service(self, session) -> None:
        from app.api.deps import get_validation_service
        from app.services.validation_service import ValidationService

        service = get_validation_service(db=session)
        assert isinstance(service, ValidationService)
        assert service.db is session

    def test_get_ocr_engine_dep_returns_engine(self) -> None:
        from app.api.deps import get_ocr_engine_dep
        from app.ocr.base import OcrEngine

        assert isinstance(get_ocr_engine_dep(), OcrEngine)

    def test_get_audit_and_anomaly_repositories(self, session) -> None:
        from app.api.deps import (
            get_anomaly_repository,
            get_audit_log_repository,
        )
        from app.repositories import AnomalyRepository, AuditLogRepository

        assert isinstance(get_audit_log_repository(db=session), AuditLogRepository)
        assert isinstance(get_anomaly_repository(db=session), AnomalyRepository)
