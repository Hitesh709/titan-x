"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import {
  Brain, RefreshCw, Search, Play, Zap, Clock, TrendingUp, TrendingDown, Minus, ArrowUp, ArrowDown,
} from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { StockRecommendation, RecommendationsPage, ScanStatus } from "@/types"
import { formatPercent, formatDate } from "@/lib/utils"

const LIMIT = 200

const SORT_OPTIONS: { label: string; sortBy: string; desc: boolean }[] = [
  { label: "Score (high → low)", sortBy: "score", desc: true },
  { label: "Confidence (high → low)", sortBy: "confidence", desc: true },
  { label: "Expected return (high → low)", sortBy: "predicted_return_pct", desc: true },
  { label: "Technical signal (strongest → weakest)", sortBy: "signal", desc: false },
  { label: "Risk (high → low)", sortBy: "risk_level", desc: true },
  { label: "Price (high → low)", sortBy: "current_price", desc: true },
  { label: "Symbol (A → Z)", sortBy: "symbol", desc: false },
]

interface ParsedMeta {
  signal?: string
  as_of_date?: string
  evidence?: string[]
  caution?: string[]
  returns?: Record<string, number | null>
}

function parseMeta(rec: StockRecommendation): ParsedMeta {
  if (!rec.metadata_json) return {}
  try {
    return JSON.parse(rec.metadata_json) as ParsedMeta
  } catch {
    return {}
  }
}

export default function RecommendationsPage() {
  const [items, setItems] = useState<StockRecommendation[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState("")
  const [sortBy, setSortBy] = useState("score")
  const [sortDesc, setSortDesc] = useState(true)
  const [scan, setScan] = useState<ScanStatus | null>(null)
  const [scanning, setScanning] = useState(false)
  const mounted = useRef(true)
  const startedRef = useRef(false)

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const res = await api.get<RecommendationsPage>(
        `/recommendations?status=active&sort_by=${sortBy}&sort_desc=${sortDesc}&limit=${LIMIT}`
      )
      if (!mounted.current) return
      setItems(res.items ?? [])
      setTotal(res.total ?? 0)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load recommendations")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [sortBy, sortDesc])

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.get<ScanStatus>("/recommendations/scan/status")
      if (!mounted.current) return
      setScan(s)
      setScanning(s.running === true)
    } catch {
      /* ignore */
    }
  }, [])

  // Kick off a live scan on first mount if there is nothing stored yet.
  useEffect(() => {
    mounted.current = true
    api
      .get<RecommendationsPage>(`/recommendations?status=active&limit=1`)
      .then((res) => {
        if (!mounted.current) return
        if ((res.total ?? 0) === 0 && !startedRef.current) {
          startedRef.current = true
          api.post<ScanStatus>("/recommendations/scan", {}).catch(() => {})
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!mounted.current) return
        setLoading(false)
        loadStatus()
      })
    return () => {
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useLiveRefresh(
    useCallback(() => {
      void load(true)
      void loadStatus()
    }, [load, loadStatus]),
    []
  )

  const handleRescan = async () => {
    setScanning(true)
    try {
      const res = await api.post<ScanStatus>("/recommendations/scan", {
        max_age_minutes: 0,
      })
      setScan(res)
    } catch (e) {
      setScanning(false)
    }
  }

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value
    const opt = SORT_OPTIONS.find((o) => o.sortBy === key)
    setSortBy(key)
    setSortDesc(opt ? opt.desc : true)
  }

  const toggleSortDesc = () => setSortDesc((d) => !d)

  // Reload whenever the sort key/direction changes.
  useEffect(() => {
    void load(true)
  }, [load])

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q) return items
    return items.filter((r) => r.symbol.toUpperCase().includes(q))
  }, [items, query])

  const buy = items.filter((r) => r.direction === "BUY").length
  const sell = items.filter((r) => r.direction === "SELL").length
  const hold = items.filter((r) => r.direction === "HOLD").length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Live Recommendations</h1>
          <p className="text-sm text-gray-500">
            Full-market BUY / SELL signals from live NSE data, refreshed automatically every 5s.
          </p>
        </div>
        <button
          onClick={handleRescan}
          disabled={scanning}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-titan-600/20 border border-titan-600/40 text-white text-sm font-medium hover:bg-titan-600/30 disabled:opacity-50 transition-colors"
        >
          {scanning ? (
            <RefreshCw size={15} className="animate-spin" />
          ) : (
            <Play size={15} />
          )}
          {scanning ? "Scanning live market…" : "Run full market scan"}
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Buy signals" value={buy} tone="text-emerald-400" icon={<TrendingUp size={16} />} />
        <StatCard label="Hold signals" value={hold} tone="text-gray-300" icon={<Minus size={16} />} />
        <StatCard label="Sell signals" value={sell} tone="text-red-400" icon={<TrendingDown size={16} />} />
        <StatCard label="Stocks covered" value={total} tone="text-titan-400" icon={<Zap size={16} />} />
      </div>

      {scan?.last && (
        <div className="text-xs text-gray-500 flex flex-wrap items-center gap-4">
          <span className="inline-flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${scanning ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`}
            />
            {scanning ? "Live scan in progress" : "Scan complete"}
          </span>
          {typeof scan.last.stored === "number" && <span>• {scan.last.stored} recommendations stored</span>}
          {typeof scan.last.failed === "number" && <span>• {scan.last.failed} symbols unavailable</span>}
          {scan.last.finished_at && <span>• Finished {new Date(scan.last.finished_at).toLocaleTimeString()}</span>}
        </div>
      )}

      {/* Search + sort */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by symbol (e.g. RELIANCE, TCS)…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/5 border border-titan-800/30 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-titan-500/50"
          />
        </div>
        <select
          value={sortBy}
          onChange={handleSortChange}
          className="px-3 py-2 rounded-lg bg-white/5 border border-titan-800/30 text-white text-sm focus:outline-none focus:border-titan-500/50"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.sortBy} value={o.sortBy} className="bg-gray-900">
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={toggleSortDesc}
          title={sortDesc ? "Sorting descending — click for ascending" : "Sorting ascending — click for descending"}
          className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-white/5 border border-titan-800/30 text-gray-300 hover:bg-white/10 transition-colors"
        >
          {sortDesc ? <ArrowDown size={15} /> : <ArrowUp size={15} />}
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card h-28 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="glass-card p-6 text-center">
          <p className="text-sm text-red-400 mb-3">{error}</p>
          <button onClick={() => load()} className="text-sm text-titan-400 hover:underline">
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-card p-10 text-center">
          <Brain size={28} className="mx-auto mb-3 text-gray-600" />
          <p className="text-sm text-gray-400">
            {items.length === 0
              ? "No recommendations generated yet. Run a full market scan to start analyzing the live NSE universe."
              : "No symbols match your search."}
          </p>
          {items.length === 0 && (
            <button
              onClick={handleRescan}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-titan-600/20 border border-titan-600/40 text-white text-sm font-medium hover:bg-titan-600/30"
            >
              <Play size={15} /> Start live scan
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} />
          ))}
        </div>
      )}
    </div>
  )
}

function StatCard({
  label, value, tone, icon,
}: {
  label: string
  value: number
  tone: string
  icon: React.ReactNode
}) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 text-gray-500">
        <span className={tone}>{icon}</span>
        <span className="text-xs">{label}</span>
      </div>
      <div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div>
    </div>
  )
}

function RecommendationCard({ rec }: { rec: StockRecommendation }) {
  const meta = parseMeta(rec)
  const dirCls =
    rec.direction === "BUY"
      ? "badge-green"
      : rec.direction === "SELL"
        ? "badge-red"
        : "badge-blue"

  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between gap-3">
        <Link href={`/dashboard/stocks/${rec.symbol}`} className="flex items-center gap-3 group">
          <span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">
            {rec.symbol.slice(0, 4)}
          </span>
          <div>
            <div className="text-white font-semibold group-hover:text-titan-400 transition-colors">
              {rec.symbol}
            </div>
            <div className="text-[11px] text-gray-500">
              ₹{rec.current_price?.toLocaleString("en-IN") ?? "—"}
            </div>
          </div>
        </Link>
        <span className={`badge ${dirCls}`}>
          {rec.direction}
          {rec.signal ? ` · ${rec.signal.replaceAll("_", " ")}` : ""}
        </span>
      </div>

      {/* Confidence + return */}
      <div className="grid grid-cols-3 gap-3 mt-4">
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Confidence</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className={`h-full rounded-full ${rec.confidence! >= 50 ? "bg-emerald-500" : "bg-yellow-500"}`}
                style={{ width: `${Math.min(100, rec.confidence ?? 0)}%` }}
              />
            </div>
            <span className="text-xs text-gray-300">{Math.round(rec.confidence ?? 0)}%</span>
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Expected return</div>
          <div
            className={`text-sm font-semibold ${
              (rec.predicted_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {rec.predicted_return_pct !== null && rec.predicted_return_pct !== undefined
              ? formatPercent(rec.predicted_return_pct)
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Holding</div>
          <div className="text-sm text-gray-300">{rec.timeframe ?? "—"}</div>
        </div>
      </div>

      {/* Risk + price target */}
      <div className="flex items-center gap-2 mt-3">
        <RiskBadge risk={rec.risk_level} />
        {rec.price_target ? (
          <span className="text-[11px] text-gray-500">
            Target ₹{rec.price_target.toLocaleString("en-IN")}
          </span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-gray-500">
          <Clock size={12} />
          {rec.generated_at ? new Date(rec.generated_at).toLocaleTimeString() : "—"}
        </span>
      </div>

      {/* Evidence / caution */}
      <div className="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-titan-800/20">
        <div>
          <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">
            Supporting evidence
          </div>
          <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
            {(meta.evidence ?? []).slice(0, 3).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] font-semibold text-red-400/90 uppercase tracking-wider mb-1.5">
            Reasons for caution
          </div>
          <ul className="space-y-1 text-xs text-gray-400 list-disc list-inside">
            {(meta.caution ?? []).slice(0, 3).map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function RiskBadge({ risk }: { risk?: string | null }) {
  const cls =
    risk === "High"
      ? "bg-red-500/10 text-red-400"
      : risk === "Medium"
        ? "bg-amber-500/10 text-amber-400"
        : "bg-emerald-500/10 text-emerald-400"
  return <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{risk ?? "—"}</span>
}