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
