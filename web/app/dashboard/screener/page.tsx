"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Filter, Save, Search, Target, Trash2 } from "lucide-react"
import Link from "next/link"
import api from "@/lib/api"
import { formatCurrency, getChangeColor } from "@/lib/utils"

type Range = { min?: number; max?: number }

type ScreenerFilters = {
  sector?: string
  exchange?: string
  market_cap?: Range
  technical?: {
    rsi?: Range
    macd?: "bullish" | "bearish"
    sma_cross?: { fast: number; slow: number; type: "golden" | "death" }
    volume_ratio?: number
  }
  fundamental?: { pe_ratio?: Range; roe?: Range }
  as_of_date?: string
}

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
  live_quote?: boolean
  quote_source?: string | null
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

interface RunResult { total: number; skip: number; limit: number; results: ScreenerResult[]; filters_applied: unknown[] }
interface PaginatedResponse<T> { items: T[]; total: number; skip: number; limit: number }
type Quote = { symbol: string; last_price: number | null; volume: number | null; change: number | null; change_percent: number | null; name?: string | null; source?: string | null }
type MarketCap = { symbol: string; market_cap: number | null }

const today = new Date().toISOString().slice(0, 10)
const MARKET_CAP_CR = 10_000_000

export default function ScreenerPage() {
  const [savedScreens, setSavedScreens] = useState<SavedScreen[]>([])
  const [results, setResults] = useState<ScreenerResult[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadingQuotes, setLoadingQuotes] = useState(false)
  const [loadingScreens, setLoadingScreens] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedScreen, setSelectedScreen] = useState<SavedScreen | null>(null)
  const [filters, setFilters] = useState<ScreenerFilters>({ as_of_date: today })
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({ name: "", description: "" })
  const limit = 50
  const mounted = useRef(true)

  const loadScreens = useCallback(async () => {
    setLoadingScreens(true)
    try {
      const res = await api.get<PaginatedResponse<SavedScreen>>("/screener/screens?limit=100")
      if (mounted.current) setSavedScreens(res.items ?? [])
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Failed to load saved screens")
    } finally { if (mounted.current) setLoadingScreens(false) }
  }, [])

  const enrichLiveQuotes = useCallback(async (page: ScreenerResult[]) => {
    if (!mounted.current || !page.length) return
    const symbols = page.map(r => r.symbol).filter(Boolean)
    setLoadingQuotes(true)
    try {
      const res = await api.get<{ quotes: Quote[] }>(`/market-data/quotes?symbols=${encodeURIComponent(symbols.join(","))}`)
      const quoteMap = new Map((res.quotes ?? []).map(q => [q.symbol.replace(/\.(NS|BO)$/i, "").toUpperCase(), q]))
      if (!mounted.current) return
      setResults(current => current.map(row => {
        const q = quoteMap.get(row.symbol.toUpperCase())
        if (!q) return row
        return { ...row, close: q.last_price != null && q.last_price > 0 ? q.last_price : row.close, volume: q.volume != null && q.volume >= 0 ? q.volume : row.volume, live_quote: q.last_price != null, quote_source: q.source ?? "live_market_feed" }
      }))
    } catch { /* retain database values */ }
    finally { if (mounted.current) setLoadingQuotes(false) }
  }, [])

  const enrichMarketCaps = useCallback(async (page: ScreenerResult[]) => {
    if (!mounted.current || !page.length) return
    const symbols = page.map(r => r.symbol).filter(Boolean)
    try {
      const res = await api.get<{ caps: MarketCap[] }>(`/market-data/market-caps?symbols=${encodeURIComponent(symbols.join(","))}`)
      const capMap = new Map((res.caps ?? []).map(c => [c.symbol.toUpperCase(), c.market_cap]))
      if (!mounted.current) return
      setResults(current => current.map(row => {
        const cap = capMap.get(row.symbol.toUpperCase())
        return cap != null && cap > 0 ? { ...row, market_cap: cap } : row
      }))
    } catch { /* retain database values */ }
  }, [])

  const runScreen = useCallback(async (nextFilters: ScreenerFilters, nextSkip = 0) => {
    const isMore = nextSkip > 0
    if (isMore) setLoadingMore(true); else setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: String(limit), skip: String(nextSkip) })
      if (nextFilters.as_of_date) params.set("as_of_date", nextFilters.as_of_date)
      const body: ScreenerFilters = { ...nextFilters }
      delete body.as_of_date
      // UI values are ₹ Crore; database filter values are raw INR.
      if (body.market_cap) {
        body.market_cap = {
          min: body.market_cap.min != null ? body.market_cap.min * MARKET_CAP_CR : undefined,
          max: body.market_cap.max != null ? body.market_cap.max * MARKET_CAP_CR : undefined,
        }
      }
      const res = await api.post<RunResult>(`/screener/run?${params.toString()}`, body)
      if (!mounted.current) return
      const page = res.results ?? []
      setResults(current => nextSkip === 0 ? page : [...current, ...page])
      setTotal(res.total ?? 0)
      setSkip(nextSkip)
      setFilters(nextFilters)
      setSelectedScreen(null)
      void enrichLiveQuotes(page)
      void enrichMarketCaps(page)
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Screen failed")
    } finally {
      if (mounted.current) { setLoading(false); setLoadingMore(false) }
    }
  }, [enrichLiveQuotes, enrichMarketCaps])

  const loadMore = () => {
    if (loading || loadingMore || results.length >= total) return
    void runScreen(filters, results.length)
  }

  const runSavedScreen = async (screen: SavedScreen) => {
    try {
      const saved = JSON.parse(screen.filters_json) as ScreenerFilters
      // Saved screens created before the ₹Cr/raw-INR fix stored raw values;
      // only new UI-created screens should be re-entered through the builder.
      setSelectedScreen(screen)
      await runScreen(saved)
    } catch { setError("Invalid filters in saved screen") }
  }

  const updateTechnical = (patch: ScreenerFilters["technical"]) => setFilters(prev => ({ ...prev, technical: { ...prev.technical, ...patch } }))

  const saveCurrentScreen = async (e: React.FormEvent) => {
    e.preventDefault(); setCreating(true); setError(null)
    try {
      await api.post("/screener/screens", { name: createForm.name, description: createForm.description || null, filters_json: JSON.stringify(filters) })
      setShowCreate(false); setCreateForm({ name: "", description: "" }); await loadScreens()
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to save screen") }
    finally { setCreating(false) }
  }

  const deleteScreen = async (id: number) => {
    if (!confirm("Delete this saved screen?")) return
    try { await api.delete(`/screener/screens/${id}`); await loadScreens(); if (selectedScreen?.id === id) setSelectedScreen(null) }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to delete screen") }
  }

  useEffect(() => { mounted.current = true; void loadScreens(); return () => { mounted.current = false } }, [loadScreens])

  const marketCap = filters.market_cap ?? {}
  const rsi = filters.technical?.rsi ?? {}
  const cross = filters.technical?.sma_cross

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold text-white">Stock Screener</h1><p className="text-gray-500 text-sm mt-1">Build reproducible stock screens and test them historically</p></div><button onClick={() => setShowCreate(true)} className="btn-primary text-sm"><Save size={14} /> Save Screen</button></div>
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300">{error}</div>}

      <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Filter size={16} className="text-titan-400" /> Screen Builder</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="text-xs text-gray-400">Exchange<select value={filters.exchange ?? ""} onChange={e => setFilters(p => ({ ...p, exchange: e.target.value || undefined }))} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"><option value="">All</option><option value="NSE">NSE</option><option value="BSE">BSE</option></select></label>
          <label className="text-xs text-gray-400">Sector<select value={filters.sector ?? ""} onChange={e => setFilters(p => ({ ...p, sector: e.target.value || undefined }))} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"><option value="">All sectors</option><option value="Technology">Technology</option><option value="Financial Services">Financial Services</option><option value="Energy">Energy</option><option value="Healthcare">Healthcare</option><option value="Industrials">Industrials</option><option value="Consumer Cyclical">Consumer Cyclical</option></select></label>
          <label className="text-xs text-gray-400">Market Cap Min (₹ Cr)<input type="number" value={marketCap.min ?? ""} onChange={e => setFilters(p => ({ ...p, market_cap: { ...p.market_cap, min: e.target.value ? Number(e.target.value) : undefined } }))} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /></label>
          <label className="text-xs text-gray-400">Market Cap Max (₹ Cr)<input type="number" value={marketCap.max ?? ""} onChange={e => setFilters(p => ({ ...p, market_cap: { ...p.market_cap, max: e.target.value ? Number(e.target.value) : undefined } }))} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /></label>
          <label className="text-xs text-gray-400">RSI Min<input type="number" min="0" max="100" value={rsi.min ?? ""} onChange={e => updateTechnical({ rsi: { ...rsi, min: e.target.value ? Number(e.target.value) : undefined } })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /></label>
          <label className="text-xs text-gray-400">RSI Max<input type="number" min="0" max="100" value={rsi.max ?? ""} onChange={e => updateTechnical({ rsi: { ...rsi, max: e.target.value ? Number(e.target.value) : undefined } })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /></label>
          <label className="text-xs text-gray-400">MACD<select value={filters.technical?.macd ?? ""} onChange={e => updateTechnical({ macd: (e.target.value || undefined) as "bullish" | "bearish" | undefined })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"><option value="">Any</option><option value="bullish">Bullish</option><option value="bearish">Bearish</option></select></label>
          <label className="text-xs text-gray-400">Volume Ratio Min<input type="number" min="0" step="0.1" value={filters.technical?.volume_ratio ?? ""} onChange={e => updateTechnical({ volume_ratio: e.target.value ? Number(e.target.value) : undefined })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" placeholder="1.5" /></label>
          <label className="text-xs text-gray-400">SMA Cross<select value={cross?.type ?? ""} onChange={e => updateTechnical({ sma_cross: e.target.value ? { fast: cross?.fast ?? 20, slow: cross?.slow ?? 50, type: e.target.value as "golden" | "death" } : undefined })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white"><option value="">None</option><option value="golden">Golden Cross</option><option value="death">Death Cross</option></select></label>
          <label className="text-xs text-gray-400">Fast SMA<input type="number" min="1" value={cross?.fast ?? 20} disabled={!cross} onChange={e => cross && updateTechnical({ sma_cross: { ...cross, fast: Number(e.target.value) } })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white disabled:opacity-40" /></label>
          <label className="text-xs text-gray-400">Slow SMA<input type="number" min="2" value={cross?.slow ?? 50} disabled={!cross} onChange={e => cross && updateTechnical({ sma_cross: { ...cross, slow: Number(e.target.value) } })} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white disabled:opacity-40" /></label>
          <label className="text-xs text-gray-400">Historical As-Of Date<input type="date" value={filters.as_of_date ?? today} onChange={e => setFilters(p => ({ ...p, as_of_date: e.target.value }))} className="mt-1 w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /></label>
        </div>
        <div className="flex justify-end mt-5"><button onClick={() => void runScreen(filters)} disabled={loading || loadingMore} className="btn-primary text-sm"><Search size={14} /> {loading ? "Screening..." : "Run Screener"}</button></div>
      </div>

      <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Target size={16} className="text-titan-400" /> Saved Screens</h3>
        {loadingScreens ? <p className="text-gray-500">Loading...</p> : savedScreens.length === 0 ? <p className="text-gray-500">No saved screens yet.</p> : <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">{savedScreens.map(screen => <div key={screen.id} className={`glass-card p-4 ${selectedScreen?.id === screen.id ? "border-titan-500" : ""}`}><button className="text-left w-full" onClick={() => void runSavedScreen(screen)}><div className="flex justify-between"><span className="text-white font-medium">{screen.name}</span><span className="text-xs text-gray-500">{screen.last_results_count ?? 0}</span></div><p className="text-xs text-gray-500 mt-1">{screen.description || "No description"}</p></button><button onClick={() => void deleteScreen(screen.id)} className="mt-3 text-xs text-red-400 hover:text-red-300 flex items-center gap-1"><Trash2 size={12} /> Delete</button></div>)}</div>}
      </div>

      <div className="glass-card overflow-hidden"><div className="px-5 py-3 border-b border-titan-800/30 flex items-center justify-between"><h3 className="text-sm font-semibold text-white">Results</h3><span className="text-xs text-gray-500">{results.length} of {total} matches</span></div>
        {results.length === 0 && !loading ? <div className="p-10 text-center text-gray-500">Set your filters and run the screener.</div> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-titan-800/30">{["Symbol", "Price", "1M Change", "Volume", "Sector", "Market Cap (Cr)", "Action"].map(h => <th key={h} className="text-right first:text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase">{h}</th>)}</tr></thead><tbody>{results.map(stock => <tr key={stock.symbol} className="border-b border-titan-800/20 hover:bg-white/5"><td className="py-3 px-4"><Link href={`/dashboard/stocks/${stock.symbol}`} className="text-white font-medium hover:text-titan-400">{stock.symbol}</Link><div className="text-[10px] text-gray-500">{stock.company_name}</div></td><td className="py-3 px-4 text-right text-white">{stock.close != null ? formatCurrency(stock.close) : <span className="text-gray-600">Loading…</span>}</td><td className={`py-3 px-4 text-right font-medium ${getChangeColor(stock.change_1m_pct ?? 0)}`}>{stock.change_1m_pct != null ? `${stock.change_1m_pct >= 0 ? "+" : ""}${stock.change_1m_pct.toFixed(2)}%` : "—"}</td><td className="py-3 px-4 text-right text-gray-400">{stock.volume != null ? stock.volume.toLocaleString("en-IN") : <span className="text-gray-600">Loading…</span>}</td><td className="py-3 px-4 text-right text-gray-400">{stock.sector || "—"}</td><td className="py-3 px-4 text-right text-gray-400">{stock.market_cap != null && stock.market_cap > 0 ? `₹${(stock.market_cap / MARKET_CAP_CR).toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr` : <span className="text-gray-600">Loading…</span>}</td><td className="py-3 px-4 text-right"><Link href={`/dashboard/backtest?symbol=${encodeURIComponent(stock.symbol)}`} className="btn-secondary text-xs inline-flex">Backtest</Link></td></tr>)}</tbody></table></div>}
        {total > results.length && <div className="p-4 border-t border-titan-800/30 text-center"><button onClick={loadMore} disabled={loading || loadingMore} className="btn-secondary text-sm min-w-32">{loadingMore ? "Loading more…" : `Load more (${Math.min(limit, total - results.length)} stocks)`}</button>{loadingQuotes && <div className="text-[11px] text-gray-600 mt-2">Updating live prices and volume…</div>}</div>}
        {total > 0 && results.length >= total && loadingQuotes && <div className="p-3 text-center text-[11px] text-gray-600">Updating live prices and volume…</div>}
      </div>

      {showCreate && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><div className="bg-titan-900 rounded-xl p-6 w-full max-w-md"><h2 className="text-xl font-bold text-white mb-4">Save Current Screen</h2><form onSubmit={saveCurrentScreen} className="space-y-4"><input required value={createForm.name} onChange={e => setCreateForm(p => ({ ...p, name: e.target.value }))} placeholder="Screen name" className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /><textarea value={createForm.description} onChange={e => setCreateForm(p => ({ ...p, description: e.target.value }))} placeholder="Description" rows={3} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white" /><div className="text-xs text-gray-500 font-mono break-all">{JSON.stringify(filters)}</div><div className="flex gap-2"><button type="button" onClick={() => setShowCreate(false)} className="btn-ghost flex-1">Cancel</button><button type="submit" disabled={creating} className="btn-primary flex-1">{creating ? "Saving..." : "Save"}</button></div></form></div></div>}
    </div>
  )
}
