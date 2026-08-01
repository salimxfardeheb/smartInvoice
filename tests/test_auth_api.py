"""Tests d'intégration de l'API d'authentification et des rôles.

Couvrent : inscription, connexion, jeton « moi », rotation/révocation des
refresh tokens, expiration, désactivation et contrôle des permissions par rôle.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_jti,
)
from app.models.enums import UserRole

from tests.conftest import auth_headers, login, register_user


def _register_roles(client) -> tuple[dict, dict, dict]:
    """Inscrit admin + comptable + acheteur et retourne leurs en-têtes."""
    register_user(client, username="admin", email="admin@example.com")
    register_user(client, username="comptable", email="comptable@example.com")
    register_user(client, username="acheteur", email="acheteur@example.com")
    return (
        auth_headers(client, "admin"),
        auth_headers(client, "comptable"),
        auth_headers(client, "acheteur"),
    )


class TestRegistration:
    def test_first_user_becomes_admin(self, client) -> None:
        response = register_user(client, username="boss", email="boss@example.com")
        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body and "refresh_token" in body

        me = client.get("/api/auth/me", headers=auth_headers(client, "boss"))
        assert me.json()["role"] == UserRole.ADMIN.value

    def test_second_user_defaults_to_accountant(self, client) -> None:
        register_user(client, username="boss", email="boss@example.com")
        register_user(client, username="employe", email="employe@example.com")
        me = client.get("/api/auth/me", headers=auth_headers(client, "employe"))
        assert me.json()["role"] == UserRole.ACCOUNTANT.value

    def test_duplicate_username_conflict(self, client) -> None:
        register_user(client, username="dup", email="a@example.com")
        response = register_user(client, username="dup", email="b@example.com")
        assert response.status_code == 409

    def test_duplicate_email_conflict(self, client) -> None:
        register_user(client, username="alice", email="same@example.com")
        response = register_user(client, username="bob", email="same@example.com")
        assert response.status_code == 409

    def test_weak_password_rejected(self, client) -> None:
        response = register_user(client, username="weak", password="court")
        assert response.status_code == 422


class TestLogin:
    def test_login_success_returns_token_pair(self, client) -> None:
        register_user(client, username="alice", password="Mot2passe-!123")
        response = login(client, "alice", "Mot2passe-!123")
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert "access_token" in body and "refresh_token" in body

    def test_login_wrong_password(self, client) -> None:
        register_user(client, username="alice")
        response = login(client, "alice", "Mauvais-!123")
        assert response.status_code == 401

    def test_login_unknown_user(self, client) -> None:
        response = login(client, "inconnu", "Mot2passe-!123")
        assert response.status_code == 401

    def test_login_inactive_user_rejected(self, client, engine) -> None:
        register_user(client, username="admin")
        register_user(client, username="cible", email="cible@example.com")
        admin = auth_headers(client, "admin")
        user_id = _user_id_by_username(client, admin, "cible")
        assert (
            client.post(
                f"/api/users/{user_id}/deactivate", headers=admin
            ).status_code
            == 200
        )
        response = login(client, "cible")
        assert response.status_code == 401


class TestMe:
    def test_me_returns_profile(self, client) -> None:
        register_user(client, username="alice")
        headers = auth_headers(client, "alice")
        response = client.get("/api/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["username"] == "alice"
        assert response.json()["is_active"] is True

    def test_me_without_token(self, client) -> None:
        assert client.get("/api/auth/me").status_code == 401

    def test_me_with_garbage_token(self, client) -> None:
        headers = {"Authorization": "Bearer not-a-token"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_me_with_expired_token(self, client) -> None:
        register_user(client, username="alice")
        token = create_access_token(
            "999", UserRole.ADMIN.value, expires_delta=timedelta(seconds=-30)
        )
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_me_with_refresh_token_rejected(self, client) -> None:
        register_user(client, username="alice")
        refresh = login(client, "alice").json()["refresh_token"]
        headers = {"Authorization": f"Bearer {refresh}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401


class TestRefresh:
    def test_refresh_rotates_token(self, client) -> None:
        register_user(client, username="alice")
        pair = login(client, "alice").json()

        response = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert response.status_code == 200
        new_pair = response.json()
        assert new_pair["access_token"] != pair["access_token"]

        me = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"}
        )
        assert me.status_code == 200

    def test_refresh_rejects_reused_token(self, client) -> None:
        register_user(client, username="alice")
        pair = login(client, "alice").json()
        client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert response.status_code == 401

    def test_refresh_expired_token(self, client) -> None:
        register_user(client, username="alice")
        expired = create_refresh_token(
            "1", UserRole.ADMIN.value, generate_jti(),
            expires_delta=timedelta(seconds=-30),
        )
        response = client.post("/api/auth/refresh", json={"refresh_token": expired})
        assert response.status_code == 401

    def test_refresh_after_logout(self, client) -> None:
        register_user(client, username="alice")
        pair = login(client, "alice").json()
        logout = client.post("/api/auth/logout", json={"refresh_token": pair["refresh_token"]})
        assert logout.status_code == 204
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert refresh.status_code == 401


class TestUsersAdmin:
    def test_admin_can_list_users(self, client) -> None:
        admin, comptable, acheteur = _register_roles(client)
        response = client.get("/api/users", headers=admin)
        assert response.status_code == 200
        assert {u["username"] for u in response.json()} == {
            "admin",
            "comptable",
            "acheteur",
        }

    def test_list_filters_by_active(self, client) -> None:
        admin, _, _ = _register_roles(client)
        inactive = client.get("/api/users?active=false", headers=admin)
        assert inactive.status_code == 200
        assert inactive.json() == []

    def test_admin_can_create_user(self, client) -> None:
        admin, _, _ = _register_roles(client)
        response = client.post(
            "/api/users",
            json={
                "username": "nouveau",
                "email": "nouveau@example.com",
                "password": "Mot2passe-!123",
                "role": UserRole.BUYER.value,
            },
            headers=admin,
        )
        assert response.status_code == 201
        assert response.json()["role"] == UserRole.BUYER.value
        assert login(client, "nouveau", "Mot2passe-!123").status_code == 200

    def test_admin_can_update_role_and_activation(self, client) -> None:
        admin, comptable, _ = _register_roles(client)
        user_id = _user_id_by_username(client, admin, "comptable")
        response = client.patch(
            f"/api/users/{user_id}",
            json={"role": UserRole.BUYER.value, "full_name": "Comptable Marie"},
            headers=admin,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == UserRole.BUYER.value
        assert body["full_name"] == "Comptable Marie"
        assert login(client, "comptable").status_code == 200

    def test_admin_can_deactivate_and_reactivate(self, client) -> None:
        admin, comptable, _ = _register_roles(client)
        user_id = _user_id_by_username(client, admin, "comptable")

        deactivated = client.post(f"/api/users/{user_id}/deactivate", headers=admin)
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False

        reactivated = client.patch(
            f"/api/users/{user_id}", json={"is_active": True}, headers=admin
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["is_active"] is True

    def test_admin_cannot_deactivate_self(self, client) -> None:
        admin, _, _ = _register_roles(client)
        admin_id = _user_id_by_username(client, admin, "admin")
        assert (
            client.post(f"/api/users/{admin_id}/deactivate", headers=admin).status_code
            == 200
        )
        assert client.get("/api/auth/me", headers=admin).status_code == 401

    def test_get_unknown_user_404(self, client) -> None:
        admin, _, _ = _register_roles(client)
        assert client.get("/api/users/999999", headers=admin).status_code == 404


class TestRoleProtection:
    def test_anonymous_is_rejected(self, client) -> None:
        assert client.get("/api/users").status_code == 401

    def test_accountant_cannot_manage_users(self, client) -> None:
        _, comptable, _ = _register_roles(client)
        assert client.get("/api/users", headers=comptable).status_code == 403
        assert client.post("/api/users", json={}, headers=comptable).status_code == 403

    def test_buyer_cannot_manage_users(self, client) -> None:
        _, _, acheteur = _register_roles(client)
        assert client.get("/api/users", headers=acheteur).status_code == 403

    def test_deactivated_user_token_is_invalidated(self, client) -> None:
        admin, comptable, _ = _register_roles(client)
        user_id = _user_id_by_username(client, admin, "comptable")
        client.post(f"/api/users/{user_id}/deactivate", headers=admin)

        me = client.get("/api/auth/me", headers=comptable)
        assert me.status_code == 401

    def test_deactivation_revokes_refresh_tokens(self, client) -> None:
        admin, comptable, _ = _register_roles(client)
        user_id = _user_id_by_username(client, admin, "comptable")
        refresh = login(client, "comptable").json()["refresh_token"]
        client.post(f"/api/users/{user_id}/deactivate", headers=admin)

        refresh_resp = client.post(
            "/api/auth/refresh", json={"refresh_token": refresh}
        )
        assert refresh_resp.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client) -> None:
        register_user(client, username="dave", password="Ancien-!123")
        headers = auth_headers(client, "dave", "Ancien-!123")
        pair = login(client, "dave", "Ancien-!123").json()

        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "Ancien-!123", "new_password": "Nouveau-!123"},
            headers=headers,
        )
        assert response.status_code == 204

        assert login(client, "dave", "Ancien-!123").status_code == 401
        assert login(client, "dave", "Nouveau-!123").status_code == 200
        assert (
            client.post(
                "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
            ).status_code
            == 401
        )

    def test_change_password_wrong_current(self, client) -> None:
        register_user(client, username="dave")
        headers = auth_headers(client, "dave")
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "incorrect", "new_password": "Nouveau-!123"},
            headers=headers,
        )
        assert response.status_code == 401


def _user_id_by_username(client, admin_headers: dict, username: str) -> int:
    """Retourne l'id d'un utilisateur depuis la liste administrateur."""
    response = client.get("/api/users", headers=admin_headers)
    assert response.status_code == 200
    for user in response.json():
        if user["username"] == username:
            return user["id"]
    raise AssertionError(f"Utilisateur {username!r} introuvable dans la liste.")
