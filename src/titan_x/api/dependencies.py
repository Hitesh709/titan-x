"""FastAPI dependency providers.

Dependency injection is kept explicit but free of boilerplate: session-only
service factories are generated from a small registry so adding a new service
is a one-line change, while providers with non-trivial wiring (auth, redis,
settings, composed services) remain hand-written for clarity.
"""
import secrets
from collections.abc import AsyncIterator, Callable
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
from titan_x.infrastructure.session_store import RedisSessionStore
from titan_x.infrastructure.task_queue import TaskQueue
from titan_x.models.user import User
from titan_x.services.ai_registry_service import AIModelRegistryService
from titan_x.services.audit_service import AuditService
from titan_x.services.auth_service import AuthService
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.broker_service import BrokerIntegrationService
from titan_x.services.company_service import CompanyService
from titan_x.services.corporate_action_detector import CorporateActionDetector
from titan_x.services.corporate_action_engine import CorporateActionEngine
from titan_x.services.corporate_tracking_service import CorporateTrackingService
from titan_x.services.data_io_service import DataImportExportService
from titan_x.services.decision_engine import DecisionEngine
from titan_x.services.ensemble_ai_engine import EnsembleAIEngine
from titan_x.services.explainability_dashboard_service import ExplainabilityDashboardService
from titan_x.services.explainability_engine import ExplainabilityEngine
from titan_x.services.financial_analysis_service import FinancialAnalysisService
from titan_x.services.financial_statement_engine import FinancialStatementEngine
from titan_x.services.fundamental_engine import FundamentalEngine
from titan_x.services.health_service import HealthService
from titan_x.services.historical_similarity_engine import HistoricalSimilarityEngine
from titan_x.services.institutional_analysis_service import InstitutionalAnalysisService
from titan_x.services.intraday_service import IntradayService
from titan_x.services.knowledge_graph_service import KnowledgeGraphService
from titan_x.services.learning_engine import LearningEngine
from titan_x.services.market_breadth_engine import MarketBreadthEngine
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.news_engine import NewsEngine
from titan_x.services.news_nlp import NewsNLPEngine
from titan_x.services.notification_delivery_service import NotificationDeliveryService
from titan_x.services.notification_service import NotificationService
from titan_x.services.optimization_engine import OptimizationEngine
from titan_x.services.order_service import OrderService
from titan_x.services.pattern_recognition_engine import PatternRecognitionEngine
from titan_x.services.portfolio_engine import PortfolioEngine
from titan_x.services.prediction_engine import PredictionEngine
from titan_x.services.preference_service import PreferenceService
from titan_x.services.price_service import CorporateActionService, PriceService
from titan_x.services.qr_auth_service import QRAuthService
from titan_x.services.report_generator import ReportGenerator
from titan_x.services.risk_engine import RiskEngine
from titan_x.services.scheduler_service import SchedulerService
from titan_x.services.sector_engine import SectorEngine
from titan_x.services.strategy_builder import StrategyBuilder
from titan_x.services.technical_indicator_engine import TechnicalIndicatorEngine
from titan_x.services.user_service import UserService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_key(supplied_key: Annotated[str | None, Security(api_key_header)], credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)], settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if supplied_key is not None and secrets.compare_digest(supplied_key, settings.api_key.get_secret_value()):
        return
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials, settings.jwt_secret_key.get_secret_value(), settings.jwt_algorithm)
        except ValueError:
            payload = None
        if payload and payload.get("type") == "access":
            return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def request_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async for session in get_session(session_factory):
        yield session


get_db = request_session


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)], session: Annotated[AsyncSession, Depends(request_session)], settings: Annotated[Settings, Depends(get_settings)]) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_token(credentials.credentials, settings.jwt_secret_key.get_secret_value(), settings.jwt_algorithm)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from exc
    if payload.get("type") not in ("access",):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type", headers={"WWW-Authenticate": "Bearer"})
    user_id = int(payload["sub"])
    repo = BaseRepository(session, User)
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_user_repository(session: Annotated[AsyncSession, Depends(request_session)]) -> BaseRepository[User]:
    return BaseRepository(session, User)


def get_health_service(session: Annotated[AsyncSession, Depends(request_session)], redis: Annotated[Redis, Depends(get_redis)]) -> HealthService:
    return HealthService(SqlAlchemyRedisHealthRepository(session, redis))


def get_auth_service(session: Annotated[AsyncSession, Depends(request_session)], settings: Annotated[Settings, Depends(get_settings)]) -> AuthService:
    return AuthService(session, settings)


def get_user_service(session: Annotated[AsyncSession, Depends(request_session)], settings: Annotated[Settings, Depends(get_settings)]) -> UserService:
    return UserService(session, settings)


def get_qr_auth_service(session: Annotated[AsyncSession, Depends(request_session)], settings: Annotated[Settings, Depends(get_settings)]) -> QRAuthService:
    return QRAuthService(session, settings)


def get_rate_limiter(request: Request) -> RateLimiter | None:
    redis = getattr(request.app.state, "redis", None)
    return RateLimiter(redis) if redis is not None else None


def get_brute_force_protector(request: Request) -> BruteForceProtector | None:
    redis = getattr(request.app.state, "redis", None)
    return BruteForceProtector(redis) if redis is not None else None


def get_cache(request: Request) -> RedisCache:
    return request.app.state.cache


def get_session_store(request: Request) -> RedisSessionStore:
    return request.app.state.session_store


def get_task_queue(request: Request) -> TaskQueue | None:
    return getattr(request.app.state, "task_queue", None)


def get_notification_delivery_service(settings: Annotated[Settings, Depends(get_settings)]) -> NotificationDeliveryService:
    return NotificationDeliveryService(settings)


def get_alert_evaluation_service(session: Annotated[AsyncSession, Depends(request_session)], delivery: Annotated[NotificationDeliveryService, Depends(get_notification_delivery_service)]) -> AlertEvaluationService:
    return AlertEvaluationService(session, delivery)


def get_notification_service(session: Annotated[AsyncSession, Depends(request_session)], settings: Annotated[Settings, Depends(get_settings)]) -> NotificationService:
    return NotificationService(session, settings)


_SESSION_SERVICE_REGISTRY: dict[str, type] = {
    "ai_registry_service": AIModelRegistryService, "audit_service": AuditService, "scheduler_service": SchedulerService,
    "company_service": CompanyService, "price_service": PriceService, "corporate_action_service": CorporateActionService,
    "news_engine": NewsEngine, "portfolio_engine": PortfolioEngine, "report_generator": ReportGenerator, "prediction_engine": PredictionEngine,
    "explainability_engine": ExplainabilityEngine, "explainability_dashboard_service": ExplainabilityDashboardService, "ensemble_ai_engine": EnsembleAIEngine,
    "decision_engine": DecisionEngine, "risk_engine": RiskEngine, "historical_similarity_engine": HistoricalSimilarityEngine,
    "pattern_recognition_engine": PatternRecognitionEngine, "market_breadth_engine": MarketBreadthEngine, "sector_engine": SectorEngine,
    "fundamental_engine": FundamentalEngine, "technical_indicator_engine": TechnicalIndicatorEngine, "news_nlp_engine": NewsNLPEngine,
    "financial_statement_engine": FinancialStatementEngine, "data_io_service": DataImportExportService, "financial_analysis_service": FinancialAnalysisService,
    "corporate_action_detector": CorporateActionDetector, "corporate_action_engine": CorporateActionEngine, "intraday_service": IntradayService,
    "preference_service": PreferenceService, "broker_integration_service": BrokerIntegrationService, "backtest_engine": BacktestEngine,
    "strategy_builder": StrategyBuilder, "optimization_engine": OptimizationEngine, "market_data_service": MarketDataService,
    "learning_engine": LearningEngine, "knowledge_graph_service": KnowledgeGraphService, "corporate_tracking_service": CorporateTrackingService,
    "order_service": OrderService, "institutional_analysis_service": InstitutionalAnalysisService,
}


def _make_session_factory(name: str, service_cls: type) -> Callable[..., object]:
    async def _factory(session: Annotated[AsyncSession, Depends(request_session)]) -> object:
        return service_cls(session)
    _factory.__name__ = f"get_{name}"
    _factory.__qualname__ = _factory.__name__
    _factory.__doc__ = f"Provide a {service_cls.__name__} bound to the request session."
    return _factory


for _service_name, _service_cls in _SESSION_SERVICE_REGISTRY.items():
    globals()[f"get_{_service_name}"] = _make_session_factory(_service_name, _service_cls)

__all__ = ["api_key_header", "bearer_scheme", "require_api_key", "request_session", "get_db", "get_current_user", "get_current_active_user", "get_redis", "get_user_repository", "get_health_service", "get_auth_service", "get_user_service", "get_qr_auth_service", "get_rate_limiter", "get_brute_force_protector", "get_cache", "get_session_store", "get_task_queue", "get_notification_delivery_service", "get_alert_evaluation_service", "get_notification_service", *(f"get_{name}" for name in _SESSION_SERVICE_REGISTRY)]
