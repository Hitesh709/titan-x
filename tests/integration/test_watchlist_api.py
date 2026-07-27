import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.user import User
from titan_x.models.watchlist import Watchlist, WatchlistFolder, WatchlistItem, WatchlistTag

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL") or not os.getenv("API_KEY") or not os.getenv("JWT_SECRET_KEY"),
        reason="integration: missing env vars",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]

HEADERS: dict[str, str] = {}
TOKEN: str | None = None


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    global TOKEN, HEADERS
    if TOKEN:
        return HEADERS
    api_key = os.getenv("API_KEY", "test-api-key-1234567890")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "watchlist_test@example.com", "password": "StrongPass1!"},
        headers={"X-API-Key": api_key},
    )
    data = resp.json()
    TOKEN = data.get("access_token", "")
    HEADERS = {"X-API-Key": api_key, "Authorization": f"Bearer {TOKEN}"}
    return HEADERS


class TestWatchlistAPI:
    async def test_create_folder(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.post("/api/v1/watchlists/folders", json={"name": "Tech Stocks"}, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Tech Stocks"
        assert "id" in data

    async def test_list_folders(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists/folders", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_folder(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists/folders", json={"name": "Energy"}, headers=h)
        fid = created.json()["id"]
        resp = await client.get(f"/api/v1/watchlists/folders/{fid}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Energy"

    async def test_get_folder_not_found(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists/folders/99999", headers=h)
        assert resp.status_code == 404

    async def test_update_folder(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists/folders", json={"name": "Old"}, headers=h)
        fid = created.json()["id"]
        resp = await client.put(f"/api/v1/watchlists/folders/{fid}", json={"name": "Updated"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_delete_folder(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists/folders", json={"name": "Temp"}, headers=h)
        fid = created.json()["id"]
        resp = await client.delete(f"/api/v1/watchlists/folders/{fid}", headers=h)
        assert resp.status_code == 204

    async def test_create_watchlist(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.post("/api/v1/watchlists", json={"name": "My Watchlist"}, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Watchlist"
        assert data["is_default"] is False

    async def test_create_default_watchlist(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.post("/api/v1/watchlists", json={"name": "Default", "is_default": True}, headers=h)
        assert resp.status_code == 201
        assert resp.json()["is_default"] is True

    async def test_list_watchlists(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    async def test_get_watchlist(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists", json={"name": "Test WL"}, headers=h)
        wid = created.json()["id"]
        resp = await client.get(f"/api/v1/watchlists/{wid}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test WL"

    async def test_get_watchlist_not_found(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists/99999", headers=h)
        assert resp.status_code == 404

    async def test_update_watchlist(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists", json={"name": "Old WL"}, headers=h)
        wid = created.json()["id"]
        resp = await client.put(f"/api/v1/watchlists/{wid}", json={"name": "Updated WL"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated WL"

    async def test_delete_watchlist(self, client: AsyncClient):
        h = await _auth_headers(client)
        created = await client.post("/api/v1/watchlists", json={"name": "Temp WL"}, headers=h)
        wid = created.json()["id"]
        resp = await client.delete(f"/api/v1/watchlists/{wid}", headers=h)
        assert resp.status_code == 204

    async def test_add_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Item Test"}, headers=h)
        wid = wl.json()["id"]
        resp = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        assert resp.status_code == 201
        assert resp.json()["symbol"] == "AAPL"

    async def test_add_duplicate_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Dup Test"}, headers=h)
        wid = wl.json()["id"]
        await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        resp = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        assert resp.status_code == 409

    async def test_list_items(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "List Items"}, headers=h)
        wid = wl.json()["id"]
        await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "GOOG"}, headers=h)
        resp = await client.get(f"/api/v1/watchlists/{wid}/items", headers=h)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_update_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Upd Item"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        resp = await client.put(f"/api/v1/watchlists/{wid}/items/{iid}", json={"notes": "Star pick"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Star pick"

    async def test_remove_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Rm Item"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        resp = await client.delete(f"/api/v1/watchlists/{wid}/items/{iid}", headers=h)
        assert resp.status_code == 204

    async def test_reorder_items(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Reorder"}, headers=h)
        wid = wl.json()["id"]
        i1 = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "A"}, headers=h)
        i2 = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "B"}, headers=h)
        resp = await client.put(
            f"/api/v1/watchlists/{wid}/items/reorder",
            json={"item_ids": [i2.json()["id"], i1.json()["id"]]},
            headers=h,
        )
        assert resp.status_code == 200

    async def test_create_tag(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.post("/api/v1/watchlists/tags", json={"name": "Tech", "color": "#1e90ff"}, headers=h)
        assert resp.status_code == 201
        assert resp.json()["name"] == "Tech"

    async def test_list_tags(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists/tags", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_tag_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Tag Test"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        tag = await client.post("/api/v1/watchlists/tags", json={"name": "Growth"}, headers=h)
        tid = tag.json()["id"]
        resp = await client.post(f"/api/v1/watchlists/{wid}/items/{iid}/tags/{tid}", headers=h)
        assert resp.status_code == 201

    async def test_untag_item(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Untag"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        tag = await client.post("/api/v1/watchlists/tags", json={"name": "Growth"}, headers=h)
        tid = tag.json()["id"]
        await client.post(f"/api/v1/watchlists/{wid}/items/{iid}/tags/{tid}", headers=h)
        resp = await client.delete(f"/api/v1/watchlists/{wid}/items/{iid}/tags/{tid}", headers=h)
        assert resp.status_code == 204

    async def test_delete_tag(self, client: AsyncClient):
        h = await _auth_headers(client)
        tag = await client.post("/api/v1/watchlists/tags", json={"name": "TempTag"}, headers=h)
        tid = tag.json()["id"]
        resp = await client.delete(f"/api/v1/watchlists/tags/{tid}", headers=h)
        assert resp.status_code == 204

    async def test_create_alert(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Alert Test"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        resp = await client.post(
            f"/api/v1/watchlists/{wid}/alerts",
            json={"item_id": iid, "alert_type": "price_above", "operator": "gt", "threshold_value": 200.0},
            headers=h,
        )
        assert resp.status_code == 201
        assert resp.json()["alert_type"] == "price_above"

    async def test_list_alerts(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "List Alerts"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        await client.post(
            f"/api/v1/watchlists/{wid}/alerts",
            json={"item_id": iid, "alert_type": "price_above", "operator": "gt", "threshold_value": 200.0},
            headers=h,
        )
        resp = await client.get(f"/api/v1/watchlists/{wid}/alerts", headers=h)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_update_alert(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Upd Alert"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        alert = await client.post(
            f"/api/v1/watchlists/{wid}/alerts",
            json={"item_id": iid, "alert_type": "price_above", "operator": "gt", "threshold_value": 200.0},
            headers=h,
        )
        aid = alert.json()["id"]
        resp = await client.put(
            f"/api/v1/watchlists/{wid}/alerts/{aid}",
            json={"threshold_value": 250.0},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["threshold_value"] == 250.0

    async def test_delete_alert(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Del Alert"}, headers=h)
        wid = wl.json()["id"]
        item = await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        iid = item.json()["id"]
        alert = await client.post(
            f"/api/v1/watchlists/{wid}/alerts",
            json={"item_id": iid, "alert_type": "price_above", "operator": "gt", "threshold_value": 200.0},
            headers=h,
        )
        aid = alert.json()["id"]
        resp = await client.delete(f"/api/v1/watchlists/{wid}/alerts/{aid}", headers=h)
        assert resp.status_code == 204

    async def test_notification_lifecycle(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.get("/api/v1/watchlists/notifications", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    async def test_mark_notification_read(self, client: AsyncClient):
        h = await _auth_headers(client)
        notifs = await client.get("/api/v1/watchlists/notifications", headers=h)
        items = notifs.json().get("items", [])
        if items:
            resp = await client.put(f"/api/v1/watchlists/notifications/{items[0]['id']}/read", headers=h)
            assert resp.status_code == 200

    async def test_mark_all_read(self, client: AsyncClient):
        h = await _auth_headers(client)
        resp = await client.put("/api/v1/watchlists/notifications/read-all", headers=h)
        assert resp.status_code == 200
        assert "marked_read" in resp.json()

    async def test_delete_notification(self, client: AsyncClient):
        h = await _auth_headers(client)
        notifs = await client.get("/api/v1/watchlists/notifications", headers=h)
        items = notifs.json().get("items", [])
        if items:
            resp = await client.delete(f"/api/v1/watchlists/notifications/{items[0]['id']}", headers=h)
            assert resp.status_code == 204

    async def test_ai_analyze(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "AI Test"}, headers=h)
        wid = wl.json()["id"]
        await client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "AAPL"}, headers=h)
        resp = await client.post(f"/api/v1/watchlists/{wid}/ai/analyze", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_insights(self, client: AsyncClient):
        h = await _auth_headers(client)
        wl = await client.post("/api/v1/watchlists", json={"name": "Insights"}, headers=h)
        wid = wl.json()["id"]
        resp = await client.get(f"/api/v1/watchlists/{wid}/ai/insights", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_watchlist_in_folder_create(self, client: AsyncClient):
        h = await _auth_headers(client)
        folder = await client.post("/api/v1/watchlists/folders", json={"name": "Folder1"}, headers=h)
        fid = folder.json()["id"]
        wl = await client.post(
            "/api/v1/watchlists",
            json={"name": "In Folder", "folder_id": fid},
            headers=h,
        )
        assert wl.status_code == 201
        assert wl.json()["folder_id"] == fid

    async def test_filter_by_folder(self, client: AsyncClient):
        h = await _auth_headers(client)
        f1 = await client.post("/api/v1/watchlists/folders", json={"name": "F1"}, headers=h)
        f2 = await client.post("/api/v1/watchlists/folders", json={"name": "F2"}, headers=h)
        await client.post("/api/v1/watchlists", json={"name": "WL1", "folder_id": f1.json()["id"]}, headers=h)
        await client.post("/api/v1/watchlists", json={"name": "WL2", "folder_id": f2.json()["id"]}, headers=h)
        resp = await client.get(f"/api/v1/watchlists?folder_id={f1.json()['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
