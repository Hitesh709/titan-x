"""API v1 router registry.

The project contains legacy API modules that do not all expose their router
under the same variable name (some use ``router``, others use names such as
``fund_router`` or ``inst_router``).  Importing those symbols statically made
Render fail at startup on the first mismatch.  This registry resolves routers
from the modules themselves and validates them before registration, so a
router variable rename cannot take the entire application down.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import Iterable

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# (module, preferred router attribute).  The preferred attribute is used when
# present.  If an older module has a different name, the fallback discovers
# module-level APIRouter objects automatically.
_ROUTER_SPECS: tuple[tuple[str, str | None], ...] = (
    ("analytics_dashboard", "router"),
    ("adaptive_stop_loss", "router"),
    ("admin", "admin_router"),
    ("advanced_screener", "router"),
    ("ai_ranking_v2", "router"),
    ("ai_registry", "router"),
    ("audit", "router"),
    ("auth", "auth_router"),
    ("automated_training", "router"),
    ("backtest", "backtest_router"),
    ("broker", "router"),
    ("companies", "companies_router"),
    ("company_research", "router"),
    ("corporate_action_detection", "cad_router"),
    ("corporate_actions_engine", "ca_engine_router"),
    ("corporate_reminders", "router"),
    ("corporate_tracking", "corp_track_router"),
    ("correlation", "router"),
    ("dashboard", "router"),
    ("data_io", "router"),
    ("data_validation", "router"),
    ("datalake", "router"),
    ("decision", "decision_router"),
    ("drift_detection", "router"),
    ("dynamic_ai_score", "router"),
    ("ensemble_ai", "ensemble_router"),
    ("event_intelligence", "router"),
    ("experiment_manager", "router"),
    ("explainability", "explainability_router"),
    ("export", "router"),
    ("feature_engineering", "router"),
    ("feature_store", "router"),
    ("financial_analysis", "router"),
    ("financial_statements", "fin_stmt_router"),
    ("fundamental_scanner", "router"),
    ("fundamentals", "fund_router"),
    ("global_market", "router"),
    ("health", "health_router"),
    ("historical_similarity", "hist_sim_router"),
    ("indices", "router"),
    ("institutional_analysis", "inst_router"),
    ("intraday", "intraday_router"),
    ("intraday_recommendation", "router"),
    ("knowledge_graph", "kg_router"),
    ("learning", "learning_router"),
    ("live_market_websocket", "router"),
    ("macro", "router"),
    ("market_breadth", "market_breadth_router"),
    ("market_data", "router"),
    ("market_data_collector", "mdc_router"),
    ("market_heatmap", "router"),
    ("market_scanner", "router"),
    ("master_decision", "router"),
    ("microstructure", "router"),
    ("model_evaluation", "router"),
    ("model_registry", "router"),
    ("monitoring", "router"),
    ("news", "news_router"),
    ("news_nlp", "news_nlp_router"),
    ("news_scanner", "router"),
    ("nightly_evaluation", "router"),
    ("opportunity_rejection", "router"),
    ("order", "order_router"),
    ("paper_trading", "paper_trading_router"),
    ("pattern_library", "router"),
    ("pattern_recognition", "pattern_router"),
    ("pattern_search", "router"),
    ("performance_measurement", "router"),
    ("portfolio", "portfolio_router"),
    ("portfolio_optimizer", "router"),
    ("prediction", "router"),
    ("preferences", "router"),
    ("price_target", "router"),
    ("prices", None),  # contains both prices_router and corp_actions_router
    ("professional_report", "router"),
    ("ranking", "router"),
    ("recommendation", "recommendation_router"),
    ("research", "research_router"),
    ("regime_detection", "router"),
    ("reports", "reports_router"),
    ("risk", "risk_router"),
    ("scheduler", "scheduler_router"),
    ("search", "router"),
    ("sector_rotation", "router"),
    ("sectors", "sector_router"),
    ("strategy", "strategy_router"),
    ("technical_indicators", "tech_ind_router"),
    ("timescaledb", "router"),
    ("top_picks", "router"),
    ("trade_journal", "trade_journal_router"),
    ("trading_calendar", "trading_calendar_router"),
    ("trading_portfolio", "trading_portfolio_router"),
    ("users", "users_router"),
    ("valuation", "router"),
    ("version", "version_router"),
    ("watchlists", "watchlist_router"),
)


def _router_candidates(module: object) -> list[APIRouter]:
    """Return unique module-level FastAPI routers."""
    candidates: list[APIRouter] = []
    for _, value in inspect.getmembers(module):
        if isinstance(value, APIRouter) and all(value is not item for item in candidates):
            candidates.append(value)
    return candidates


def _resolve_module_routers(module_name: str, preferred: str | None) -> list[APIRouter]:
    module = importlib.import_module(f"{__package__}.{module_name}")

    if preferred:
        selected = getattr(module, preferred, None)
        if isinstance(selected, APIRouter):
            return [selected]

    # Fallback handles renamed router variables and multi-router modules.
    candidates = _router_candidates(module)
    if preferred:
        logger.warning(
            "Router attribute %s.%s was not found; discovered %d APIRouter object(s)",
            module_name,
            preferred,
            len(candidates),
        )
    return candidates


def _build_router() -> APIRouter:
    api_router = APIRouter(prefix="/api/v1")
    seen: set[int] = set()
    failures: list[str] = []

    for module_name, preferred in _ROUTER_SPECS:
        try:
            routers = _resolve_module_routers(module_name, preferred)
            if not routers:
                failures.append(f"{module_name}: no APIRouter found")
                continue
            for router in routers:
                marker = id(router)
                if marker not in seen:
                    api_router.include_router(router)
                    seen.add(marker)
        except Exception as exc:  # keep startup diagnostics explicit
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")

    if failures:
        # Do not silently hide broken modules.  Startup continues so Render can
        # expose the actual application, while the diagnostics remain visible.
        logger.error("API v1 router registration warnings: %s", " | ".join(failures))

    return api_router


v1_router = _build_router()

__all__ = ["v1_router"]
