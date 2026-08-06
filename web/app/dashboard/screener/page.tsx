"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Target, Filter, Search, Save, TrendingUp, TrendingDown, Settings, Play, Trash2, RefreshCw, ChevronDown } from "lucide-react"
import Link from "next/link"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"

interface ScreenerResult {
  symbol: string
  company_name: string | null
  sector: string | null
  industry: string | null
  exchange: string | null
  market_cap: number | null
  close: number | null
  volume: number | null
  change_1m_pct: number | null
}

interface SavedScreen {
  id: number
  name: string
  description: string | null
  filters_json: string
  last_run_at: string | null
  last_results_count: number | null
  created_at: string
  updated_at: string
}

interface RunResult {
  total: number
  skip: number
  limit: number
  results: ScreenerResult[]
  filters_applied: string[][]
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export default function ScreenerPage() {
  const [savedScreens, setSavedScreens] = useState<SavedScreen[]>([])
  const [runResults, setRunResults] = useState<ScreenerResult[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [totalResults, setTotalResults] = useState(0)
  const [skip, setSkip] = useState(0)
  const limit = 50

  const [selectedScreen, setSelectedScreen] = useState<SavedScreen | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({ name: "", description: "", filters_json: "{}" })
  const [currentFilters, setCurrentFilters] = useState({})

  const mounted = useRef(true)

  const loadScreens = useCallback(async () => {
    try {
      const res = await api.get<PaginatedResponse<SavedScreen>>("/screener/screens?limit=100")
      if (!mounted.current) return
      setSavedScreens(res.items ?? [])
    } catch (e) {
      if (!mounted.current) return
      console.error("Failed to load saved screens:", e)
    }
  }, [])

  const runScreen = useCallback(async (filters: Record<string, unknown>, screenId?: number) => {
    setRunning(true)
    setError(null)
    try {
      const endpoint = screenId ? `/screener/screens/${screenId}/run?limit=${limit}` : `/screener/run?limit=${limit}`
      const res = await api.post<RunResult>(endpoint, filters)
      if (!mounted.current) return
      setRunResults(res.results ?? [])
      setTotalResults(res.total ?? 0)
      setSkip(0)
      setCurrentFilters(filters)
      if (screenId) {
        void loadScreens()
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Screen failed")
    } finally {
      if (mounted.current) setRunning(false)
    }
  }, [])

  const handleAdhocRun = (filters: Record<string, unknown>) => {
    runScreen(filters)
    setSelectedScreen(null)
  }

  const handleSavedRun = (screen: SavedScreen) => {
    try {
      const filters = JSON.parse(screen.filters_json)
      runScreen(filters, screen.id)
      setSelectedScreen(screen)
    } catch {
      setError("Invalid filters in saved screen")
    }
  }

  const handleCreateScreen = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.post("/screener/screens", {
        name: createForm.name,
        description: createForm.description,
        filters_json: createForm.filters_json,
      })
      setShowCreate(false)
      setCreateForm({ name: "", description: "", filters_json: "{}" })
      void loadScreens()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save screen")
    } finally {
      setCreating(false)
    }
  }

  const handleDeleteScreen = async (id: number) => {
    if (!confirm("Delete this saved screen?")) return
    try {
      await api.delete(`/screener/screens/${id}`)
      void loadScreens()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete screen")
    }
  }

  useEffect(() => {
    mounted.current = true
    loadScreens()
    return () => { mounted.current = false }
  }, [loadScreens])

  useLiveRefresh(() => { if (selectedScreen) handleSavedRun(selectedScreen) }, [selectedScreen])

  const formatDate = (s: string | null) => s ? new Date(s).toLocaleString() : "—"
  const formatMarketCap = (v: number | null) => v ? formatCurrency(v).replace("₹", "") : "—"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Stock Screener</h1>
          <p className="text-gray-500 text-sm mt-1">Screen thousands of stocks using custom criteria</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
            <Save size={14} /> Save Screen
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300">×</button>
        </div>
      )}

      {/* Saved Screeners */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Target size={16} className="text-titan-400" /> Saved Screens
        </h3>
        {savedScreens.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No saved screens yet. Create one to save your filters.</p>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {savedScreens.map((s) => (
              <div key={s.id} className="glass-card p-4 hover:border-titan-600/40 cursor-pointer transition-all"
                onClick={() => handleSavedRun(s)}>
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-medium text-white">{s.name}</h3>
                  <span className="text-xs text-gray-500">{s.last_results_count ?? 0} results</span>
                </div>
                <p className="text-xs text-gray-500 line-clamp-2">{s.description || "No description"}</p>
                <div className="text-[10px] text-gray-600 mt-2">Last run: {formatDate(s.last_run_at)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Filter Builder */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Filter size={16} className="text-titan-400" /> Quick Filters
        </h3>
        <div className="flex flex-wrap gap-3">
          {[
            { key: "sector", label: "Sector", options: ["Technology", "Financial Services", "Energy", "Consumer Cyclical", "Healthcare", "Industrials"] },
            { key: "market_cap_min", label: "Min Market Cap (Cr)", type: "number", placeholder: "1000" },
            { key: "technical_rsi_min", label: "Min RSI (14)", type: "number", placeholder: "60" },
            { key: "liquidity_volume_min", label: "Min Volume", type: "number", placeholder: "1000000" },
          ].map((f) => (
            <div key={f.key} className="flex items-center gap-2 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm">
              {f.options ? (
                <select
                  value={(currentFilters as Record<string, unknown>)[f.key] as string || ""}
                  onChange={e => setCurrentFilters(prev => ({ ...prev, [f.key]: e.target.value || undefined }))}
                  className="flex-1 bg-titan-800 border border-white/10 rounded-lg px-2 py-1 text-white text-sm"
                >
                  <option value="">All {f.label}</option>
                  {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={f.type || "text"}
                  placeholder={f.placeholder}
                  value={((currentFilters as Record<string, unknown>)[f.key] as string) || ""}
                  onChange={e => setCurrentFilters(prev => ({ ...prev, [f.key]: e.target.value || undefined }))}
                  className="flex-1 bg-titan-800 border border-white/10 rounded-lg px-2 py-1 text-white text-sm placeholder-gray-500"
                />
              )}
            </div>
          ))}
          <button onClick={() => handleAdhocRun(currentFilters)} disabled={running} className="btn-primary text-sm">
            <Search size={14} /> {running ? "Screening..." : "Run Screen"}
          </button>
        </div>
      </div>

      {/* Results */}
      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-titan-800/30 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Results</h3>
          <span className="text-xs text-gray-500">{runResults.length} of {totalResults} matches</span>
        </div>
        {loading && runResults.length === 0 ? (
          <div className="p-8"><div className="space-y-3 animate-pulse">{[1,2,3,4].map(i => <div key={i} className="h-10 rounded-lg bg-white/5" />)}</div></div>
        ) : runResults.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Run a screen to see results</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-titan-800/30">
                  <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase">Symbol</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Price</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">1M Change</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Volume</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Sector</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Market Cap (Cr)</th>
                </tr>
              </thead>
              <tbody>
                {runResults.map((s) => (
                  <tr key={s.symbol} className="border-b border-titan-800/20 hover:bg-white/5">
                    <td className="py-3 px-4">
                      <Link href={`/dashboard/stocks/${s.symbol}`} className="text-white font-medium hover:text-titan-400">{s.symbol}</Link>
                      <div className="text-[10px] text-gray-500">{s.company_name}</div>
                    </td>
                    <td className="py-3 px-4 text-right text-white">{s.close ? formatCurrency(s.close).replace("₹", "") : "—"}</td>
                    <td className={`py-3 px-4 text-right font-medium ${getChangeColor(s.change_1m_pct ?? 0)}`}>
                      {s.change_1m_pct !== null ? (s.change_1m_pct >= 0 ? "+" : "") + s.change_1m_pct.toFixed(2) + "%" : "—"}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-400">{s.volume ? s.volume.toLocaleString() : "—"}</td>
                    <td className="py-3 px-4 text-right text-gray-400">{s.sector || "—"}</td>
                    <td className="py-3 px-4 text-right text-gray-400">{formatMarketCap(s.market_cap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalResults > skip + runResults.length && (
          <div className="p-4 border-t border-titan-800/30 text-center">
            <button onClick={() => setSkip(s => s + limit)} disabled={loading} className="btn-secondary text-sm">Load more</button>
          </div>
        )}
      </div>

      {/* Create Screen Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-md max-h-[80vh] overflow-y-auto">
            <h2 className="text-xl font-bold text-white mb-4">Save Screen</h2>
            <form onSubmit={handleCreateScreen} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Name</label>
                <input value={createForm.name} onChange={e => setCreateForm({...createForm, name: e.target.value})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="My Screen" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Description</label>
                <textarea value={createForm.description} onChange={e => setCreateForm({...createForm, description: e.target.value})} rows={2} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="Optional description" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Filters (JSON)</label>
                <textarea value={createForm.filters_json} onChange={e => setCreateForm({...createForm, filters_json: e.target.value})} rows={6} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white font-mono text-sm placeholder-gray-500" placeholder='{"sector": "Technology", "market_cap_min": 1000}' />
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary flex-1">{creating ? "Saving..." : "Save Screen"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
