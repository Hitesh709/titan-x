"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TestTube, TrendingUp, TrendingDown, Calendar, Play, Settings2, Trash2, RefreshCw, FileText } from "lucide-react"
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

  const [selectedReport, setSelectedReport] = useState<{ backtest: BacktestSummary; report: BacktestReport } | null>(null)

  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<PaginatedResponse<BacktestSummary>>(
        `/backtests?limit=${limit}&skip=${skip}`
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
    return () => { mounted.current = false }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => { setRefreshing(true); void load(true) }

  const handleCreate = async (e: React.FormEvent) => {
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
      setForm({ ...form, name: "", symbol: "" })
      void load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create backtest")
    } finally {
      setCreating(false)
    }
  }

  const handleRun = async (backtest: BacktestSummary) => {
    try {
      await api.post(`/backtests/${backtest.id}/run`)
      void load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run backtest")
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this backtest?")) return
    try {
      await api.delete(`/backtests/${id}`)
      void load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete backtest")
    }
  }

  const handleViewReport = async (backtest: BacktestSummary) => {
    try {
      const report = await api.get<BacktestReport>(`/backtests/${backtest.id}/report`)
      setSelectedReport({ backtest, report })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load report")
    }
  }

  const formatDate = (s: string | null) => s ? new Date(s).toLocaleDateString() : "—"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtesting</h1>
          <p className="text-gray-500 text-sm mt-1">Strategy development, backtesting, and performance analysis</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
            <TestTube size={14} /> New Backtest
          </button>
          <button onClick={handleRefresh} className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors">
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300">×</button>
        </div>
      )}

      {selectedReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">{selectedReport.backtest.name} — Report</h2>
              <button onClick={() => setSelectedReport(null)} className="text-gray-500 hover:text-white">×</button>
            </div>
            <div className="grid md:grid-cols-3 gap-4 text-sm">
              <div className="glass-card p-4">
                <p className="text-gray-500">Total Return</p>
                <p className={`text-2xl font-bold ${getChangeColor(selectedReport.report.total_return_pct)}`}>
                  {formatPercent(selectedReport.report.total_return_pct)}
                </p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Benchmark</p>
                <p className={`text-2xl font-bold ${getChangeColor(selectedReport.report.benchmark_return_pct)}`}>
                  {formatPercent(selectedReport.report.benchmark_return_pct)}
                </p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Alpha</p>
                <p className={`text-2xl font-bold ${getChangeColor(selectedReport.report.alpha_pct)}`}>
                  {formatPercent(selectedReport.report.alpha_pct)}
                </p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Sharpe Ratio</p>
                <p className="text-2xl font-bold text-white">{selectedReport.report.sharpe_ratio.toFixed(2)}</p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Max Drawdown</p>
                <p className="text-2xl font-bold text-red-400">{formatPercent(selectedReport.report.max_drawdown_pct)}</p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Win Rate</p>
                <p className="text-2xl font-bold text-emerald-400">{formatPercent(selectedReport.report.win_rate_pct)}</p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Total Trades</p>
                <p className="text-2xl font-bold text-white">{selectedReport.report.total_trades}</p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Initial Capital</p>
                <p className="text-2xl font-bold text-white">{formatCurrency(selectedReport.report.initial_capital)}</p>
              </div>
              <div className="glass-card p-4">
                <p className="text-gray-500">Final Equity</p>
                <p className="text-2xl font-bold text-white">{formatCurrency(selectedReport.report.final_equity)}</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-titan-800/30">
              <button onClick={() => setSelectedReport(null)} className="btn-secondary w-full">Close</button>
            </div>
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
                <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="My Strategy" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Symbol (e.g. RELIANCE)</label>
                <input value={form.symbol} onChange={e => setForm({...form, symbol: e.target.value.toUpperCase()})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="RELIANCE" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                  <input type="date" value={form.start_date} onChange={e => setForm({...form, start_date: e.target.value})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">End Date</label>
                  <input type="date" value={form.end_date} onChange={e => setForm({...form, end_date: e.target.value})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Initial Capital</label>
                <input type="number" value={form.initial_capital} onChange={e => setForm({...form, initial_capital: Number(e.target.value)})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Strategy</label>
                <select value={form.strategy_type} onChange={e => setForm({...form, strategy_type: e.target.value as StrategyType})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                  {STRATEGY_TYPES.map(s => <option key={s} value={s}>{s.replace("_", " ").toUpperCase()}</option>)}
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary flex-1">{creating ? "Creating..." : "Create"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="p-8">
            <div className="space-y-3 animate-pulse">
              {[1,2,3,4].map(i => <div key={i} className="h-16 rounded-lg bg-white/5" />)}
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
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Capital</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Period</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Created</th>
                    <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-gray-500">No backtests yet. Create one to get started.</td>
                    </tr>
                  ) : (
                    backtests.map(b => (
                      <tr key={b.id} className="border-b border-titan-800/20 hover:bg-white/5">
                        <td className="py-3 px-4 text-white font-medium">{b.name}</td>
                        <td className="py-3 px-4 text-white">{b.symbol}</td>
                        <td className="py-3 px-4 text-gray-400">{b.strategy_type.replace("_", " ").toUpperCase()}</td>
                        <td className="py-3 px-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            b.status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                            b.status === "running" ? "bg-blue-500/10 text-blue-400" :
                            b.status === "failed" ? "bg-red-500/10 text-red-400" :
                            "bg-gray-500/10 text-gray-400"
                          }`}>{b.status}</span>
                        </td>
                        <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(b.initial_capital).replace("₹", "")}</td>
                        <td className="py-3 px-4 text-gray-400 text-xs">
                          {formatDate(b.start_date)} – {formatDate(b.end_date)}
                        </td>
                        <td className="py-3 px-4 text-gray-500 text-xs">{formatDate(b.created_at)}</td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1">
                            <button onClick={() => handleRun(b)} disabled={b.status === "running"} className="btn-ghost text-xs px-2 py-1" title="Run"><Play size={12} /></button>
                            <button onClick={() => handleViewReport(b)} className="btn-ghost text-xs px-2 py-1" title="View Report"><FileText size={12} /></button>
                            <button onClick={() => handleDelete(b.id)} className="btn-ghost text-xs px-2 py-1 text-red-500 hover:text-red-400" title="Delete"><Trash2 size={12} /></button>
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
                <button onClick={() => setSkip(s => s + limit)} disabled={loading} className="btn-secondary text-sm">Load more</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
