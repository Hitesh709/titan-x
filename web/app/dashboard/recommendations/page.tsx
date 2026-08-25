"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { RefreshCw, Search, Play, Zap, TrendingUp, TrendingDown, Minus, ArrowUp, ArrowDown, Brain } from "lucide-react"
import api from "@/lib/api"
import type { StockRecommendation } from "@/types"
import { WidgetError, RefreshButton } from "@/components/dashboard/widget"
import { StatCard, RecommendationCard } from "./components"
import { SymbolAnalyzer } from "./analyzer"
import { IntradayRecommendations } from "./intraday"

type SortKey = "technical" | "risk" | "confidence" | "return" | "symbol"
type SortDir = "asc" | "desc"
type StrictDeliveryResponse = { recommendations: StockRecommendation[]; strict_technical_threshold?: number; strict_gate?: string; scanning?: boolean; scan_status?: { scanned?: number; universe_size?: number; progress_pct?: number; error?: string | null } }

const DELIVERY_CACHE_KEY = "titanx.strict.delivery.equity.v2"
const riskRank = (risk?: string | null) => risk === "Low" ? 1 : risk === "Medium" ? 2 : risk === "High" ? 3 : 0

export default function RecommendationsPage() {
  const [recommendations, setRecommendations] = useState<StockRecommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("technical")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [scanInfo, setScanInfo] = useState<string | null>(null)
  const [mode, setMode] = useState<"delivery" | "intraday">("delivery")
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<StrictDeliveryResponse>("/recommendations/strict?mode=delivery&segment=equity&limit=100")
      if (!mounted.current) return
      if ((res.recommendations ?? []).length > 0 || !res.scanning) {
        setRecommendations(res.recommendations ?? [])
        if ((res.recommendations ?? []).length > 0) localStorage.setItem(DELIVERY_CACHE_KEY, JSON.stringify(res.recommendations))
        else localStorage.removeItem(DELIVERY_CACHE_KEY)
      }
      setError(res.scan_status?.error ?? null)
      if (res.scanning) {
        setScanInfo(`Full-market delivery scan running: ${res.scan_status?.scanned ?? 0} / ${res.scan_status?.universe_size ?? 0} symbols (${Math.round(res.scan_status?.progress_pct ?? 0)}%).`)
        window.setTimeout(() => void load(true), 5000)
      } else if (res.scan_status?.error) {
        setScanInfo(`Scan stopped: ${res.scan_status.error}`)
      } else if (res.recommendations?.length) {
        setScanInfo(`Full-market delivery scan complete: ${res.recommendations.length} stock(s) with Delivery Technical Pillar ≥95.`)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load delivery recommendations")
    } finally {
      if (mounted.current) { setLoading(false); setRefreshing(false) }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    try {
      const cached = localStorage.getItem(DELIVERY_CACHE_KEY)
      if (cached) {
        const parsed = JSON.parse(cached) as StockRecommendation[]
        if (Array.isArray(parsed) && parsed.length) { setRecommendations(parsed); setLoading(false); setScanInfo("Showing saved Delivery recommendations. Run Scan when you want fresh results.") }
      }
    } catch { /* ignore malformed browser cache */ }
    // Do not scan or query the API automatically. Saved recommendations remain available locally; scanning is user-triggered.
    return () => { mounted.current = false }
  }, [load])

  const handleScan = async () => {
    setScanning(true); setError(null); setScanInfo("No automatic scan. Run a delivery scan when you want fresh recommendations.")
    try { await api.post("/recommendations/scan?sync=false&limit=3000", {}); await load(true) }
    catch (e) { setError(e instanceof Error ? e.message : "Scan failed") }
    finally { setScanning(false) }
  }

  const handleRefresh = () => { setRefreshing(true); void load(true) }
  const toggleSort = (key: SortKey) => { if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc"); else { setSortKey(key); setSortDir("desc") } }

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase()
    const list = q ? recommendations.filter((r) => r.symbol.toUpperCase().includes(q)) : recommendations
    return [...list].sort((a, b) => {
      let av: number | string; let bv: number | string
      if (sortKey === "symbol") { av = a.symbol; bv = b.symbol }
      else if (sortKey === "return") { av = a.predicted_return_pct ?? -Infinity; bv = b.predicted_return_pct ?? -Infinity }
      else if (sortKey === "confidence") { av = a.confidence ?? 0; bv = b.confidence ?? 0 }
      else if (sortKey === "risk") { av = riskRank(a.risk_level); bv = riskRank(b.risk_level) }
      else {
        const score = (r: StockRecommendation) => { const x = r as StockRecommendation & { technical_pillar_score?: number; technical_score?: number }; return x.technical_pillar_score ?? x.technical_score ?? 0 }
        av = score(a); bv = score(b)
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return a.symbol.localeCompare(b.symbol)
    })
  }, [recommendations, query, sortKey, sortDir])

  const buyCount = recommendations.filter((r) => r.direction === "BUY").length
  const sellCount = recommendations.filter((r) => r.direction === "SELL").length
  const neutralCount = recommendations.length - buyCount - sellCount
  const avgConfidence = recommendations.length === 0 ? 0 : Math.round(recommendations.reduce((s, r) => s + (r.confidence ?? 0), 0) / recommendations.length)

  const sortButton = (key: SortKey, label: string) => <button onClick={() => toggleSort(key)} className={`px-2 py-1 rounded border ${sortKey === key ? "border-titan-500 text-titan-300" : "border-white/10 text-gray-400"}`}>{label} {sortKey === key ? (sortDir === "asc" ? <ArrowUp size={11} className="inline" /> : <ArrowDown size={11} className="inline" />) : null}</button>

  return <div className="space-y-6">
    <div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold text-white">Recommendations</h1><p className="text-gray-500 text-sm mt-1">Titan X recommendations — Delivery and Intraday use separate Technical Pillar gates.</p></div>{mode === "delivery" && <div className="flex items-center gap-2"><button onClick={handleScan} disabled={scanning} className="btn-secondary text-sm inline-flex items-center gap-2 disabled:opacity-50">{scanning ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}{scanning ? "Scanning…" : "Run Scan"}</button><RefreshButton onClick={handleRefresh} spinning={refreshing} /></div>}</div>
    <div className="glass-card p-2 flex gap-2 border border-titan-500/10"><button onClick={() => setMode("delivery")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === "delivery" ? "bg-titan-600 text-white" : "text-gray-400 hover:text-white hover:bg-white/[0.03]"}`}>Delivery / Short Term</button><button onClick={() => setMode("intraday")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === "intraday" ? "bg-titan-600 text-white" : "text-gray-400 hover:text-white hover:bg-white/[0.03]"}`}>Intraday</button></div>
    {mode === "intraday" ? <IntradayRecommendations /> : <>
      {error && !scanning && <WidgetError message={error} onRetry={() => void load(false)} />}
      {scanInfo && <div className="glass-card p-3 text-sm text-titan-300 border border-titan-500/20">{scanInfo}</div>}
      <div className="glass-card p-3 text-xs text-titan-300 border border-titan-500/20">Delivery strict gate: <b>Delivery Technical Pillar Score ≥95</b>. Intraday Technical Pillar is independent and is not required for Delivery. Recommendations are saved in the browser so logout/login does not force a rescan.</div>
      <SymbolAnalyzer />
      {loading && recommendations.length === 0 ? <div className="glass-card p-8 text-center text-gray-400">No automatic scan. Run a delivery scan when you want fresh recommendations.</div> : <>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4"><StatCard label="Buy signals" value={buyCount} tone="text-emerald-400" icon={<TrendingUp size={16} />} /><StatCard label="Sell signals" value={sellCount} tone="text-red-400" icon={<TrendingDown size={16} />} /><StatCard label="Neutral" value={neutralCount} tone="text-gray-400" icon={<Minus size={16} />} /><StatCard label="Avg confidence" value={avgConfidence} tone="text-titan-400" icon={<Zap size={16} />} /></div>
        <div className="flex flex-wrap items-center gap-3"><div className="relative w-full sm:w-64"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by symbol…" className="input-field w-full text-sm pl-9" /></div><div className="flex flex-wrap items-center gap-2 text-xs text-gray-500"><span>Sort:</span>{sortButton("technical", "Technical")}{sortButton("risk", "Risk")}{sortButton("confidence", "Confidence")}{sortButton("return", "Return")}{sortButton("symbol", "Symbol")}</div></div>
        {filtered.length === 0 ? <div className="glass-card p-10 text-center"><Brain size={28} className="mx-auto text-titan-500/60 mb-3" /><p className="text-gray-400">No stock currently has a Delivery Technical Pillar Score ≥95.</p><p className="text-gray-600 text-xs mt-2">Titan X does not require the Intraday Technical Pillar for Delivery recommendations.</p><button onClick={handleScan} className="btn-primary mt-4 text-sm inline-flex items-center gap-2"><Play size={14} /> Run fresh delivery market scan</button></div> : <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">{filtered.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)}</div>}
      </>}
    </>}
  </div>
}
