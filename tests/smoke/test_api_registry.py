"""Smoke tests for API registration and route integrity."""
from __future__ import annotations

from collections import defaultdict


def _route_key(route) -> tuple[str, str]:
    return (getattr(route, "path", ""), ",".join(sorted(getattr(route, "methods", set()))))


def test_api_routes_are_unique(app):
    """No duplicate method/path combinations should reach production."""
    routes = [r for r in app.routes if getattr(r, "methods", None)]
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for route in routes:
        seen[_route_key(route)] += 1
    duplicates = {key: count for key, count in seen.items() if count > 1}
    assert not duplicates, f"Duplicate API routes detected: {duplicates}"


def test_critical_api_routes_are_mounted(app):
    """Core production APIs must never silently become 404s."""
    routes = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    required = {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/indices"),
        ("GET", "/api/v1/market-data/quotes"),
        ("POST", "/api/v1/recommendations/scan"),
    }
    missing = sorted(required - routes)
    assert not missing, f"Critical API routes are not mounted: {missing}"


def test_v1_registry_contains_routes(app):
    """The v1 router must expose a non-trivial production route surface."""
    v1_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/")
        and getattr(route, "methods", None)
    ]
    assert len(v1_routes) >= 20, (
        "Unexpectedly small API surface; router discovery/registration may have failed "
        f"({len(v1_routes)} routes found)."
    )
