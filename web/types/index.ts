export interface User {
  id: string
  email: string
  full_name?: string
  role?: string
  is_active: boolean
  is_verified: boolean
  created_at?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface MarketIndex {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
}

export interface Stock {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
  volume: number
  marketCap: number
}

export interface PortfolioHolding {
  symbol: string
  name: string
  shares: number
  avgPrice: number
  currentPrice: number
  totalValue: number
  gainLoss: number
  gainLossPercent: number
  weight: number
}

export interface NewsItem {
  id: string
  title: string
  source: string
  sentiment: "positive" | "negative" | "neutral"
  timestamp: string
  url: string
  summary: string
  symbols: string[]
}

export interface Watchlist {
  id: string
  name: string
  symbols: string[]
  created_at: string
}

export interface Alert {
  id: string
  symbol: string
  type: "price_above" | "price_below" | "percent_change" | "volume"
  condition: string
  value: number
  triggered: boolean
  created_at: string
}

export interface AiRecommendation {
  symbol: string
  action: "buy" | "sell" | "hold"
  confidence: number
  targetPrice: number
  reasoning: string
  timeframe: string
}

export interface ChartDataPoint {
  date: string
  value: number
  volume?: number
}

export interface LayerScore {
  score: number
  signal: string
  confidence: number
  evidence: string[]
  metrics?: Record<string, number | string | null>
  source?: string
}

export interface TopPick {
  symbol: string
  name: string
  sector?: string | null
  price: number
  change_pct: number
  change_1m_pct: number
  composite: number
  signal: string
  summary: string
  layers: {
    trend: LayerScore
    smart_money: LayerScore
    fundamentals: LayerScore
    news: LayerScore
    regime: LayerScore
    risk: LayerScore
  }
}

export interface TopPicksResponse {
  generated_at: string
  universe_size: number
  scored: number
  layers: { key: string; label: string; weight: number }[]
  top_picks: TopPick[]
}

// ---------- Market breadth ----------
export interface BreadthSummary {
  trade_date: string
  advancing: number
  declining: number
  advance_decline_ratio?: number
  new_highs: number
  new_lows: number
  breadth_oscillator?: number
  index_strength_score?: number
}

export interface ADLinePoint {
  trade_date: string
  advance_decline_line: number
}

export interface OscillatorPoint {
  trade_date: string
  breadth_oscillator: number
}

export interface HighLowPoint {
  trade_date: string
  new_highs: number
  new_lows: number
}

export interface VolumeBreadthPoint {
  trade_date: string
  advancing_volume: number
  declining_volume: number
}

// ---------- Indices ----------
export interface IndexSnapshot {
  symbol: string
  name: string
  open: number
  high: number
  low: number
  close: number
  change: number
  change_pct: number
  volume: number
  trade_date?: string
}

export interface IndexHistoryPoint {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface IndexPerformance {
  periods?: Record<string, number | null>
}

// ---------- Sectors ----------
export interface SectorRanking {
  sector: string
  rank?: number
  constituent_count?: number
  momentum_score?: number
  relative_strength?: number
  ytd_return?: number | null
  periods?: Record<string, number | null>
  rotation_signal: string | null
}

export interface SectorRotation {
  as_of_date: string
  leading: Array<Record<string, unknown>>
  neutral: Array<Record<string, unknown>>
  lagging: Array<Record<string, unknown>>
  rotation_breadth?: number
}

export interface SectorData {
  name: string
  constituent_count?: number
  return_pct?: number | null
}

// ---------- News ----------
export interface NewsArticle {
  id: string
  symbol?: string | null
  title: string
  source: string
  published_at?: string | null
  url: string
  summary?: string | null
  sentiment?: string
}

export interface NewsRow {
  id: string
  symbol?: string | null
  title: string
  source: string
  published_at?: string | null
  sentiment?: string
  sentiment_confidence?: number
  url?: string | null
}

// ---------- Paper trading ----------
export interface PaperPosition {
  symbol: string
  quantity: number
  average_price: number
  current_price: number | null
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  realized_pnl: number
  cost_basis: number
  allocation_pct: number
  sector?: string | null
}

export interface PaperAccountSummary {
  portfolio_value: number
  positions_count: number
  cash_balance: number
  initial_capital: number
  total_pnl: number
  total_unrealized_pnl: number
  total_pnl_pct: number
  total_realized_pnl: number
}

export interface PaperAnalytics {
  win_rate: number
  profit_factor?: number | null
  expectancy?: number | null
  cagr?: number | null
  sharpe_ratio?: number | null
  sortino_ratio?: number | null
  max_drawdown?: number | null
  max_drawdown_amount?: number | null
  total_trades: number
  winning_trades: number
  losing_trades: number
}

export interface PerformanceReport {
  total_trades: number
  filled_orders: number
  cancelled_orders: number
  win_rate: number
  winning_trades?: number
  losing_trades?: number
  account?: PaperAccountSummary
}

export interface EquityCurvePoint {
  date: string
  equity: number
}

export interface SectorExposure {
  sector: string
  positions: number
  market_value: number
  allocation_pct: number
}

export interface PaperTradeRow {
  id: number
  trade_time?: string | null
  symbol: string
  side: string
  quantity: number
  price: number
  commission: number
  realized_pnl: number | null
}

// ---------- Research ----------
export interface ResearchCompany {
  symbol: string
  company_name?: string
  sector?: string | null
  industry?: string | null
  market_cap?: number | null
  days: number
  has_research?: boolean
  direction?: string
  signal?: string | null
  score?: number | null
  confidence?: number | null
  predicted_return_pct?: number | null
  current_price?: number | null
  price_target?: number | null
  risk_level?: string | null
  timeframe?: string | null
}

export interface ResearchCompanyPage {
  items: ResearchCompany[]
  total?: number
}

export interface ResearchDetail {
  days: number
  has_research?: boolean
  company_name?: string
  direction?: string
  signal?: string | null
  risk_level?: string | null
  timeframe?: string | null
  generated_at?: string | null
  score?: number | null
  confidence?: number | null
  predicted_return_pct?: number | null
  current_price?: number | null
  price_target?: number | null
  reasoning?: string | null
  evidence?: string[]
  caution?: string[]
}

// ---------- Market data ----------
export interface MarketQuote {
  symbol: string
  name?: string
  last_price?: number | null
  change?: number | null
  change_percent?: number | null
  volume: number
  market_cap?: number | null
  exchange?: string
  market_state?: string | null
  currency?: string
  timestamp?: string
  source?: string
}

export interface BatchQuotesResponse {
  quotes: MarketQuote[]
  count?: number
}

export interface CompanyProfile {
  name?: string
  exchange?: string
  sector?: string | null
  industry?: string | null
  market_cap?: number | null
  currency?: string
}

export interface StockHistoryResponse {
  points: IndexHistoryPoint[]
}

export interface CompanySearchResult {
  symbol: string
  company_name?: string
  sector?: string | null
}

// ---------- AI picks ----------
export interface AiPick {
  symbol: string
  combined_signal: string
  combined_score: number
  combined_confidence: number
  expected_return_pct?: number | null
  risk?: string | null
  holding_period_days?: number | null
  evidence?: string[]
  why_buy?: string[]
  why_not_buy?: string[]
}

// ---------- Dashboard / heatmap ----------
export interface MarketHeatmapData {
  summary: {
    avg_sector_return_pct?: number | null
    advancing_sectors?: number
    declining_sectors?: number
    total_sectors?: number
    market_breadth?: number | null
    index_strength?: number | null
  }
  breadth: {
    advance_decline_ratio?: number | null
  }
}

export interface HeatmapMover {
  symbol: string
  close?: number | null
  volume: number
  return_pct?: number | null
}

export interface PortfolioSummary {
  has_account?: boolean
  total_equity: number
  total_return_pct: number
  cash_balance: number
  positions_value: number
  unrealized_pnl: number
  positions_count: number
  positions?: Array<{
    symbol: string
    quantity: number
    current_price: number | null
    avg_price: number | null
    market_value: number
  }>
}

export interface DashboardAlert {
  id: string
  severity: string
  symbol?: string
  event_type?: string
  is_read?: boolean
  title?: string
  message?: string | null
  triggered_at?: string | null
}

export interface WatchlistSummary {
  id: string | number
  name: string
  item_count: number
  description?: string | null
  symbols: string[]
}

// ---------- Recommendations ----------
export interface ScanStatus {
  running?: boolean
  last?: {
    stored?: number
    failed?: number
    finished_at?: string | null
  }
}

export interface StockRecommendation {
  id: string
  symbol: string
  direction?: string
  signal?: string | null
  confidence?: number
  predicted_return_pct?: number | null
  timeframe?: string | null
  risk_level?: string | null
  price_target?: number | null
  generated_at?: string | null
  metadata_json?: string | null
  inputs_json?: string | null
  current_price?: number | null
}

export interface RecommendationsPage {
  items: StockRecommendation[]
  total?: number
}

export interface IntradayRecommendation {
  symbol: string
  segment: "equity" | "fno"
  instrument: "EQUITY" | "FUTURES" | "OPTIONS"
  direction: "BUY" | "SELL" | "HOLD"
  signal: string
  score: number
  confidence: number
  current_price: number
  entry_price: number
  target_price: number
  stop_price: number
  risk_reward: number
  expected_return_pct: number
  volume_ratio: number
  rsi: number | null
  ema20: number | null
  ema50: number | null
  momentum_pct: number
  option_bias?: "CALL" | "PUT" | "NONE"
  option_strike?: number | null
  timeframe: string
  generated_at: string
  evidence: string[]
  caution: string[]
}

export interface IntradayRecommendationsResponse {
  segment: "equity" | "fno"
  generated_at: string
  market_open: boolean
  universe_size: number
  scanned: number
  recommendations: IntradayRecommendation[]
}
