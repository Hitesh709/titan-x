import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.core.config import Settings, get_settings
from titan_x.core.security import decode_token
from titan_x.db.repository import BaseRepository
from titan_x.db.session import get_session
from titan_x.infrastructure.brute_force_protection import BruteForceProtector
from titan_x.infrastructure.cache import RedisCache
from titan_x.infrastructure.health_repository import SqlAlchemyRedisHealthRepository
from titan_x.infrastructure.rate_limiter import RateLimiter
from titan_x.infrastructure.scheduler import Scheduler
from titan_x.infrastructure.session_store import RedisSessionStore
from titan_x.infrastructure.task_queue import TaskQueue
from titan_x.models.user import User
from titan_x.services.ai_registry_service import AIModelRegistryService
from titan_x.services.audit_service import AuditService
from titan_x.services.auth_service import AuthService
from titan_x.services.company_service import CompanyService
from titan_x.services.corporate_action_detector import CorporateActionDetector
from titan_x.services.financial_analysis_service import FinancialAnalysisService
from titan_x.services.data_io_service import DataImportExportService
from titan_x.services.corporate_tracking_service import CorporateTrackingService
from titan_x.services.institutional_analysis_service import InstitutionalAnalysisService
from titan_x.services.health_service import HealthService
from titan_x.services.intraday_service import IntradayService
from titan_x.services.knowledge_graph_service import KnowledgeGraphService
from titan_x.services.corporate_action_engine import CorporateActionEngine
from titan_x.services.financial_statement_engine import FinancialStatementEngine
from titan_x.services.news_engine import NewsEngine
from titan_x.services.news_nlp import NewsNLPEngine
from titan_x.services.fundamental_engine import FundamentalEngine
from titan_x.services.market_breadth_engine import MarketBreadthEngine
from titan_x.services.pattern_recognition_engine import PatternRecognitionEngine
from titan_x.services.historical_similarity_engine import HistoricalSimilarityEngine
from titan_x.services.risk_engine import RiskEngine
from titan_x.services.decision_engine import DecisionEngine
from titan_x.services.ensemble_ai_engine import EnsembleAIEngine
from titan_x.services.portfolio_engine import PortfolioEngine
from titan_x.services.prediction_engine import PredictionEngine
from titan_x.services.report_generator import ReportGenerator
from titan_x.services.sector_engine import SectorEngine
from titan_x.services.explainability_dashboard_service import ExplainabilityDashboardService
from titan_x.services.explainability_engine import ExplainabilityEngine
from titan_x.services.technical_indicator_engine import TechnicalIndicatorEngine
from titan_x.services.alert_evaluation_service import AlertEvaluationService
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.broker_service import BrokerIntegrationService
from titan_x.services.learning_engine import LearningEngine
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.notification_delivery_service import NotificationDeliveryService
from titan_x.services.notification_service import NotificationService
from titan_x.services.preference_service import PreferenceService
from titan_x.services.order_service import OrderService
from titan_x.services.optimization_engine import OptimizationEngine
from titan_x.services.strategy_builder import StrategyBuilder
from titan_x.services.price_service import CorporateActionService, PriceService
from titan_x.services.scheduler_service import SchedulerService
from titan_x.services.user_service import UserService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_key(
    supplied_key: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected_key = settings.api_key.get_secret_value()
    if supplied_key is None or not secrets.compare_digest(supplied_key, expected_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def request_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async for session in get_session(session_factory):
        yield session


get_db = request_session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(request_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(
            credentials.credentials,
            settings.jwt_secret_key.get_secret_value(),
            settings.jwt_algorithm,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") not in ("access",):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload["sub"])
    repo = BaseRepository(session, User)
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


async def get_ai_registry_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> AIModelRegistryService:
    return AIModelRegistryService(session)


async def get_audit_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> AuditService:
    return AuditService(session)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> BaseRepository[User]:
    return BaseRepository(session, User)


def get_health_service(
    session: Annotated[AsyncSession, Depends(request_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> HealthService:
    return HealthService(SqlAlchemyRedisHealthRepository(session, redis))


def get_auth_service(
    session: Annotated[AsyncSession, Depends(request_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(session, settings)


def get_user_service(
    session: Annotated[AsyncSession, Depends(request_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserService:
    return UserService(session, settings)


def get_rate_limiter(request: Request) -> RateLimiter:
    return RateLimiter(request.app.state.redis)


def get_brute_force_protector(request: Request) -> BruteForceProtector:
    return BruteForceProtector(request.app.state.redis)


def get_cache(request: Request) -> RedisCache:
    return request.app.state.cache


def get_session_store(request: Request) -> RedisSessionStore:
    return request.app.state.session_store


def get_task_queue(request: Request) -> TaskQueue | None:
    return getattr(request.app.state, "task_queue", None)


async def get_scheduler_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> SchedulerService:
    return SchedulerService(session)


async def get_company_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> CompanyService:
    return CompanyService(session)


async def get_price_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PriceService:
    return PriceService(session)


async def get_corporate_action_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> CorporateActionService:
    return CorporateActionService(session)


async def get_news_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> NewsEngine:
    return NewsEngine(session)


async def get_portfolio_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PortfolioEngine:
    return PortfolioEngine(session)


async def get_report_generator(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> ReportGenerator:
    return ReportGenerator(session)


async def get_prediction_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PredictionEngine:
    return PredictionEngine(session)


async def get_explainability_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> ExplainabilityEngine:
    return ExplainabilityEngine(session)


async def get_explainability_dashboard_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> ExplainabilityDashboardService:
    return ExplainabilityDashboardService(session)


async def get_ensemble_ai_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> EnsembleAIEngine:
    return EnsembleAIEngine(session)


async def get_decision_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> DecisionEngine:
    return DecisionEngine(session)


async def get_risk_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> RiskEngine:
    return RiskEngine(session)


async def get_historical_similarity_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> HistoricalSimilarityEngine:
    return HistoricalSimilarityEngine(session)


async def get_pattern_recognition_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PatternRecognitionEngine:
    return PatternRecognitionEngine(session)


async def get_market_breadth_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MarketBreadthEngine:
    return MarketBreadthEngine(session)


async def get_sector_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> SectorEngine:
    return SectorEngine(session)


async def get_fundamental_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> FundamentalEngine:
    return FundamentalEngine(session)


async def get_technical_indicator_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> TechnicalIndicatorEngine:
    return TechnicalIndicatorEngine(session)


async def get_news_nlp_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> NewsNLPEngine:
    return NewsNLPEngine(session)


async def get_financial_statement_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> FinancialStatementEngine:
    return FinancialStatementEngine(session)


async def get_data_io_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> DataImportExportService:
    return DataImportExportService(session)


async def get_financial_analysis_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> FinancialAnalysisService:
    return FinancialAnalysisService(session)


async def get_corporate_action_detector(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> CorporateActionDetector:
    return CorporateActionDetector(session)


async def get_corporate_action_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> CorporateActionEngine:
    return CorporateActionEngine(session)


async def get_intraday_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> IntradayService:
    return IntradayService(session)


async def get_notification_delivery_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationDeliveryService:
    return NotificationDeliveryService(settings)


async def get_alert_evaluation_service(
    session: Annotated[AsyncSession, Depends(request_session)],
    delivery: Annotated[NotificationDeliveryService, Depends(get_notification_delivery_service)],
) -> AlertEvaluationService:
    return AlertEvaluationService(session, delivery)


async def get_preference_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PreferenceService:
    return PreferenceService(session)


async def get_notification_service(
    session: Annotated[AsyncSession, Depends(request_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationService:
    return NotificationService(session, settings)


async def get_broker_integration_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> BrokerIntegrationService:
    return BrokerIntegrationService(session)


async def get_backtest_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> BacktestEngine:
    return BacktestEngine(session)


async def get_strategy_builder(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> StrategyBuilder:
    return StrategyBuilder(session)


async def get_optimization_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> OptimizationEngine:
    return OptimizationEngine(session)


async def get_market_data_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MarketDataService:
    return MarketDataService(session)


async def get_learning_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> LearningEngine:
    return LearningEngine(session)


async def get_knowledge_graph_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> KnowledgeGraphService:
    return KnowledgeGraphService(session)


async def get_corporate_tracking_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> CorporateTrackingService:
    return CorporateTrackingService(session)


async def get_order_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> OrderService:
    return OrderService(session)


async def get_institutional_analysis_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> InstitutionalAnalysisService:
    return InstitutionalAnalysisService(session)
