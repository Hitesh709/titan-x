"""Domain models registered with SQLAlchemy metadata."""

from titan_x.models.auth_challenge import AuthChallenge
from titan_x.models.user_device import UserDevice
from titan_x.models.company import Company
from titan_x.models.financial import FinancialLineItem, FinancialStatement
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.adaptive_stop_loss import AdaptiveStopLoss
from titan_x.models.chart_pattern import ChartPattern, SupportResistance
from titan_x.models.opportunity_rejection import OpportunityRejection
from titan_x.models.price_target import PriceTarget
from titan_x.models.historical_similarity import SimilarityAnalysis, SimilarityMatch
from titan_x.models.risk import PortfolioRisk, RiskMetrics
from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.portfolio import Portfolio, PortfolioHolding, PortfolioTransaction
from titan_x.models.prediction import Prediction
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.intraday import IntradayPrice
from titan_x.models.knowledge_graph import (
    BusinessRelationship,
    CompanyPromoter,
    EntityEvent,
    Industry,
    Promoter,
    Sector,
    Subsidiary,
)
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory
from titan_x.models.news_nlp import NewsEntity, NewsNLPAnalysis
from titan_x.models.job import Job, JobExecution
from titan_x.models.institutional_holdings import (
    DIIHolding,
    ETFHolding,
    FIIHolding,
    InstitutionalAnalysis,
    MutualFundHolding,
)
from titan_x.models.broker import BrokerConnection
from titan_x.models.audit import AuditLog
from titan_x.models.ai_registry import AIModelRegistry, ModelDeployment
from titan_x.models.corporate_action_detection import CorporateActionDetection
from titan_x.models.data_validation import DataQualityScore, ValidationAnomaly, ValidationRun
from titan_x.models.financial_analysis import AnnualResult, FinancialAnalysis, Guidance, QuarterlyResult
from titan_x.models.preference import UserPreference
from titan_x.models.order import Order, OrderFill, Position
from titan_x.models.corporate_tracking import (
    CorporateAnalysis,
    InsiderTrade,
    PromoterTransaction,
    ShareholdingPattern,
)
from titan_x.models.price import AdjustedPrice, CorporateAction, DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.index_price import IndexDaily
from titan_x.models.watchlist import (
    Notification,
    Watchlist,
    WatchlistAiInsight,
    WatchlistAlert,
    WatchlistFolder,
    WatchlistItem,
    WatchlistItemTag,
    WatchlistMonitorEvent,
    WatchlistTag,
)
from titan_x.models.backtest import Backtest, BacktestEquityPoint, BacktestReport, BacktestSignal, BacktestTrade
from titan_x.models.learning import LearningHistory, ModelWeight
from titan_x.models.strategy import OptimizationRun, Strategy, StrategyExecution, StrategyShare
from titan_x.models.notification_history import DeliveryLog, NotificationHistory, NotificationRetry
from titan_x.models.correlation import CorrelationMatrix, CorrelationPair
from titan_x.models.global_market import GlobalAnalysis, GlobalCondition, GlobalMarketData, GlobalSimilarityResult
from titan_x.models.master_decision import MasterDecision
from titan_x.models.ranking import StockRanking
from titan_x.models.macro import MacroAnalysis, MacroFeature, MacroIndicator
from titan_x.models.data_lake import (
    DataLakeArchive,
    DataLakeCatalog,
    DataLakeDiff,
    DataLakeIngestionRun,
    DataLakeLineage,
    DataLakeMetadata,
    DataLakePipeline,
    DataLakeSchema,
    DataLakeSnapshot,
    DataLakeSource,
    DataLakeStorageRecord,
    DataLakeVersion,
)
from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.fundamental_scanner import FundamentalScanResult
from titan_x.models.market_scanner import MarketScanResult
from titan_x.models.trading_calendar import (
    CorporateCalendar,
    CorporateReminder,
    ExpiryCalendar,
    SettlementCalendar,
    SpecialSession,
    TradingHoliday,
)
from titan_x.models.market_data_collector import (
    CollectorQueueItem,
    DataChecksum,
    DataSource,
    DataValidationResult,
    SyncAuditLog,
    SyncRun,
)
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.refresh_token import RefreshToken
from titan_x.models.regime import MarketRegime, RegimeSignal
from titan_x.models.user import User
from titan_x.models.valuation import DCFValuation, RelativeValuation, SectorValuation, ValuationReport
from titan_x.models.event_intelligence import EventDetection, EventImpactHistory
from titan_x.models.pattern_library import PatternDefinition, PatternInstance
from titan_x.models.pattern_search import PatternSearchQuery, PatternSearchMatch
from titan_x.models.ai_ranking_v2 import AIRankingV2, RankingModelWeight
from titan_x.models.portfolio_optimizer import OptimizationAllocation, PortfolioOptimization
from titan_x.models.professional_report import ProfessionalReport
from titan_x.models.company_research import CompanyResearch
from titan_x.models.trade_journal import TradeJournal
from titan_x.models.performance_snapshot import PerformanceSnapshot
from titan_x.models.nightly_evaluation import NightlyEvaluation, PredictionError
from titan_x.models.model_registry import (
    ModelMetric,
    ModelRegistryDeployment,
    ModelRegistryEntry,
    ModelRegistryVersion,
    ModelTrainingRun,
)
from titan_x.models.automated_training import (
    DatasetVersion,
    FeatureSet,
    HyperparameterConfig,
    TrainingJob,
    TrainingJobCheckpoint,
    TrainingJobLog,
)
from titan_x.models.feature_store import (
    FeatureLineage,
    FeatureOfflineStore,
    FeatureStoreDef,
    FeatureStoreEntity,
    FeatureStoreValue,
    FeatureValidationResult,
    FeatureValidationRule,
    FeatureVersion,
)
from titan_x.models.experiment_manager import (
    Experiment,
    ExperimentArtifact,
    ExperimentChart,
    ExperimentMetric,
    ExperimentParameter,
    ExperimentTag,
)
from titan_x.models.model_evaluation import ModelEvaluation, ModelEvaluationMetric
from titan_x.models.recommendation import Recommendation
from titan_x.models.dynamic_ai_score import DynamicAIScore, DynamicWeight
from titan_x.models.saved_screen import SavedScreen
from titan_x.models.paper_trading import PaperAccount, PaperOrder, PaperPosition, PaperTrade, SimulatedOrder
from titan_x.models.drift_detection import (
    ConceptDriftResult,
    DistributionProfile,
    DriftAlert,
    DriftDetectionRun,
    FeatureDriftResult,
)
from titan_x.models.monitoring import SystemMetric

__all__ = [
    "SystemMetric",
    "Recommendation",
    "RefreshToken", "User", "Company", "Job", "JobExecution",
    "DailyPrice", "CorporateAction", "AdjustedPrice", "IntradayPrice",
    "FinancialStatement", "FinancialLineItem",
    "NewsArticle", "NewsArticleCategory", "NewsCategory",
    "NewsNLPAnalysis", "NewsEntity",
    "TechnicalIndicator",
    "FundamentalMetric",
    "IndexDaily",
    "MarketBreadth",
    "ChartPattern",
    "SupportResistance",
    "SimilarityAnalysis",
    "SimilarityMatch",
    "RiskMetrics",
    "PortfolioRisk",
    "TradingDecision",
    "EnsemblePrediction",
    "Prediction",
    "ExplainabilityAnalysis",
    "Portfolio",
    "PortfolioHolding",
    "PortfolioTransaction",
    "SectorPerformance",
    "Watchlist",
    "WatchlistFolder",
    "WatchlistItem",
    "WatchlistTag",
    "WatchlistItemTag",
    "WatchlistAlert",
    "WatchlistAiInsight",
    "Notification",
    "NotificationHistory",
    "DeliveryLog",
    "NotificationRetry",
    "Backtest",
    "BacktestTrade",
    "BacktestSignal",
    "BacktestEquityPoint",
    "BacktestReport",
    "Strategy",
    "OptimizationRun",
    "LearningHistory",
    "ModelWeight",
    "Sector",
    "Industry",
    "Promoter",
    "CompanyPromoter",
    "Subsidiary",
    "EntityEvent",
    "BusinessRelationship",
    "CorporateActionDetection",
    "QuarterlyResult", "AnnualResult", "Guidance", "FinancialAnalysis",
    "AIModelRegistry", "ModelDeployment",
    "AuditLog",
    "BrokerConnection",
    "UserPreference",
    "Order", "OrderFill", "Position",
    "PromoterTransaction",
    "InsiderTrade",
    "ShareholdingPattern",
    "CorporateAnalysis",
    "FIIHolding",
    "DIIHolding",
    "MutualFundHolding",
    "ETFHolding",
    "InstitutionalAnalysis",
    "DCFValuation",
    "RelativeValuation",
    "SectorValuation",
    "ValuationReport",
    "MarketRegime",
    "RegimeSignal",
    "MarketMicrostructure",
    "CorrelationPair",
    "CorrelationMatrix",
    "MacroIndicator",
    "MacroAnalysis",
    "MacroFeature",
    "GlobalMarketData",
    "GlobalAnalysis",
    "GlobalCondition",
    "GlobalSimilarityResult",
    "StockRanking",
    "MasterDecision",
    "DataSource", "SyncRun", "SyncAuditLog", "DataChecksum",
    "CollectorQueueItem", "DataValidationResult",
    "ValidationRun", "ValidationAnomaly", "DataQualityScore",
    "FeatureDefinition", "FeatureValue",
    "DataLakeCatalog", "DataLakeSchema", "DataLakeVersion",
    "DataLakePipeline", "DataLakeLineage", "DataLakeArchive",
    "DataLakeMetadata", "DataLakeStorageRecord",
    "DataLakeSource", "DataLakeIngestionRun",
    "DataLakeSnapshot", "DataLakeDiff",
    "FundamentalScanResult",
    "MarketScanResult",
    "TradingHoliday", "SpecialSession", "ExpiryCalendar",
    "SettlementCalendar", "CorporateCalendar", "CorporateReminder",
    "EventDetection", "EventImpactHistory",
    "PatternDefinition", "PatternInstance",
    "PatternSearchQuery", "PatternSearchMatch",
    "AIRankingV2", "RankingModelWeight",
    "PortfolioOptimization", "OptimizationAllocation",
    "AdaptiveStopLoss",
    "PriceTarget",
    "OpportunityRejection",
    "ProfessionalReport",
    "CompanyResearch",
    "TradeJournal",
    "PerformanceSnapshot",
    "NightlyEvaluation",
    "PredictionError",
    "ModelRegistryEntry",
    "ModelRegistryVersion",
    "ModelTrainingRun",
    "ModelMetric",
    "ModelRegistryDeployment",
    "DatasetVersion",
    "FeatureSet",
    "HyperparameterConfig",
    "TrainingJob",
    "TrainingJobCheckpoint",
    "TrainingJobLog",
    "FeatureStoreEntity",
    "FeatureStoreDef",
    "FeatureVersion",
    "FeatureStoreValue",
    "FeatureOfflineStore",
    "FeatureLineage",
    "FeatureValidationRule",
    "FeatureValidationResult",
    "Experiment",
    "ExperimentParameter",
    "ExperimentMetric",
    "ExperimentArtifact",
    "ExperimentChart",
    "ExperimentTag",
    "ModelEvaluation",
    "ModelEvaluationMetric",
    "DistributionProfile",
    "DriftDetectionRun",
    "FeatureDriftResult",
    "ConceptDriftResult",
    "DriftAlert",
    "DynamicAIScore",
    "DynamicWeight",
    "SavedScreen",
    "PaperAccount",
    "PaperOrder",
    "PaperPosition",
    "PaperTrade",
    "StrategyShare",
    "StrategyExecution",
    "AuthChallenge", "UserDevice",
]
