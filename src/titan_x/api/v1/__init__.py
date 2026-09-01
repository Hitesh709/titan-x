"""API v1 router registry.

Core routers are registered explicitly for deterministic startup. Every other
API module/package is discovered automatically so a newly-created endpoint
cannot silently become a 404 simply because it was omitted from a registry.
Import failures are recorded and exposed through startup logging rather than
preventing unrelated API routes from starting.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Iterable

from fastapi import APIRouter

logger = logging.getLogger(__name__)

_ROUTER_SPECS: tuple[tuple[str, str | None], ...] = (
    ("auth", "auth_router"),
    ("health", "health_router"),
    ("users", "users_router"),
    ("companies", "companies_router"),
    ("market_data", "router"),
    ("indices", "router"),
    ("prices", None),
    ("dashboard", "router"),
    ("top_picks", "router"),
    ("recommendation", "router"),
    ("intraday_recommendation", "router"),
    ("intraday", "intraday_router"),
    ("prediction", "prediction_router"),
    ("fundamentals", "fund_router"),
    ("financial_statements", "fin_stmt_router"),
    ("fundamental_scanner", "router"),
    ("technical_indicators", "tech_ind_router"),
    ("technical_strength", "router"),
    ("sectors", "sector_router"),
    ("market_breadth", "market_breadth_router"),
    ("pattern_recognition", "pattern_router"),
    ("risk", "risk_router"),
    ("portfolio", "portfolio_router"),
    ("watchlists", "router"),
    ("news", "news_router"),
    ("news_nlp", "news_nlp_router"),
    ("macro", "router"),
    ("global_market", "router"),
    ("valuation", "router"),
    ("strategy", "strategy_router"),
    ("backtest", "backtest_router"),
    ("learning", "learning_router"),
    ("knowledge_graph", "kg_router"),
    ("decision", "decision_router"),
    ("master_decision", "router"),
    ("ensemble_ai", "ensemble_router"),
    ("explainability", "explainability_router"),
    ("ai_ranking_v2", "router"),
    ("advanced_screener", "router"),
    ("market_scanner", "router"),
    ("market_heatmap", "router"),
    ("sector_rotation", "router"),
    ("regime_detection", "router"),
    ("correlation", "router"),
    ("institutional_analysis", "inst_router"),
    ("corporate_actions_engine", "ca_engine_router"),
    ("corporate_action_detection", "cad_router"),
    ("event_intelligence", "router"),
    ("price_target", "router"),
    ("professional_report", "router"),
    ("reports", "router"),
    ("search", "router"),
    ("export", "router"),
    ("data_io", "router"),
    ("data_validation", "router"),
    ("datalake", "router"),
    ("feature_engineering", "router"),
    ("feature_store", "router"),
    ("model_registry", "router"),
    ("model_evaluation", "router"),
    ("drift_detection", "router"),
    ("monitoring", "router"),
    ("scheduler", "scheduler_router"),
    ("trading_calendar", "router"),
    ("paper_trading", "router"),
    ("trade_journal", "router"),
    ("trading_portfolio", "router"),
    ("order", "router"),
    ("broker", "router"),
    ("preferences", "router"),
    ("mfa", "router"),
    ("qr_auth", "router"),
    ("admin", "admin_router"),
    ("audit", "router"),
    ("version", "version_router"),
    ("public_market", "router"),
)


def _routers(module: object) -> Iterable[APIRouter]:
    for _, value in inspect.getmembers(module):
        if isinstance(value, APIRouter):
            yield value


def _resolve(module_name: str, router_name: str | None) -> list[APIRouter]:
    module = importlib.import_module(f"{__package__}.{module_name}")
    if router_name is not None:
        router = getattr(module, router_name, None)
        return [router] if isinstance(router, APIRouter) else []
    return list(_routers(module))


def _discover_specs() -> list[tuple[str, str | None]]:
    """Discover API modules/packages not present in the explicit registry."""
    discovered: list[tuple[str, str | None]] = []
    explicit = {name for name, _ in _ROUTER_SPECS}
    package = importlib.import_module(__package__)

    for item in pkgutil.iter_modules(package.__path__):
        name = item.name
        if name.startswith("_") or name in explicit:
            continue
        # Use automatic APIRouter inspection rather than assuming the exported
        # variable is named ``router``. This catches modules such as
        # adaptive_stop_loss and analytics_dashboard safely.
        discovered.append((name, None))

    for item in pkgutil.iter_modules(package.__path__):
        if not item.ispkg or item.name.startswith("_"):
            continue
        try:
            subpackage = importlib.import_module(f"{__package__}.{item.name}")
        except Exception:
            continue
        subpath = getattr(subpackage, "__path__", None)
        if subpath is None:
            continue
        for child in pkgutil.iter_modules(subpath):
            if child.name == "router":
                discovered.append((f"{item.name}.router", None))

    return discovered


def _build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    seen: set[int] = set()
    failures: list[str] = []
    registered_modules: set[str] = set()

    specs = list(_ROUTER_SPECS)
    specs.extend(_discover_specs())

    for module_name, router_name in specs:
        if module_name in registered_modules:
            continue
        registered_modules.add(module_name)
        try:
            resolved = _resolve(module_name, router_name)
            if not resolved:
                failures.append(f"{module_name}: router '{router_name}' not found")
                continue
            for child in resolved:
                marker = id(child)
                if marker not in seen:
                    router.include_router(child)
                    seen.add(marker)
        except Exception as exc:
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")

    if failures:
        logger.error(
            "API v1 router registration failures: %d; %s",
            len(failures),
            " | ".join(failures),
        )
    logger.info(
        "API v1 router audit: registered=%d modules=%d failures=%d discovered=%d",
        len(seen),
        len(registered_modules),
        len(failures),
        max(0, len(specs) - len(_ROUTER_SPECS)),
    )
    return router


v1_router = _build_router()

__all__ = ["v1_router"]
