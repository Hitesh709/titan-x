import pytest
from httpx import AsyncClient

from titan_x.core.rbac import Role, role_ge
from titan_x.core.security import hash_password
from titan_x.db.repository import BaseRepository
from titan_x.models.user import User


class TestRoleHierarchy:
    def test_normal_is_below_premium(self) -> None:
        assert not role_ge(Role.NORMAL, Role.PREMIUM)

    def test_premium_meets_premium(self) -> None:
        assert role_ge(Role.PREMIUM, Role.PREMIUM)

    def test_analyst_meets_normal(self) -> None:
        assert role_ge(Role.ANALYST, Role.NORMAL)

    def test_admin_meets_all(self) -> None:
        assert role_ge(Role.ADMIN, Role.NORMAL)
        assert role_ge(Role.ADMIN, Role.PREMIUM)
        assert role_ge(Role.ADMIN, Role.ANALYST)
        assert role_ge(Role.ADMIN, Role.ADMIN)

    def test_admin_exact_fails_for_analyst(self) -> None:
        assert not role_ge(Role.ANALYST, Role.ADMIN)


class TestRegistrationIncludesRole:
    @pytest.mark.asyncio
    async def test_register_defaults_to_normal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "role@test.com", "password": "Str0ng!Pass"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "normal"

    @pytest.mark.asyncio
    async def test_me_returns_role(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={"email": "merole@test.com", "password": "Str0ng!Pass"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "merole@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.json()["role"] == "normal"


class TestRoleProtectedEndpoints:
    @pytest.mark.asyncio
    async def test_premium_content_denied_for_normal(
        self, client: AsyncClient, user_repo: BaseRepository[User]
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
            "/api/v1/admin/premium/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_premium_content_allowed_for_premium(
        self, client: AsyncClient, user_repo: BaseRepository[User]
    ) -> None:
        user = await user_repo.create(
            email="prem@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
            role="premium",
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "prem@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/v1/admin/premium/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "Premium content" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_analytics_allowed_for_analyst(
        self, client: AsyncClient, user_repo: BaseRepository[User]
    ) -> None:
        user = await user_repo.create(
            email="analyst@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
            role="analyst",
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_analytics_denied_for_premium(
        self, client: AsyncClient, user_repo: BaseRepository[User]
    ) -> None:
        user = await user_repo.create(
            email="prem2@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
            role="premium",
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "prem2@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_dashboard_allowed_for_admin(
        self, client: AsyncClient, user_repo: BaseRepository[User]
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
        resp = await client.get(
            "/api/v1/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_dashboard_denied_for_analyst(
        self, client: AsyncClient, user_repo: BaseRepository[User]
    ) -> None:
        user = await user_repo.create(
            email="analyst2@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
            role="analyst",
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "analyst2@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/v1/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_access_all_endpoints(
        self, client: AsyncClient, user_repo: BaseRepository[User]
    ) -> None:
        user = await user_repo.create(
            email="superadmin@test.com",
            hashed_password=hash_password("Str0ng!Pass"),
            role="admin",
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "superadmin@test.com", "password": "Str0ng!Pass"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for path in ["/api/v1/admin/dashboard", "/api/v1/admin/analytics", "/api/v1/admin/premium/content"]:
            resp = await client.get(path, headers=headers)
            assert resp.status_code == 200, f"Admin denied on {path}"
