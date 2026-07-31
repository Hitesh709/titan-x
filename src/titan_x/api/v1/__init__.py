from fastapi import APIRouter

from titan_x.api.v1.admin import admin_router
from titan_x.api.v1.audit import router as audit_router
from titan_x.api.v1.ai_registry import router as ai_registry_router
from titan_x.api.v1.auth import auth_router
from titan_x.api.v1.institutional_analysis import inst_router
from titan_x.api.v1.corporate_action_detection import cad_router
from titan_x.api.v1.corporate_reminders import router as corporate_reminders_router
from titan_x.api.v1.corporate_tracking import corp_track_router
from titan_x.api.v1.data_io import router as data_io_router
from titan_x.api.v1.data_validation import router as data_validation_router
from titan_x.api.v1.companies import companies_router
from titan_x.api.v1.health import health_router
from titan_x.api.v1.intraday import intraday_router
from titan_x.api.v1.knowledge_graph import kg_router
from titan_x.api.v1.news import news_router
from titan_x.api.v1.news_nlp import news_nlp_router
from titan_x.api.v1.fundamentals import fund_router
from titan_x.api.v1.market_breadth import market_breadth_router
from titan_x.api.v1.pattern_recognition import pattern_router
from titan_x.api.v1.historical_similarity import hist_sim_router
from titan_x.api.v1.risk import risk_router
from titan_x.api.v1.decision import decision_router
from titan_x.api.v1.ensemble_ai import ensemble_router
from titan_x.api.v1.prediction import prediction_router
from titan_x.api.v1.reports import router as reports_router
from titan_x.api.v1.explainability import explainability_router
from titan_x.api.v1.portfolio import portfolio_router
from titan_x.api.v1.preferences import router as prefs_router
from titan_x.api.v1.sectors import sector_router
from titan_x.api.v1.technical_indicators import tech_ind_router
from titan_x.api.v1.monitoring import router as monitoring_router
from titan_x.api.v1.corporate_actions_engine import ca_engine_router
from titan_x.api.v1.financial_analysis import router as fa_router
from titan_x.api.v1.financial_statements import fin_stmt_router
from titan_x.api.v1.prices import corp_actions_router, prices_router
from titan_x.api.v1.scheduler import scheduler_router
from titan_x.api.v1.users import users_router
from titan_x.api.v1.version import version_router
from titan_x.api.v1.backtest import backtest_router
from titan_x.api.v1.broker import router as broker_router
from titan_x.api.v1.correlation import router as correlation_router
from titan_x.api.v1.datalake import router as datalake_router
from titan_x.api.v1.global_market import router as global_market_router
from titan_x.api.v1.learning import learning_router
from titan_x.api.v1.feature_engineering import router as feature_engineering_router
from titan_x.api.v1.market_data_collector import router as mdc_router
from titan_x.api.v1.master_decision import router as master_decision_router
from titan_x.api.v1.ranking import router as ranking_router
from titan_x.api.v1.fundamental_scanner import router as fundamental_scanner_router
from titan_x.api.v1.news_scanner import router as news_scanner_router
from titan_x.api.v1.market_scanner import router as market_scanner_router
from titan_x.api.v1.macro import router as macro_router
from titan_x.api.v1.microstructure import router as microstructure_router
from titan_x.api.v1.regime_detection import router as regime_router
from titan_x.api.v1.valuation import router as valuation_router
from titan_x.api.v1.market_data import router as market_data_router
from titan_x.api.v1.indices import router as indices_router
from titan_x.api.v1.strategy import strategy_router
from titan_x.api.v1.trading_calendar import router as trading_calendar_router
from titan_x.api.v1.timescaledb import router as timescaledb_router
from titan_x.api.v1.order import router as order_router
from titan_x.api.v1.watchlists import router as watchlist_router
from titan_x.api.v1.adaptive_stop_loss import router as adaptive_stop_loss_router
from titan_x.api.v1.opportunity_rejection import router as opportunity_rejection_router
from titan_x.api.v1.price_target import router as price_target_router
from titan_x.api.v1.event_intelligence import router as event_intelligence_router
from titan_x.api.v1.pattern_library import router as pattern_library_router
from titan_x.api.v1.pattern_search import router as pattern_search_router
from titan_x.api.v1.ai_ranking_v2 import router as ai_ranking_v2_router
from titan_x.api.v1.portfolio_optimizer import router as portfolio_optimizer_router
from titan_x.api.v1.professional_report import router as professional_report_router
from titan_x.api.v1.company_research import router as company_research_router
from titan_x.api.v1.trade_journal import router as trade_journal_router
from titan_x.api.v1.performance_measurement import router as performance_measurement_router
from titan_x.api.v1.nightly_evaluation import router as nightly_evaluation_router
from titan_x.api.v1.model_registry import router as model_registry_router
from titan_x.api.v1.automated_training import router as automated_training_router
from titan_x.api.v1.feature_store import router as feature_store_router
from titan_x.api.v1.experiment_manager import router as experiment_manager_router
from titan_x.api.v1.model_evaluation import router as model_evaluation_router
from titan_x.api.v1.drift_detection import router as drift_detection_router
from titan_x.api.v1.recommendation import router as recommendation_router
from titan_x.api.v1.dynamic_ai_score import router as dynamic_ai_score_router
from titan_x.api.v1.market_heatmap import router as market_heatmap_router
from titan_x.api.v1.sector_rotation import router as sector_rotation_router
from titan_x.api.v1.advanced_screener import router as advanced_screener_router
from titan_x.api.v1.paper_trading import router as paper_trading_router
from titan_x.api.v1.dashboard import router as dashboard_router
from titan_x.api.v1.search import router as search_router
from titan_x.api.v1.export import router as export_router

v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/")
async def v1_root() -> dict[str, str]:
    return {
        "app": "TITAN X API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health/live",
    }


v1_router.include_router(ai_registry_router)
v1_router.include_router(audit_router)
v1_router.include_router(health_router)
v1_router.include_router(version_router)
v1_router.include_router(auth_router)
v1_router.include_router(admin_router)
v1_router.include_router(users_router)
v1_router.include_router(scheduler_router)
v1_router.include_router(monitoring_router)
v1_router.include_router(cad_router)
v1_router.include_router(fa_router)
v1_router.include_router(inst_router)
v1_router.include_router(corporate_reminders_router)
v1_router.include_router(corp_track_router)
v1_router.include_router(data_io_router)
v1_router.include_router(data_validation_router)
v1_router.include_router(companies_router)
v1_router.include_router(prices_router)
v1_router.include_router(corp_actions_router)
v1_router.include_router(news_router)
v1_router.include_router(news_nlp_router)
v1_router.include_router(intraday_router)
v1_router.include_router(kg_router)
v1_router.include_router(fin_stmt_router)
v1_router.include_router(market_breadth_router)
v1_router.include_router(pattern_router)
v1_router.include_router(hist_sim_router)
v1_router.include_router(risk_router)
v1_router.include_router(prediction_router)
v1_router.include_router(reports_router)
v1_router.include_router(ensemble_router)
v1_router.include_router(explainability_router)
v1_router.include_router(portfolio_router)
v1_router.include_router(prefs_router)
v1_router.include_router(decision_router)
v1_router.include_router(sector_router)
v1_router.include_router(fund_router)
v1_router.include_router(tech_ind_router)
v1_router.include_router(ca_engine_router)
v1_router.include_router(backtest_router)
v1_router.include_router(broker_router)
v1_router.include_router(watchlist_router)
v1_router.include_router(order_router)
v1_router.include_router(strategy_router)
v1_router.include_router(trading_calendar_router)
v1_router.include_router(timescaledb_router)
v1_router.include_router(market_data_router)
v1_router.include_router(indices_router)
v1_router.include_router(correlation_router)
v1_router.include_router(datalake_router)
v1_router.include_router(global_market_router)
v1_router.include_router(learning_router)
v1_router.include_router(fundamental_scanner_router)
v1_router.include_router(news_scanner_router)
v1_router.include_router(market_scanner_router)
v1_router.include_router(macro_router)
v1_router.include_router(master_decision_router)
v1_router.include_router(feature_engineering_router)
v1_router.include_router(mdc_router)
v1_router.include_router(microstructure_router)
v1_router.include_router(regime_router)
v1_router.include_router(valuation_router)
v1_router.include_router(adaptive_stop_loss_router)
v1_router.include_router(opportunity_rejection_router)
v1_router.include_router(price_target_router)
v1_router.include_router(event_intelligence_router)
v1_router.include_router(pattern_library_router)
v1_router.include_router(pattern_search_router)
v1_router.include_router(ai_ranking_v2_router)
v1_router.include_router(portfolio_optimizer_router)
v1_router.include_router(professional_report_router)
v1_router.include_router(company_research_router)
v1_router.include_router(trade_journal_router)
v1_router.include_router(performance_measurement_router)
v1_router.include_router(nightly_evaluation_router)
v1_router.include_router(model_registry_router)
v1_router.include_router(automated_training_router)
v1_router.include_router(feature_store_router)
v1_router.include_router(experiment_manager_router)
v1_router.include_router(model_evaluation_router)
v1_router.include_router(drift_detection_router)
v1_router.include_router(recommendation_router)
v1_router.include_router(dynamic_ai_score_router)
v1_router.include_router(market_heatmap_router)
v1_router.include_router(sector_rotation_router)
v1_router.include_router(advanced_screener_router)
v1_router.include_router(paper_trading_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(search_router)
v1_router.include_router(export_router)

__all__ = ["v1_router"]
