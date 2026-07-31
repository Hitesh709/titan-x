import pytest
from httpx import AsyncClient

from titan_x.core.security import hash_password
from titan_x.db.repository import BaseRepository
from titan_x.models.user import User


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "Str0ng!Pass"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "Another1!"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_tokens(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "Str0ng!Pass"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_current_user(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "me@example.com", "password": "Str0ng!Pass"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "Str0ng!Pass"},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient, user_repo: BaseRepository[User]) -> None:
    user = await user_repo.create(
        email="logout@example.com",
        hashed_password=hash_password("Str0ng!Pass"),
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "Str0ng!Pass"},
    )
    data = login_resp.json()
    access = data["access_token"]
    refresh = data["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "Str0ng!Pass"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "Str0ng!Pass"},
    )
    data = login_resp.json()
    old_access = data["access_token"]
    refresh = data["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 200
    new = resp.json()
    assert "access_token" in new
    assert "refresh_token" in new
    assert new["access_token"] != old_access
    assert new["refresh_token"] != refresh


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-valid-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_after_logout_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshout@example.com", "password": "Str0ng!Pass"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshout@example.com", "password": "Str0ng!Pass"},
    )
    data = login_resp.json()
    refresh = data["refresh_token"]

    await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
    )

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_returns_reset_url(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "forgot@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"]
    assert data["reset_url"] is not None
    assert "token=" in data["reset_url"]


@pytest.mark.asyncio
async def test_reset_password_flow(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "resetme@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "resetme@example.com"},
    )
    reset_url = resp.json()["reset_url"]
    token = reset_url.split("token=")[1]

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewPass!9"},
    )
    assert resp.status_code == 200

    login_old = await client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "Str0ng!Pass"},
    )
    assert login_old.status_code == 401

    login_new = await client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "NewPass!9"},
    )
    assert login_new.status_code == 200


@pytest.mark.asyncio
async def test_send_verification_returns_url(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "verify@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/send-verification",
        json={"email": "verify@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_url"] is not None
    assert "token=" in data["verification_url"]


@pytest.mark.asyncio
async def test_verify_email_flow(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "verifyflow@example.com", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/send-verification",
        json={"email": "verifyflow@example.com"},
    )
    verify_url = resp.json()["verification_url"]
    token = verify_url.split("token=")[1]

    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Email verified successfully"

    me_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "verifyflow@example.com", "password": "Str0ng!Pass"},
    )
    token = me_resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.json()["is_verified"] is True
