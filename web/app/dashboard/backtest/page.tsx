"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TestTube, Play, Trash2, RefreshCw, FileText, TrendingUp } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"

interface BacktestSummary {
  id: number
  name: string
  symbol: string
  strategy_type: string
  status: string
  initial_capital: number
  start_date: string | null
  end_date: string | null
  created_at: string | null
}

interface BacktestReport {
  total_return_pct: number
  benchmark_return_pct: number
  alpha_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  total_trades: number
  initial_capital: number
  final_equity: number
}

interface EquityPoint {
  date: string | null
  equity: number
  cash: number
  holdings_value: number
  returns_pct: number
  drawdown_pct: number
}

interface Trade {
  id: number
  trade_number: number
  symbol: string
  side: string
  status: string
  entry_date: string | null
  entry_price: number | null
  exit_date: string | null
  exit_price: number | null
  quantity: number | null
  pnl: number | null
  pnl_pct: number | null
  holding_days: number | null
  exit_reason: string | null
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

const STRATEGY_TYPES = ["sma_crossover", "rsi", "bollinger", "custom"] as const
type StrategyType = (typeof STRATEGY_TYPES)[number]

export default function BacktestPage() {
  const [backtests, setBacktests] = useState<BacktestSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const limit = 20

  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({
    name: "",
    symbol: "",
    start_date: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().split("T")[0],
    end_date: new Date().toISOString().split("T")[0],
    initial_capital: 100000,
    strategy_type: "sma_crossover" as StrategyType,
  })

  const [selectedReport, setSelectedReport] = useState<{
    backtest: BacktestSummary
    report: BacktestReport
    equity: EquityPoint[]
    trades: Trade[]
  } | null>(null)

  const mounted = useRef(true)
  const prefillApplied = useRef(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)

    try {
      const res = await api.get<PaginatedResponse<BacktestSummary>>(
        `/backtests?limit=${limit}&skip=${skip}`,
      )

      if (!mounted.current) return
      setBacktests(res.items ?? [])
      setTotal(res.total ?? 0)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load backtests")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [skip])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (prefillApplied.current) return

    const symbol = new URLSearchParams(window.location.search)
      .get("symbol")
      ?.trim()
      .toUpperCase()

    if (!symbol) return

    prefillApplied.current = true
    setForm((current) => ({
      ...current,
      symbol,
      name: `${symbol} Backtest`,
    }))
    setShowCreate(true)
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    void load(true)
  }

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setCreating(true)

    try {
      const params = new URLSearchParams({
        name: form.name,
        symbol: form.symbol,
        start_date: form.start_date,
        end_date: form.end_date,
        initial_capital: String(form.initial_capital),
        strategy_type: form.strategy_type,
      })

      await api.post(`/backtests?${params.toString()}`)
      setShowCreate(false)
      setForm((current) => ({ ...current, name: "", symbol: "" }))
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create backtest")
    } finally {
      setCreating(false)
    }
  }

  const handleRun = async (backtest: BacktestSummary) => {
    try {
      await api.post(`/backtests/${backtest.id}/run`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run backtest")
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this backtest?")) return

    try {
      await api.delete(`/backtests/${id}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete backtest")
    }
  }

  const handleViewReport = async (backtest: BacktestSummary) => {
    try {
      const [report, equity, trades] = await Promise.all([
        api.get<BacktestReport>(`/backtests/${backtest.id}/report`),
        api.get<EquityPoint[]>(`/backtests/${backtest.id}/equity-curve`),
        api.get<Trade[]>(`/backtests/${backtest.id}/trades`),
      ])

      setSelectedReport({
        backtest,
        report,
        equity: equity ?? [],
        trades: trades ?? [],
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load backtest results")
    }
  }

  const formatDate = (value: string | null) => {
    return value ? new Date(value).toLocaleDateString() : "—"
  }

  const renderEquityCurve = (points: EquityPoint[]) => {
    if (!points.length) {
      return (
        <div className="h-48 flex items-center justify-center text-gray-500">
          No equity data available yet.
        </div>
      )
    }

    const width = 900
    const height = 240
    const pad = 24
    const values = points
      .map((point) => Number(point.equity))
      .filter(Number.isFinite)

    if (!values.length) {
      return (
        <div className="h-48 flex items-center justify-center text-gray-500">
          No valid equity data available.
        </div>
      )
    }

    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1

    const path = points
      .map((point, index) => {
        const x = pad + (index / Math.max(points.length - 1, 1)) * (width - pad * 2)
        const y =
          height -
          pad -
          ((Number(point.equity) - min) / range) * (height - pad * 2)

        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(" ")

    return (
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full min-w-[680px] h-56"
          role="img"
          aria-label="Backtest equity curve"
        >
          <line
            x1={pad}
            y1={height - pad}
            x2={width - pad}
            y2={height - pad}
            stroke="currentColor"
            className="text-white/10"
          />
          <line
            x1={pad}
            y1={pad}
            x2={pad}
            y2={height - pad}
            stroke="currentColor"
            className="text-white/10"
          />
          <path
            d={path}
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            className="text-emerald-400"
          />
        </svg>

        <div className="flex justify-between text-[11px] text-gray-500 px-2">
          <span>{formatDate(points[0]?.date ?? null)}</span>
          <span>Peak {formatCurrency(max)}</span>
          <span>{formatDate(points[points.length - 1]?.date ?? null)}</span>
        </div>
      </div>
    )
  }

  const reportMetrics: Array<[string, string, string]> = selectedReport
    ? [
        [
          "Total Return",
          formatPercent(selectedReport.report.total_return_pct),
          getChangeColor(selectedReport.report.total_return_pct),
        ],
        [
          "Benchmark",
          formatPercent(selectedReport.report.benchmark_return_pct),
          getChangeColor(selectedReport.report.benchmark_return_pct),
        ],
        [
          "Alpha",
          formatPercent(selectedReport.report.alpha_pct),
          getChangeColor(selectedReport.report.alpha_pct),
        ],
        [
          "Sharpe Ratio",
          selectedReport.report.sharpe_ratio.toFixed(2),
          "text-white",
        ],
        [
          "Max Drawdown",
          formatPercent(selectedReport.report.max_drawdown_pct),
          "text-red-400",
        ],
        [
          "Win Rate",
          formatPercent(selectedReport.report.win_rate_pct),
          "text-emerald-400",
        ],
        [
          "Total Trades",
          String(selectedReport.report.total_trades),
          "text-white",
        ],
        [
          "Final Equity",
          formatCurrency(selectedReport.report.final_equity),
          "text-white",
        ],
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtesting</h1>
          <p className="text-gray-500 text-sm mt-1">
            Strategy development, backtesting, and performance analysis
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary text-sm"
          >
            <TestTube size={14} /> New Backtest
          </button>
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-red-500 hover:text-red-300"
          >
            ×
          </button>
        </div>
      )}

      {selectedReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-5xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-xl font-bold text-white">
                  {selectedReport.backtest.name} — Results
                </h2>
                <p className="text-gray-500 text-sm">
                  {selectedReport.backtest.symbol} · {selectedReport.backtest.strategy_type}
                </p>
              </div>
              <button
                onClick={() => setSelectedReport(null)}
                className="text-gray-500 hover:text-white text-xl"
              >
                ×
              </button>
            </div>

            <div className="grid md:grid-cols-4 gap-3 text-sm">
              {reportMetrics.map(([label, value, color]) => (
                <div key={label} className="glass-card p-4">
                  <p className="text-gray-500">{label}</p>
                  <p className={`text-2xl font-bold ${color}`}>{value}</p>
                </div>
              ))}
            </div>

            <div className="glass-card p-4 mt-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp size={16} className="text-emerald-400" />
                <h3 className="font-semibold text-white">Equity Curve</h3>
              </div>
              {renderEquityCurve(selectedReport.equity)}
            </div>

            <div className="glass-card p-4 mt-4">
              <h3 className="font-semibold text-white mb-3">Trade History</h3>

              {selectedReport.trades.length === 0 ? (
                <p className="text-gray-500 text-sm">No trades recorded.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-gray-500">
                        <th className="py-2 text-left">#</th>
                        <th className="py-2 text-left">Side</th>
                        <th className="py-2 text-left">Entry</th>
                        <th className="py-2 text-left">Exit</th>
                        <th className="py-2 text-right">P&amp;L</th>
                        <th className="py-2 text-right">P&amp;L %</th>
                        <th className="py-2 text-right">Days</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedReport.trades.map((trade) => (
                        <tr
                          key={trade.id}
                          className="border-b border-white/5"
                        >
                          <td className="py-2 text-gray-400">{trade.trade_number}</td>
                          <td className="py-2 text-white">{trade.side}</td>
                          <td className="py-2 text-gray-400">{formatDate(trade.entry_date)}</td>
                          <td className="py-2 text-gray-400">{formatDate(trade.exit_date)}</td>
                          <td
                            className={`py-2 text-right ${getChangeColor(trade.pnl ?? 0)}`}
                          >
                            {trade.pnl == null ? "—" : formatCurrency(trade.pnl)}
                          </td>
                          <td
                            className={`py-2 text-right ${getChangeColor(trade.pnl_pct ?? 0)}`}
                          >
                            {trade.pnl_pct == null ? "—" : formatPercent(trade.pnl_pct)}
                          </td>
                          <td className="py-2 text-right text-gray-400">
                            {trade.holding_days ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <button
              onClick={() => setSelectedReport(null)}
              className="btn-secondary w-full mt-4"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-white mb-4">New Backtest</h2>

            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                  className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
                  placeholder="My Strategy"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Symbol (e.g. RELIANCE)
                </label>
                <input
                  value={form.symbol}
                  onChange={(e) =>
                    setForm({ ...form, symbol: e.target.value.toUpperCase() })
                  }
                  required
                  className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
                  placeholder="RELIANCE"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                  <input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">End Date</label>
                  <input
                    type="date"
                    value={form.end_date}
                    onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                    className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Initial Capital</label>
                <input
                  type="number"
                  min="1"
                  value={form.initial_capital}
                  onChange={(e) =>
                    setForm({ ...form, initial_capital: Number(e.target.value) })
                  }
                  className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Strategy</label>
                <select
                  value={form.strategy_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      strategy_type: e.target.value as StrategyType,
                    })
                  }
                  className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"
                >
                  {STRATEGY_TYPES.map((strategy) => (
                    <option key={strategy} value={strategy}>
                      {strategy.replace("_", " ").toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="btn-ghost flex-1"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="btn-primary flex-1"
                >
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="p-8">
            <div className="space-y-3 animate-pulse">
              {[1, 2, 3, 4].map((item) => (
                <div key={item} className="h-16 rounded-lg bg-white/5" />
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30 text-left">
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Name</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Symbol</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Strategy</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Status</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase text-right">Capital</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Period</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Created</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-gray-500">
                        No backtests yet. Create one to get started.
                      </td>
                    </tr>
                  ) : (
                    backtests.map((backtest) => (
                      <tr
                        key={backtest.id}
                        className="border-b border-titan-800/20 hover:bg-white/5"
                      >
                        <td className="py-3 px-4 text-white font-medium">{backtest.name}</td>
                        <td className="py-3 px-4 text-white">{backtest.symbol}</td>
                        <td className="py-3 px-4 text-gray-400">
                          {backtest.strategy_type.replace("_", " ").toUpperCase()}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              backtest.status === "completed"
                                ? "bg-emerald-500/10 text-emerald-400"
                                : backtest.status === "running"
                                  ? "bg-blue-500/10 text-blue-400"
                                  : backtest.status === "failed"
                                    ? "bg-red-500/10 text-red-400"
                                    : "bg-gray-500/10 text-gray-400"
                            }`}
                          >
                            {backtest.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right text-gray-400">
                          {formatCurrency(backtest.initial_capital).replace("₹", "")}
                        </td>
                        <td className="py-3 px-4 text-gray-400 text-xs">
                          {formatDate(backtest.start_date)} – {formatDate(backtest.end_date)}
                        </td>
                        <td className="py-3 px-4 text-gray-500 text-xs">
                          {formatDate(backtest.created_at)}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleRun(backtest)}
                              disabled={backtest.status === "running"}
                              className="btn-ghost text-xs px-2 py-1"
                              title="Run"
                              aria-label={`Run backtest ${backtest.name}`}
                            >
                              <Play size={12} />
                            </button>
                            <button
                              onClick={() => handleViewReport(backtest)}
                              disabled={backtest.status !== "completed"}
                              className="btn-ghost text-xs px-2 py-1"
                              title="View results"
                              aria-label={`View results for ${backtest.name}`}
                            >
                              <FileText size={12} />
                            </button>
                            <button
                              onClick={() => handleDelete(backtest.id)}
                              className="btn-ghost text-xs px-2 py-1 text-red-500 hover:text-red-400"
                              title="Delete"
                              aria-label={`Delete backtest ${backtest.name}`}
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {total > skip + backtests.length && (
              <div className="p-4 border-t border-titan-800/30 text-center">
                <button
                  onClick={() => setSkip((current) => current + limit)}
                  disabled={loading}
                  className="btn-secondary text-sm"
                >
                  Load more
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
