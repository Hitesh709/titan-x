"use client"

import { useCallback, useEffect, useState } from "react"
import {
  TrendingUp, DollarSign, Activity,
  BarChart3, ArrowUpRight, ArrowDownRight,
  LineChart, RefreshCw,
} from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import {
  formatCurrency, formatPercent, formatCompactNumber,
  getChangeColor,
} from "@/lib/utils"
import TopPickWidget from "@/components/TopPickWidget"

interface DashboardPortfolio {
  has_account: boolean
  account_id?: number
  cash_balance?: number
  positions_value?: number
  total_equity?: number
  unrealized_pnl?: number
  total_return?: number
  total_return_pct?: number
  positions_count?: number
}

interface DashboardPerformance {
  has_data: boolean
  win_rate?: number
  total_trades?: number
  profit_factor?: number
  sharpe_ratio?: number
  max_drawdown?: number
}

interface AlertItem {
  id: number
  symbol: string
  event_type: string
  severity: string
  title: string | null
  message: string
  is_read: boolean
  triggered_at: string | null
}

interface DashboardData {
  portfolio: DashboardPortfolio
  performance: DashboardPerformance
  alerts: AlertItem[]
  ai_picks: unknown[]
  watchlists: unknown[]
  news: unknown[]
}

interface IndexItem {
  symbol: string
  name: string
  close: number
  change: number
  change_pct: number
  volume: number
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—"
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} hr ago`
  return `${Math.floor(hrs / 24)} d ago`
}

function severityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "positive":
      return "bg-emerald-500"
    case "negative":
      return "bg-red-500"
    case "warning":
    case "critical":
      return "bg-yellow-500"
    default:
      return "bg-titan-500"
  }
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [indices, setIndices] = useState<IndexItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [dash, idx] = await Promise.allSettled([
      api.get<DashboardData>("/dashboard"),
      api.get<{ items: IndexItem[] }>("/indices"),
    ])
    if (dash.status === "fulfilled") {
      setDashboard(dash.value)
      setError(null)
    } else {
      setError(dash.reason instanceof Error ? dash.reason.message : "Failed to load dashboard")
    }
    if (idx.status === "fulfilled") {
      setIndices(idx.value.items || [])
    }
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useLiveRefresh(() => {
    load()
  }, [])

  const refresh = () => {
    setRefreshing(true)
    load()
  }

  const portfolio = dashboard?.portfolio
  const performance = dashboard?.performance
  const alerts = dashboard?.alerts || []

  const equity = portfolio?.total_equity || 0
  const cash = portfolio?.cash_balance || 0
  const positionsValue = portfolio?.positions_value || 0
  const cashPct = equity > 0 ? (cash / equity) * 100 : 0
  const positionsPct = equity > 0 ? (positionsValue / equity) * 100 : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Real-time portfolio and market overview</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-titan-400 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="glass-card p-4 flex items-center justify-between gap-4 border border-red-500/30">
          <span className="text-sm text-red-400">Failed to load live data: {error}</span>
          <button
            type="button"
            onClick={refresh}
            className="text-xs badge-blue px-3 py-1"
          >
            Retry
          </button>
        </div>
      )}

      {/* Portfolio Value Card */}
      <div className="glass-card p-6">
        {loading && !portfolio ? (
          <div className="h-32 animate-pulse bg-white/5 rounded-lg" />
        ) : !portfolio?.has_account ? (
          <div className="py-6 text-center">
            <p className="text-sm text-gray-400">No paper account yet.</p>
            <p className="text-xs text-gray-600 mt-1">
              Open a paper account to start tracking your live portfolio here.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between mb-4">
              <div>
                <p className="text-sm text-gray-400">Total Portfolio Value</p>
                <h2 className="text-3xl font-bold text-white mt-1">{formatCurrency(equity)}</h2>
                <div className="flex items-center gap-3 mt-2">
                  <span className={`flex items-center gap-1 text-sm font-medium ${getChangeColor(portfolio?.total_return || 0)}`}>
                    {(portfolio?.total_return ?? 0) >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                    {formatCurrency(portfolio?.total_return || 0)} ({formatPercent(portfolio?.total_return_pct || 0)})
                  </span>
                  <span className="text-gray-600">total return</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-gray-400">Unrealized P&L</p>
                <p className={`text-lg font-semibold ${getChangeColor(portfolio?.unrealized_pnl || 0)}`}>
                  {formatCurrency(portfolio?.unrealized_pnl || 0)}
                </p>
              </div>
            </div>

            {/* Allocation */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Asset Allocation</span>
                <span className="text-gray-500">Weight</span>
              </div>
              <div className="flex h-2 rounded-full overflow-hidden bg-white/5">
                <div className="bg-titan-500" style={{ width: `${cashPct}%` }} title={`Cash: ${cashPct.toFixed(1)}%`} />
                <div className="bg-emerald-500" style={{ width: `${positionsPct}%` }} title={`Positions: ${positionsPct.toFixed(1)}%`} />
              </div>
              <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-1">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-titan-500" />
                  Cash {cashPct.toFixed(1)}%
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  Positions {positionsPct.toFixed(1)}%
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {
            icon: DollarSign,
            label: "Cash Balance",
            value: portfolio?.has_account ? formatCurrency(cash) : "—",
            change: null,
            positive: null as boolean | null,
          },
          {
            icon: Activity,
            label: "Open Positions",
            value: portfolio?.has_account ? `${portfolio.positions_count ?? 0}` : "—",
            change: null,
            positive: null as boolean | null,
          },
          {
            icon: TrendingUp,
            label: "Unrealized P&L",
            value: portfolio?.has_account ? formatCurrency(portfolio.unrealized_pnl || 0) : "—",
            change: portfolio?.has_account ? formatPercent(portfolio.total_return_pct || 0) : null,
            positive: (portfolio?.unrealized_pnl ?? 0) >= 0,
          },
          {
            icon: BarChart3,
            label: "Win Rate",
            value: performance?.has_data && performance.win_rate != null ? `${performance.win_rate.toFixed(1)}%` : "—",
            change: performance?.has_data ? `${performance.total_trades ?? 0} trades` : "no data",
            positive: null as boolean | null,
          },
        ].map((stat) => (
          <div key={stat.label} className="glass-card p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-gray-500">{stat.label}</span>
              <stat.icon size={16} className="text-titan-400" />
            </div>
            <div className="text-xl font-bold text-white">{loading && !dashboard ? "" : stat.value}</div>
            {stat.change && (
              <div className={`text-xs mt-1 ${stat.positive === true ? "text-emerald-400" : stat.positive === false ? "text-red-400" : "text-gray-500"}`}>
                {stat.change}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Market Indices + Top Movers */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Market Indices */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <LineChart size={16} className="text-titan-400" /> Market Indices
          </h3>
          {loading && indices.length === 0 ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-8 animate-pulse bg-white/5 rounded-lg" />
              ))}
            </div>
          ) : indices.length === 0 ? (
            <p className="text-sm text-gray-500">No market index data available yet.</p>
          ) : (
            <div className="space-y-3">
              {indices.map((index) => (
                <div key={index.symbol} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                  <div>
                    <div className="text-sm font-medium text-white">{index.symbol}</div>
                    <div className="text-xs text-gray-500">Vol: {formatCompactNumber(index.volume)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-white">{index.close.toLocaleString()}</div>
                    <div className={`text-xs font-medium ${getChangeColor(index.change)}`}>
                      {index.change >= 0 ? "+" : ""}{index.change_pct.toFixed(2)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top Picks */}
        <TopPickWidget />
      </div>

      {/* Alerts */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Activity size={16} className="text-titan-400" /> Recent Activity
        </h3>
        {loading && alerts.length === 0 ? (
          <div className="space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse bg-white/5 rounded-lg" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <p className="text-sm text-gray-500">No recent alerts. Add symbols to a watchlist to receive alerts.</p>
        ) : (
          <div className="space-y-3">
            {alerts.slice(0, 8).map((alert) => (
              <div key={alert.id} className="flex items-start gap-3 py-2 border-b border-titan-800/20 last:border-0">
                <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${severityColor(alert.severity)}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{alert.symbol}</span>
                    <span className="badge-blue text-[10px]">{alert.event_type}</span>
                    {!alert.is_read && <span className="text-[10px] text-titan-400">NEW</span>}
                  </div>
                  <p className="text-sm text-gray-400 mt-0.5">{alert.title || alert.message}</p>
                </div>
                <span className="text-xs text-gray-600 shrink-0">{timeAgo(alert.triggered_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
