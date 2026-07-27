export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
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
