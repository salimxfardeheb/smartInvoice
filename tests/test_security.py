"""Tests unitaires : hash des mots de passe, jetons JWT et matrice des rôles."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.exceptions import ExpiredTokenError, InvalidTokenError
from app.core.permissions import Permission, permissions_for
from app.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_jti,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import UserRole


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password("s3cr3t-Password")
        assert hashed != "s3cr3t-Password"
        assert verify_password("s3cr3t-Password", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("bon-mot-de-passe")
        assert verify_password("mauvais-mot-de-passe", hashed) is False

    def test_hash_is_salted(self) -> None:
        assert hash_password("même-password") != hash_password("même-password")


class TestJwtTokens:
    def test_access_token_roundtrip(self) -> None:
        token = create_access_token(42, UserRole.ADMIN.value)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == UserRole.ADMIN.value
        assert payload["type"] == TOKEN_TYPE_ACCESS
        assert "exp" in payload and "jti" in payload

    def test_refresh_token_roundtrip_with_jti(self) -> None:
        jti = generate_jti()
        token = create_refresh_token(42, UserRole.ADMIN.value, jti)
        payload = decode_token(token)
        assert payload["type"] == TOKEN_TYPE_REFRESH
        assert payload["jti"] == jti

    def test_tokens_are_distinct(self) -> None:
        access = create_access_token(1, UserRole.ADMIN.value)
        refresh = create_refresh_token(1, UserRole.ADMIN.value, generate_jti())
        assert access != refresh

    def test_decode_expired_token_raises(self) -> None:
        token = create_access_token(
            1, UserRole.ADMIN.value, expires_delta=timedelta(seconds=-10)
        )
        with pytest.raises(ExpiredTokenError):
            decode_token(token)

    def test_decode_invalid_token_raises(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_token("pas.un.jeton")

    def test_decode_tampered_token_raises(self) -> None:
        token = create_access_token(1, UserRole.ADMIN.value)
        tampered = token[:-2] + ("XX" if token[-2:] != "XX" else "YY")
        with pytest.raises(InvalidTokenError):
            decode_token(tampered)

    def test_token_hash_is_deterministic(self) -> None:
        assert hash_token("abc") == hash_token("abc")
        assert hash_token("abc") != hash_token("abd")


class TestRolePermissions:
    def test_admin_has_all_permissions(self) -> None:
        assert permissions_for(UserRole.ADMIN) == frozenset(Permission)

    def test_accountant_can_manage_invoices(self) -> None:
        granted = permissions_for(UserRole.ACCOUNTANT)
        assert Permission.INVOICE_DEPOSIT in granted
        assert Permission.INVOICE_VALIDATE in granted
        assert Permission.INVOICE_CORRECT in granted
        assert Permission.INVOICE_CONFIRM not in granted
        assert Permission.USER_WRITE not in granted

    def test_buyer_can_confirm_but_not_validate(self) -> None:
        granted = permissions_for(UserRole.BUYER)
        assert Permission.INVOICE_CONFIRM in granted
        assert Permission.INVOICE_VALIDATE not in granted
        assert Permission.INVOICE_DEPOSIT not in granted
        assert Permission.USER_READ not in granted

    def test_jwt_role_claim_matches_registry(self) -> None:
        token = create_access_token(1, UserRole.BUYER.value)
        assert decode_token(token)["role"] == UserRole.BUYER.value
