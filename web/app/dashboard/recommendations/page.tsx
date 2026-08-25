"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { RefreshCw, Search, Play, Zap, TrendingUp, TrendingDown, Minus, ArrowUp, ArrowDown, Brain } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { StockRecommendation } from "@/types"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"
import { StatCard, RecommendationCard } from "./components"
import { SymbolAnalyzer } from "./analyzer"
import { IntradayRecommendations } from "./intraday"

type SortKey = "confidence" | "return" | "symbol"
type SortDir = "asc" | "desc"

export default function RecommendationsPage() {
  const [recommendations, setRecommendations] = useState<StockRecommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("confidence")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [scanInfo, setScanInfo] = useState<string | null>(null)
  const [mode, setMode] = useState<"delivery" | "intraday">("delivery")
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<{ recommendations: StockRecommendation[]; strict_technical_threshold?: number }>(
        "/recommendations/strict?mode=delivery&limit=100",
      )
      if (!mounted.current) return
      setRecommendations(res.recommendations ?? [])
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load strict recommendations")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleScan = async () => {
    setScanning(true)
    setError(null)
    setScanInfo(null)
    try {
      const res = await api.post<{
        last?: {
          universe?: number
          scanned?: number
          stored?: number
          no_trade?: number
          insufficient_data?: number
          failed?: number
          used_fallback_universe?: boolean
        }
        last_error?: string
      }>("/recommendations/scan?sync=true&limit=500", {})
      const last = res?.last
      if (last) {
        const universe = Number(last.universe ?? 0)
        const scanned = Number(last.scanned ?? 0)
        const stored = Number(last.stored ?? 0)
        const noTrade = Number(last.no_trade ?? 0)
        const insufficient = Number(last.insufficient_data ?? 0)
        const failed = Number(last.failed ?? 0)
        let msg = `Scanned ${scanned}${universe ? `/${universe}` : ""} symbols · ${stored} signal(s) stored · ${noTrade} no-trade · ${insufficient} insufficient · ${failed} failed.`
        if (last.used_fallback_universe) msg += " (DB universe empty — used built-in NSE list)"
        if (res?.last_error) msg += ` Scan error: ${res.last_error}`
        setScanInfo(msg)
      } else {
        setScanInfo("Scan finished but returned no detail.")
      }
      for (let i = 0; i < 3; i++) {
        await new Promise(r => setTimeout(r, 800))
        await load(true)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed")
    } finally {
      setScanning(false)
    }
  }

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase()
    const list = q ? recommendations.filter((r) => r.symbol.toUpperCase().includes(q)) : recommendations
    return [...list].sort((a, b) => {
      let av: number | string
      let bv: number | string
      if (sortKey === "symbol") {
        av = a.symbol
        bv = b.symbol
      } else if (sortKey === "return") {
        av = a.predicted_return_pct ?? -Infinity
        bv = b.predicted_return_pct ?? -Infinity
      } else {
        av = a.confidence ?? 0
        bv = b.confidence ?? 0
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return 0
    })
  }, [recommendations, query, sortKey, sortDir])

  const buyCount = recommendations.filter((r) => r.direction === "BUY").length
  const sellCount = recommendations.filter((r) => r.direction === "SELL").length
  const neutralCount = recommendations.length - buyCount - sellCount
  const avgConfidence = recommendations.length === 0 ? 0 : Math.round(recommendations.reduce((s, r) => s + (r.confidence ?? 0), 0) / recommendations.length)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Recommendations</h1>
          <p className="text-gray-500 text-sm mt-1">Titan X strict stock recommendations — technical conviction must be ≥95 in both delivery and intraday</p>
        </div>
        {mode === "delivery" && (
          <div className="flex items-center gap-2">
            <button onClick={handleScan} disabled={scanning} className="btn-secondary text-sm inline-flex items-center gap-2 disabled:opacity-50">
              {scanning ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
              {scanning ? "Scanning…" : "Run Scan"}
            </button>
            <RefreshButton onClick={handleRefresh} spinning={refreshing} />
          </div>
        )}
      </div>

      <div className="glass-card p-2 flex gap-2 border border-titan-500/10">
        <button onClick={() => setMode("delivery")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === "delivery" ? "bg-titan-600 text-white" : "text-gray-400 hover:text-white hover:bg-white/[0.03]"}`}>
          Delivery / Short Term
        </button>
        <button onClick={() => setMode("intraday")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === "intraday" ? "bg-titan-600 text-white" : "text-gray-400 hover:text-white hover:bg-white/[0.03]"}`}>
          Intraday
        </button>
      </div>

      {mode === "intraday" ? (
        <IntradayRecommendations />
      ) : (
        <>
          {error && <WidgetError message={error} onRetry={() => load(false)} />}
          {scanInfo && <div className="glass-card p-3 text-sm text-titan-300 border border-titan-500/20">{scanInfo}</div>}
          <div className="glass-card p-3 text-xs text-titan-300 border border-titan-500/20">Strict gate: the same stock must have directional technical conviction ≥95 on the delivery model and the live 5-minute intraday model, with matching BUY/SELL direction.</div>
          <SymbolAnalyzer />

          {loading ? (
            <div className="grid md:grid-cols-3 gap-4">
              <div className="glass-card p-5"><WidgetLoading lines={2} /></div>
              <div className="glass-card p-5"><WidgetLoading lines={2} /></div>
              <div className="glass-card p-5"><WidgetLoading lines={2} /></div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard label="Buy signals" value={buyCount} tone="text-emerald-400" icon={<TrendingUp size={16} />} />
                <StatCard label="Sell signals" value={sellCount} tone="text-red-400" icon={<TrendingDown size={16} />} />
                <StatCard label="Neutral" value={neutralCount} tone="text-gray-400" icon={<Minus size={16} />} />
                <StatCard label="Avg confidence" value={avgConfidence} tone="text-titan-400" icon={<Zap size={16} />} />
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <div className="relative w-full sm:w-64">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by symbol…" className="input-field w-full text-sm pl-9" />
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>Sort:</span>
                  <button onClick={() => toggleSort("confidence")} className={`px-2 py-1 rounded border ${sortKey === "confidence" ? "border-titan-500 text-titan-300" : "border-white/10 text-gray-400"}`}>Confidence {sortKey === "confidence" ? (sortDir === "asc" ? <ArrowUp size={11} className="inline" /> : <ArrowDown size={11} className="inline" />) : null}</button>
                  <button onClick={() => toggleSort("return")} className={`px-2 py-1 rounded border ${sortKey === "return" ? "border-titan-500 text-titan-300" : "border-white/10 text-gray-400"}`}>Return {sortKey === "return" ? (sortDir === "asc" ? <ArrowUp size={11} className="inline" /> : <ArrowDown size={11} className="inline" />) : null}</button>
                  <button onClick={() => toggleSort("symbol")} className={`px-2 py-1 rounded border ${sortKey === "symbol" ? "border-titan-500 text-titan-300" : "border-white/10 text-gray-400"}`}>Symbol {sortKey === "symbol" ? (sortDir === "asc" ? <ArrowUp size={11} className="inline" /> : <ArrowDown size={11} className="inline" />) : null}</button>
                </div>
              </div>

              {filtered.length === 0 ? (
                <div className="glass-card p-10 text-center">
                  <Brain size={28} className="mx-auto text-titan-500/60 mb-3" />
                  <p className="text-gray-400">No stock currently passes the strict 95+ delivery + intraday technical gate.</p>
                  <p className="text-gray-600 text-xs mt-2">Titan X will intentionally show no recommendation when the threshold is not met.</p>
                  <button onClick={handleScan} className="btn-primary mt-4 text-sm inline-flex items-center gap-2"><Play size={14} /> Run fresh market scan</button>
                </div>
              ) : (
                <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {filtered.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
