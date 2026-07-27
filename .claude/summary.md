# Summary

## Objective
- Build a comprehensive financial data analysis platform with multiple AI engines for pattern detection, risk assessment, market analysis, and ensemble predictions

## Important Details
- All services follow existing codebase patterns: SQLAlchemy async models, service classes with session injection, FastAPI routers with dependency injection
- No external Python dependencies added beyond project requirements; all computations use pure Python/stdlib
- All new models registered in `models/__init__.py`, all new routers registered in `api/v1/__init__.py`, all new dependencies registered in `api/dependencies.py`
- API requires API key authentication via `require_api_key` dependency
- Tests use `sqlite+aiosqlite:///` in-memory database with `pytest-asyncio`
- Run with `--noconftest --override-ini="asyncio_mode=auto"` due to pre-existing bugs in conftest and several modules
- **Pre-existing bugs fixed**: `company_service.py` (`list[str]` shadowed by `list()` method → `Sequence[str]`), `news.py` (late `articles` relationship → inline), `db/mixins.py` (`BigInteger` → `Integer` for SQLite autoincrement compat), `jobs/__init__.py` (class names vs function name aliases)

## Work State
### Completed
- **Corporate Actions Engine**: `CorporateAction` model with split/bonus/dividend/rights/merger/acquisition + 6 static adjustment methods. 18 tests.
- **Financial Statement Engine**: `FinancialStatement` + `FinancialLineItem` models. 17/15/13 standard concepts per statement type. Ratios: ROE, ROA, D/E, profit/operating margin, asset turnover, interest coverage, OCF ratio. 15 tests.
- **News Engine**: `NewsArticle` with 3-layer dedup (source+source_id, url_hash SHA256, fingerprint MD5), 10 built-in categories. 22 tests.
- **News NLP Engine**: Financial lexicon sentiment, regex NER, `CompanyMapper`, 10-sector keywords, 25 event patterns, weighted confidence scorer. 22 tests.
- **Technical Indicator Engine**: 22 indicators (7 MAs, 5 oscillators, 3 volatility, 2 trend, 4 volume, 1 momentum). 40+ tests.
- **Fundamental Engine**: 22 metrics across 7 categories (valuation, profitability, leverage, liquidity, growth, efficiency, quality). 25 tests.
- **Sector Engine**: `SectorPerformance` model. `SectorEngine` with equal-weighted returns across 8 periods, momentum scoring, relative strength, rotation signals, historical performance. Router + tests. 18 tests.
- **Market Breadth Engine**: `MarketBreadth` model. Daily A/D counts, volume breadth, new highs/lows, cumulative A/D line, SMA-based oscillator, weighted index strength. 12 API endpoints. 24 tests.
- **Pattern Recognition Engine**: `ChartPattern` + `SupportResistance` models. Pattern detectors: double top/bottom, cup handle, flags (bull/bear), triangles (symmetrical/ascending/descending). S/R clustering with strength. Rule-based AI classification. 16 API endpoints. 22 tests.
- **Historical Similarity Engine**: `SimilarityAnalysis` + `SimilarityMatch` models. Min-max normalization, Pearson correlation (30%) + Euclidean distance (50%) + volume similarity (20%). Cross-symbol search. Forward returns at 5 horizons. Optimal holding period. 7 API endpoints. 23 tests.
- **Risk Engine**: `RiskMetrics` + `PortfolioRisk` models. MDD (5 periods), annualized volatility (3 windows), liquidity brackets, gap frequency/magnitude, news-based event risk. Markowitz portfolio risk (covariance, VaR 95/99, ES, diversification, concentration). Composite risk score + rating. 9 API endpoints. 25 tests.
- **Decision Engine**: `TradingDecision` model. Weighted opportunity score (6 factors), confidence (5 factors), 5-level recommendation, structured explanation with KEY FACTORS + ACTION sections. 6 API endpoints. 22 tests.
- **Ensemble AI Engine**: `EnsemblePrediction` model, `EnsembleAIEngine` service orchestrating 6 sub-analyzers: Technical (RSI/MACD/MAs), Fundamental (PE/ROE/quality), News (sentiment), Macro (sector+breadth), Risk (inverted), Pattern (chart+similarity). Weighted voting with configurable weights. Agreement calculation. Explainable output with structured text. 6 API endpoints. 36 unit tests + 9 integration tests (45 total, all passing).

### Active
- None

### Blocked
- None

## Next Move
1. Run full test suite when conftest is fixed: `python -m pytest tests/unit/ -v`
2. Or run individual engine tests with: `--noconftest --override-ini="asyncio_mode=auto"`

## Relevant Files
- `src/titan_x/models/ensemble.py`: EnsemblePrediction model
- `src/titan_x/services/ensemble_ai_engine.py`: EnsembleAIEngine with 6 sub-analyzers + weighted voting + explanation
- `src/titan_x/api/v1/ensemble_ai.py`: 6 API endpoints at /api/v1/ensemble-ai
- `src/titan_x/api/v1/__init__.py`: Router registered (ensemble_router)
- `src/titan_x/api/dependencies.py`: get_ensemble_ai_engine dependency
- `src/titan_x/models/__init__.py`: EnsemblePrediction imported
- `tests/unit/test_ensemble_ai_engine.py`: 36 unit tests
- `tests/integration/test_ensemble_ai_api.py`: 9 integration tests
