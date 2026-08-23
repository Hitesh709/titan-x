from fastapi.testclient import TestClient

from titan_x.main import app


def test_analytics_dashboard_api() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/analytics/dashboard",
        json={
            "equity": [100, 105, 102, 110],
            "trades": [5, -3, 8, -1],
            "benchmark_return_pct": 5.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_return_pct"] == 10.0
    assert body["trades"]["win_rate_pct"] == 50.0


def test_analytics_dashboard_rejects_non_finite_values() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/analytics/dashboard",
        json={"equity": [100, "NaN"]},
    )
    assert response.status_code == 422
