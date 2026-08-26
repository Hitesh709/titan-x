"""API v1 router registry."""

from __future__ import annotations

import importlib
import inspect
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

_ROUTER_SPECS: tuple[tuple[str, str | None], ...] = (
    ("analytics_dashboard", "router"), ("adaptive_stop_loss", "router"), ("admin", "admin_router"),
    ("advanced_screener", "router"), ("ai_ranking_v2", "router"), ("ai_registry", "router"),
    ("audit", "router"), ("auth", "auth_router"), ("automated_training", "router"),
    ("backtest", "backtest_router"), ("broker", "router"), ("companies", "companies_router"),
    ("company_research", "router"), ("corporate_action_detection", "cad_router"),
    ("corporate_actions_engine", "ca_engine_router"), ("corporate_reminders", "router"),
    ("corporate_tracking", "corp_track_router"), ("correlation", "router"), ("dashboard", "router"),
    ("data_io", "router"), ("data_validation", "router"), ("datalake", "router"),
    ("decision", "decision_router"), ("drift_detection", "router"), ("dynamic_ai_score", "router"),
    ("ensemble_ai", "ensemble_router"), ("event_intelligence", "router"), ("experiment_manager", "router"),
    ("explainability", "explainability_router"), ("export", "router"), ("feature_engineering", "router"),
    ("feature_store", "router"), ("financial_analysis", "router"), ("financial_statements", "fin_stmt_router"),
    ("fundamental_scanner", "router"), ("fundamentals", "fund_router"), ("global_market", "router"),
    ("health", "health_router"), ("historical_similarity", "hist_sim_router"), ("indices", "router"),
    ("institutional_analysis", "inst_router"), ("intraday", "intraday_router"),
    ("intraday_recommendation", "router"), ("knowledge_graph", "kg_router"), ("learning", "learning_router"),
    ("live_market_websocket", "router"), ("macro", "router"), ("market_breadth", "market_breadth_router"),
    ("market_data", "router"), ("market_data_collector", "router"), ("market_heatmap", "router"),
    ("market_scanner", "router"), ("master_decision", "router"), ("microstructure", "router"),
    ("model_evaluation", "router"), ("model_registry", "router"), ("monitoring", "router"),
    ("news", "news_router"), ("news_nlp", "news_nlp_router"), ("news_scanner", "router"),
    ("nightly_evaluation", "router"), ("opportunity_rejection", "router"), ("order", "router"),
    ("paper_trading", "router"), ("pattern_library", "router"), ("pattern_recognition", "pattern_router"),
    ("pattern_search", "router"), ("performance_measurement", "router"), ("portfolio", "portfolio_router"),
    ("portfolio_optimizer", "router"), ("prediction", "router"), ("preferences", "router"),
    ("price_target", "router"), ("prices", None), ("professional_report", "router"), ("ranking", "router"),
    ("recommendation", "router"), ("research", "router"), ("regime_detection", "router"), ("reports", "router"),
    ("risk", "risk_router"), ("scheduler", "scheduler_router"), ("search", "router"),
    ("sector_rotation", "router"), ("sectors", "sector_router"), ("strategy", "strategy_router"),
    ("technical_indicators", "tech_ind_router"), ("technical_strength", "router"), ("timescaledb", "router"),
    ("top_picks", "router"), ("trade_journal", "router"), ("trading_calendar", "router"),
    ("trading_portfolio", "router"), ("users", "users_router"), ("valuation", "router"),
    ("version", "version_router"), ("watchlists", "router"), ("public_market", "router"),
    ("mfa", "router"),
)


def _router_candidates(module: object) -> list[APIRouter]:
    return [value for _, value in inspect.getmembers(module) if isinstance(value, APIRouter)]


def _resolve_module_routers(module_name: str, preferred: str | None) -> list[APIRouter]:
    module = importlib.import_module(f"{__package__}.{module_name}")
    if preferred:
        selected = getattr(module, preferred, None)
        if isinstance(selected, APIRouter):
            return [selected]
        return _router_candidates(module)
    return _router_candidates(module)


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
                if id(router) not in seen:
                    api_router.include_router(router)
                    seen.add(id(router))
        except Exception as exc:
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
    if failures:
        logger.error("API v1 router registration failures: %s", " | ".join(failures))
    return api_router


v1_router = _build_router()
__all__ = ["v1_router"]
