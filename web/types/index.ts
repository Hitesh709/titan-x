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
  access_token?: string
  refresh_token?: string
  token_type: string
  mfa_required?: boolean
  mfa_challenge?: string | null
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
