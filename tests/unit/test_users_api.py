import pytest
from httpx import AsyncClient

from titan_x.core.security import hash_password
from titan_x.db.repository import BaseRepository
from titan_x.models.user import User


@pytest.mark.asyncio
async def test_list_users_requires_admin(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    user = await user_repo.create(
        email="normal@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="normal",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "normal@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_returns_paginated(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    user = await user_repo.create(
        email="admin@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(5):
        await user_repo.create(
            email=f"user{i}@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
        )

    resp = await client.get("/api/v1/admin/users?skip=0&limit=3", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    assert len(data["items"]) == 3
    assert data["skip"] == 0
    assert data["limit"] == 3


@pytest.mark.asyncio
async def test_get_user_by_id(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="admin2@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    target = await user_repo.create(
        email="target@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin2@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.get(f"/api/v1/admin/users/{target.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "target@test.com"


@pytest.mark.asyncio
async def test_get_user_not_found(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="admin3@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin3@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.get("/api/v1/admin/users/99999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_creates_user(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="createadmin@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "createadmin@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "createdbyadmin@test.com",
            "password": "Str0ng!Pass",
            "role": "premium",
            "is_verified": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "createdbyadmin@test.com"
    assert data["role"] == "premium"
    assert data["is_verified"] is True


@pytest.mark.asyncio
async def test_admin_updates_user(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="updateadmin@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    target = await user_repo.create(
        email="updatee@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "updateadmin@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "analyst", "is_verified": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "analyst"
    assert data["is_verified"] is True
    assert data["email"] == "updatee@test.com"


@pytest.mark.asyncio
async def test_admin_deletes_user(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="deladmin@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    target = await user_repo.create(
        email="todelete@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "deladmin@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.delete(
        f"/api/v1/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "User deleted"

    check = await client.get(
        f"/api/v1/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert check.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(
    client: AsyncClient, user_repo: BaseRepository[User]
) -> None:
    admin = await user_repo.create(
        email="selfdel@test.com",
        hashed_password=hash_password("Str0ng!Pass"),
        role="admin",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "selfdel@test.com", "password": "Str0ng!Pass"},
    )
    token = login.json()["access_token"]

    resp = await client.delete(
        f"/api/v1/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
