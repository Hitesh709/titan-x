"""Re-export facade for the market data collection pipeline.

Keeps the historical import path ``titan_x.services.market_data_collector_service``
working while the implementation lives in :mod:`titan_x.services.market_data_collection`.
"""
from titan_x.services.market_data_collection import (
    ChecksumService,
    DataValidator,
    LiveStreamAdapter,
    MarketDataCollectorService,
    MockLiveStreamAdapter,
    MockSourceAdapter,
    SourceAdapter,
    SyncOrchestrator,
    SyncResult,
    ValidationOutcome,
)

__all__ = [
    "ChecksumService",
    "DataValidator",
    "LiveStreamAdapter",
    "MarketDataCollectorService",
    "MockLiveStreamAdapter",
    "MockSourceAdapter",
    "SourceAdapter",
    "SyncOrchestrator",
    "SyncResult",
    "ValidationOutcome",
]