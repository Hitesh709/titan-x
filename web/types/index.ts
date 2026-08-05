export interface User {
  id: number
  email: string
  role: string
  is_active: boolean
  is_verified: boolean
  full_name?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface MessageResponse {
  message: string
}

export interface ForgotPasswordResponse {
  message: string
  reset_url?: string | null
}

export interface SendVerificationResponse {
  message: string
  verification_url?: string | null
}

export interface RegisterResponse {
  id: number
  email: string
  role: string
  is_active: boolean
  is_verified: boolean
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

export interface PortfolioPosition {
  symbol: string
  quantity: number
  avg_price: number
  current_price: number | null
  cost_basis: number
  market_value: number
  unrealized_pnl: number
  realized_pnl: number
}

export interface PortfolioSummary {
  has_account: boolean
  account_id?: number
  cash_balance?: number
  positions_value?: number
  total_equity?: number
  unrealized_pnl?: number
  total_return?: number
  total_return_pct?: number
  positions_count?: number
  positions?: PortfolioPosition[]
}

export interface WatchlistSummary {
  id: number
  name: string
  description?: string | null
  item_count: number
  symbols: string[]
}

export interface AiPick {
  symbol: string
  combined_score: number
  combined_signal: string
  combined_confidence: number
  as_of_date?: string | null
  expected_return_pct?: number | null
  risk?: string | null
  holding_period_days?: number | null
  evidence?: string[]
  why_buy?: string[]
  why_not_buy?: string[]
}

export interface DashboardNewsItem {
  id: number
  symbol?: string | null
  title: string
  source: string
  published_at?: string | null
  sentiment: string
  sentiment_confidence?: number | null
}

export interface DashboardPerformance {
  has_data: boolean
  cagr?: number
  win_rate?: number
  profit_factor?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  max_drawdown?: number
  expectancy?: number
  total_trades?: number
  winning_trades?: number
  losing_trades?: number
}

export interface DashboardAlert {
  id: number
  symbol: string
  event_type: string
  severity: string
  title: string
  message: string
  is_read: boolean
  triggered_at?: string | null
}

export interface DashboardData {
  portfolio: PortfolioSummary
  watchlists: WatchlistSummary[]
  ai_picks: AiPick[]
  news: DashboardNewsItem[]
  performance: DashboardPerformance
  alerts: DashboardAlert[]
}

export interface SectorIndustry {
  name: string
  constituent_count: number
  return_pct: number | null
  volume: number
}

export interface SectorData {
  name: string
  return_pct: number | null
  momentum_score?: number | null
  relative_strength?: number | null
  rank?: number | null
  constituent_count: number
  volume: number
  industries: SectorIndustry[]
}

export interface HeatmapMover {
  symbol: string
  return_pct: number | null
  close: number | null
  volume: number
}

export interface MarketBreadth {
  advancing?: number | null
  declining?: number | null
  unchanged?: number | null
  total_stocks?: number | null
  advance_decline_ratio?: number | null
  advancing_volume?: number | null
  declining_volume?: number | null
  total_volume?: number | null
  new_highs?: number | null
  new_lows?: number | null
  breadth_oscillator?: number | null
  index_strength_score?: number | null
}

export interface HeatmapSummary {
  total_sectors: number
  advancing_sectors: number
  declining_sectors: number
  avg_sector_return_pct?: number | null
  total_volume: number
  best_sector?: string | null
  best_sector_return?: number | null
  worst_sector?: string | null
  worst_sector_return?: number | null
  market_breadth?: number | null
  index_strength?: number | null
}

export interface MarketHeatmapData {
  as_of_date: string
  period: string
  sectors: SectorData[]
  leaders: HeatmapMover[]
  laggards: HeatmapMover[]
  breadth: MarketBreadth
  summary: HeatmapSummary
}

export interface NewsCategory {
  id: number
  name: string
  description?: string | null
}

export interface NewsArticle {
  id: number
  title: string
  summary?: string | null
  content?: string | null
  source: string
  source_id: string
  url: string
  symbol?: string | null
  author?: string | null
  published_at?: string | null
  language?: string
  is_cleaned?: boolean
  categories?: NewsCategory[]
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface IndexSnapshot {
  symbol: string
  name: string
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  prev_close: number | null
  change: number
  change_pct: number
  volume: number
}

export interface IndicesListResponse {
  items: IndexSnapshot[]
}

export interface MarketQuote {
  symbol: string
  name: string
  last_price: number | null
  change: number | null
  change_percent: number | null
  volume: number
  market_cap?: number | null
  exchange: string
  market_state?: string
  currency: string
  timestamp: string
  source?: string
}

export interface BatchQuotesResponse {
  quotes: MarketQuote[]
  count: number
}

export interface CompanyProfile {
  symbol: string
  name: string
  sector: string | null
  industry: string | null
  market_cap?: number | null
  exchange: string
  currency: string
  source?: string
}

export interface StockHistoryResponse {
  symbol: string
  points: IndexHistoryPoint[]
}

export interface IndexHistoryPoint {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface IndexHistoryResponse {
  symbol: string
  range: string
  points: IndexHistoryPoint[]
}

export interface IndexPerformance {
  symbol: string
  trade_date: string
  close: number
  periods: {
    "1W"?: number | null
    "1M"?: number | null
    "3M"?: number | null
    "6M"?: number | null
    YTD?: number | null
    "1Y"?: number | null
  }
}

export interface SectorRanking {
  rank: number | null
  sector: string
  momentum_score: number | null
  relative_strength: number | null
  ytd_return: number | null
  constituent_count: number | null
  periods: Record<string, number | null>
  rotation_signal: string | null
}

export interface SectorRotation {
  as_of_date: string
  leading: Array<Record<string, unknown>>
  lagging: Array<Record<string, unknown>>
  neutral: Array<Record<string, unknown>>
  rotation_breadth: number
}

export interface BreadthSummary {
  trade_date: string
  advancing: number
  declining: number
  advance_decline_ratio: number | null
  advance_decline_line: number | null
  new_highs: number
  new_lows: number
  advancing_volume: number
  declining_volume: number
  volume_breadth_ratio: number | null
  breadth_oscillator: number | null
  index_strength_score: number | null
}

export interface ADLinePoint {
  trade_date: string
  advance_decline_line: number | null
}

export interface OscillatorPoint {
  trade_date: string
  breadth_oscillator: number | null
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
  volume_breadth_ratio: number | null
}

export interface StoredBreadth {
  id: number
  trade_date: string
  advancing: number
  declining: number
  unchanged: number
  total_stocks: number
  advancing_volume: number
  declining_volume: number
  unchanged_volume: number
  total_volume: number
  new_highs: number
  new_lows: number
  advance_decline_ratio: number | null
  advance_decline_line: number | null
  volume_breadth_ratio: number | null
  breadth_oscillator: number | null
  index_strength_score: number | null
}

export interface PaperAccountSummary {
  account_id: number
  initial_capital: number
  cash_balance: number
  portfolio_value: number
  total_invested: number
  total_realized_pnl: number
  total_unrealized_pnl: number
  total_pnl: number
  total_pnl_pct: number
  positions_count: number
  is_active: boolean
}

export interface PaperPosition {
  symbol: string
  sector: string | null
  quantity: number
  average_price: number
  current_price: number | null
  cost_basis: number
  market_value: number
  realized_pnl: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  allocation_pct: number
}

export interface SectorExposure {
  sector: string
  market_value: number
  positions: number
  allocation_pct: number
}

export interface EquityCurvePoint {
  date: string
  equity: number
  event?: string | null
}

export interface PaperTradeRow {
  id: number
  symbol: string
  side: string
  quantity: number
  price: number
  commission: number
  realized_pnl: number | null
  trade_time: string | null
}

export interface PerformanceReport {
  account: PaperAccountSummary | null
  total_trades: number
  filled_orders: number
  cancelled_orders: number
  winning_trades: number
  losing_trades: number
  win_rate: number
}

export interface PaperAnalytics {
  cagr: number | null
  win_rate: number
  profit_factor: number | null
  sharpe_ratio: number | null
  sortino_ratio: number | null
  max_drawdown: number | null
  max_drawdown_amount: number | null
  expectancy: number | null
  total_trades: number
  winning_trades: number
  losing_trades: number
  breakeven_trades: number
}

export interface StockRecommendation {
  id: number
  symbol: string
  direction: "BUY" | "SELL" | "HOLD"
  signal?: string | null
  confidence: number | null
  price_target: number | null
  current_price: number | null
  timeframe: string | null
  reasoning: string | null
  recommendation_type: string | null
  status: string
  score: number | null
  risk_level: string | null
  predicted_return_pct: number | null
  source: string | null
  metadata_json: string | null
  generated_at: string | null
  expires_at: string | null
}

export interface RecommendationMeta {
  signal: string
  as_of_date: string
  evidence: string[]
  caution: string[]
  returns: Record<string, number | null>
  indicators?: Record<string, unknown>
}

export interface RecommendationsPage {
  items: StockRecommendation[]
  total: number
  limit: number
  offset: number
}

export interface ScanStatus {
  started?: boolean
  reason?: string
  running?: boolean
  last?: {
    universe?: number
    scanned?: number
    stored?: number
    insufficient_data?: number
    failed?: number
    skipped_fresh?: number
    finished_at?: string
  } | null
}
