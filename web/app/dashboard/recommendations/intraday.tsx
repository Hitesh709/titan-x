"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { RefreshCw, TrendingDown, TrendingUp, Clock3, AlertTriangle, ArrowUp, ArrowDown } from "lucide-react"
import api from "@/lib/api"
import type { IntradayRecommendation, IntradayRecommendationsResponse } from "@/types"

type StrictIntradayRecommendation = IntradayRecommendation & {
  technical_pillar_score?: number | string | null
  technical_score?: number | string | null
  score?: number | string | null
  factors?: Record<string, { score?: number | string | null; direction?: number | string | null }> | null
  evidence?: string[] | null
  caution?: string[] | null
  risk_level?: string | null
  volume_ratio?: number | string | null
}
type StrictResponse = IntradayRecommendationsResponse & {
  recommendations?: StrictIntradayRecommendation[] | null
  scanning?: boolean
  universe_size?: number | null
  scanned?: number | null
  scan_status?: { scanned?: number | null; universe_size?: number | null; progress_pct?: number | null; error?: string | null }
}
type SortKey = "technical" | "risk" | "confidence" | "return" | "symbol"
type SortDir = "asc" | "desc"

const toNumber = (value: unknown, fallback = 0) => {
  const n = typeof value === "number" ? value : Number(value)
  return Number.isFinite(n) ? n : fallback
}
function money(value: unknown) {
  const n = toNumber(value, NaN)
  return Number.isFinite(n) ? `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"
}
function score(value: unknown) { return toNumber(value, 0) }

const FNO_INDEX_PRIORITY = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]
const PILLARS = ["technical", "fundamental", "news", "regime", "similarity", "risk"]
const PILLAR_LABELS: Record<string, string> = { technical: "Technical", fundamental: "Fundamental", news: "News", regime: "Regime", similarity: "Pattern", risk: "Risk" }
const riskRank = (risk?: string | null) => risk === "Low" ? 1 : risk === "Medium" ? 2 : risk === "High" ? 3 : 0
function fnoPriority(symbol: unknown) {
  const normalized = String(symbol ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "")
  const index = FNO_INDEX_PRIORITY.findIndex((name) => normalized === name || normalized.startsWith(name))
  return index === -1 ? 999 : index
}

function pillarsFor(rec: StrictIntradayRecommendation) {
  const factors = rec.factors ?? {}
  const technical = score(rec.technical_pillar_score ?? rec.technical_score ?? rec.score)
  return PILLARS.map((name) => ({
    name,
    score: name === "technical" ? technical : score(factors[name]?.score, 50),
  }))
}

function RecommendationCard({ rec }: { rec: StrictIntradayRecommendation }) {
  const symbol = String(rec.symbol ?? "UNKNOWN")
  const bullish = rec.direction === "BUY"
  const bearish = rec.direction === "SELL"
  const directionClass = bullish ? "badge-green" : bearish ? "badge-red" : "badge-blue"
  const technicalScore = score(rec.technical_pillar_score ?? rec.technical_score ?? rec.score)
  const pillars = pillarsFor(rec)
  const evidence = Array.isArray(rec.evidence) ? rec.evidence.filter(Boolean) : []
  const caution = Array.isArray(rec.caution) ? rec.caution.filter(Boolean) : []
  const volumeRatio = score(rec.volume_ratio, NaN)

  return <div className="glass-card p-5">
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">{symbol.slice(0, 4)}</span>
        <div><div className="text-white font-semibold">{symbol}</div><div className="text-[11px] text-gray-500">{rec.instrument ?? "—"} · {rec.timeframe ?? "—"}</div></div>
      </div>
      <span className={`badge ${directionClass}`}>{bullish ? <TrendingUp size={12} className="inline mr-1" /> : bearish ? <TrendingDown size={12} className="inline mr-1" /> : null}{rec.direction ?? "WAIT"}</span>
    </div>

    <div className="mt-4 flex items-center justify-between">
      <div><div className="text-[11px] text-gray-500">Current</div><div className="text-lg font-semibold text-white">{money(rec.current_price)}</div></div>
      <div className="text-right"><div className="text-[11px] text-gray-500">Technical Pillar</div><div className="text-sm font-semibold text-emerald-300">{technicalScore.toFixed(0)} / 100</div></div>
    </div>

    <div className="grid grid-cols-3 gap-2 mt-4">
      <div className="rounded-lg bg-white/[0.03] p-2"><div className="text-[10px] text-gray-500">Entry</div><div className="text-xs text-white mt-1">{money(rec.entry_price)}</div></div>
      <div className="rounded-lg bg-emerald-500/[0.05] p-2"><div className="text-[10px] text-gray-500">Target</div><div className="text-xs text-emerald-300 mt-1">{money(rec.target_price)}</div></div>
      <div className="rounded-lg bg-red-500/[0.05] p-2"><div className="text-[10px] text-gray-500">Stop</div><div className="text-xs text-red-300 mt-1">{money(rec.stop_price)}</div></div>
    </div>

    <div className="mt-4">
      <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Pillar scores</div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {pillars.map((p) => <div key={p.name} className="bg-white/[0.03] rounded-lg p-2.5 border border-white/5">
          <div className="flex items-center justify-between"><span className="text-[11px] text-gray-400">{PILLAR_LABELS[p.name]}</span><span className={`text-[12px] font-semibold ${p.score >= 70 ? "text-emerald-400" : p.score <= 40 ? "text-red-400" : "text-amber-400"}`}>{Math.round(p.score)}</span></div>
          <div className="mt-1 h-1 rounded-full bg-white/5 overflow-hidden"><div className={`h-full rounded-full ${p.score >= 70 ? "bg-emerald-500" : p.score <= 40 ? "bg-red-500" : "bg-amber-500"}`} style={{ width: `${Math.min(100, Math.max(0, p.score))}%` }} /></div>
        </div>)}
      </div>
    </div>

    <div className="grid grid-cols-4 gap-2 mt-3 text-[11px]">
      <div><span className="text-gray-500">RSI</span><div className="text-gray-200 mt-0.5">{Number.isFinite(toNumber(rec.rsi, NaN)) ? toNumber(rec.rsi).toFixed(1) : "—"}</div></div>
      <div><span className="text-gray-500">EMA20</span><div className="text-gray-200 mt-0.5">{money(rec.ema20)}</div></div>
      <div><span className="text-gray-500">EMA50</span><div className="text-gray-200 mt-0.5">{money(rec.ema50)}</div></div>
      <div><span className="text-gray-500">Vol</span><div className="text-gray-200 mt-0.5">{Number.isFinite(volumeRatio) ? `${volumeRatio.toFixed(1)}x` : "—"}</div></div>
    </div>

    {rec.segment === "fno" && <div className="mt-4 rounded-lg border border-titan-500/20 bg-titan-500/[0.04] p-3"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-titan-300">F&O Strategy</span><span className="text-xs text-white">{rec.option_bias === "CALL" ? "CALL bias" : rec.option_bias === "PUT" ? "PUT bias" : "No option bias"}</span></div><div className="mt-1 text-[11px] text-gray-400">Futures: {bullish ? "LONG" : bearish ? "SHORT" : "WAIT"}{rec.option_strike ? ` · ATM candidate ${rec.option_strike}` : ""}</div></div>}

    <div className="mt-4 pt-3 border-t border-white/5">
      <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">Why</div>
      {evidence.length > 0 ? <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">{evidence.slice(0, 3).map((item, index) => <li key={`${symbol}-evidence-${index}`}>{String(item)}</li>)}</ul> : <div className="text-xs text-gray-500">Technical signal generated from the current market model.</div>}
      {caution.length > 0 && <div className="mt-2 flex gap-2 text-[11px] text-amber-300"><AlertTriangle size={13} className="shrink-0 mt-0.5" /><span>{String(caution[0])}</span></div>}
    </div>
  </div>
}

export function IntradayRecommendations() {
  const [segment, setSegment] = useState<"equity" | "fno">("equity")
  const [data, setData] = useState<StrictResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>("technical")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const cacheKey = `titanx.strict.intraday.${segment}.v2`
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<StrictResponse>(`/recommendations/strict?mode=intraday&segment=${segment}&limit=3000`)
      const normalized: StrictResponse = { ...res, recommendations: Array.isArray(res.recommendations) ? res.recommendations : [] }
      setData(normalized)
      try { localStorage.setItem(cacheKey, JSON.stringify(normalized)) } catch { /* storage is optional */ }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to load strict intraday recommendations"
      setError(message)
      try {
        const cached = localStorage.getItem(cacheKey)
        if (cached) setData(JSON.parse(cached) as StrictResponse)
      } catch { /* ignore malformed cache */ }
    } finally { setLoading(false) }
  }, [segment, cacheKey])

  useEffect(() => {
    setError(null)
    try {
      const cached = localStorage.getItem(cacheKey)
      if (cached) {
        const parsed = JSON.parse(cached) as StrictResponse
        if (parsed && Array.isArray(parsed.recommendations)) setData(parsed)
      }
    } catch { /* ignore malformed cache */ }
    // Deliberately no API request here. Intraday scanning is manual only.
  }, [cacheKey])

  const toggleSort = (key: SortKey) => { if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc"); else { setSortKey(key); setSortDir("desc") } }
  const displayedRecommendations = useMemo(() => {
    const recommendations = [...((data?.recommendations ?? []) as StrictIntradayRecommendation[])]
    return recommendations.sort((a, b) => {
      if (segment === "fno" && sortKey === "technical") { const p = fnoPriority(a.symbol) - fnoPriority(b.symbol); if (p !== 0) return p }
      let av: number | string; let bv: number | string
      if (sortKey === "technical") { av = score(a.technical_pillar_score ?? a.technical_score ?? a.score); bv = score(b.technical_pillar_score ?? b.technical_score ?? b.score) }
      else if (sortKey === "risk") { av = riskRank(a.risk_level); bv = riskRank(b.risk_level) }
      else if (sortKey === "confidence") { av = score(a.confidence); bv = score(b.confidence) }
      else if (sortKey === "return") { av = score(a.expected_return_pct); bv = score(b.expected_return_pct) }
      else { av = String(a.symbol ?? ""); bv = String(b.symbol ?? "") }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return String(a.symbol ?? "").localeCompare(String(b.symbol ?? ""))
    })
  }, [data?.recommendations, segment, sortKey, sortDir])

  const priorityIndices = useMemo(() => displayedRecommendations.filter((rec) => fnoPriority(rec.symbol) < 999), [displayedRecommendations])
  const scanStatus = data?.scan_status
  const sortButton = (key: SortKey, label: string) => <button onClick={() => toggleSort(key)} className={`px-2 py-1 rounded border ${sortKey === key ? "border-titan-500 text-titan-300" : "border-white/10 text-gray-400"}`}>{label} {sortKey === key ? (sortDir === "asc" ? <ArrowUp size={11} className="inline" /> : <ArrowDown size={11} className="inline" />) : null}</button>

  return <div className="space-y-5">
    <div className="glass-card p-3 flex flex-wrap items-center justify-between gap-3">
      <div><div className="text-white font-semibold flex items-center gap-2"><Clock3 size={15} className="text-titan-400" /> Intraday AI</div><div className="text-xs text-gray-500 mt-1">5-minute market structure · Technical Pillar ≥95 · full available universe · manual refresh only</div></div>
      <div className="flex items-center gap-2"><div className="flex rounded-lg border border-white/10 p-1 bg-white/[0.02]"><button onClick={() => setSegment("equity")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "equity" ? "bg-titan-600 text-white" : "text-gray-400"}`}>Equity Intraday</button><button onClick={() => setSegment("fno")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "fno" ? "bg-titan-600 text-white" : "text-gray-400"}`}>F&O Intraday</button></div><button onClick={() => void load()} disabled={loading} className="btn-secondary text-xs inline-flex items-center gap-2 disabled:opacity-50"><RefreshCw size={13} className={loading ? "animate-spin" : ""} /> {loading ? "Scanning…" : "Refresh / Scan"}</button></div>
    </div>

    {data && <div className="grid grid-cols-2 md:grid-cols-4 gap-3"><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Universe</div><div className="text-xl text-white font-semibold mt-1">{data.universe_size ?? scanStatus?.universe_size ?? "—"}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Scanned</div><div className="text-xl text-white font-semibold mt-1">{data.scanned ?? scanStatus?.scanned ?? "—"}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Strict Signals</div><div className="text-xl text-emerald-400 font-semibold mt-1">{displayedRecommendations.length}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500 flex items-center gap-1"><Clock3 size={12} /> Status</div><div className="text-xs text-gray-300 mt-2">{data.scanning ? `${Math.round(score(scanStatus?.progress_pct))}% scanning` : data.generated_at ? new Date(data.generated_at).toLocaleTimeString() : "Complete"}</div></div></div>}
    {data?.scanning && <div className="glass-card p-4 border border-titan-500/20 text-sm text-titan-300">Full-market intraday scan is running in the background — {scanStatus?.scanned ?? 0} / {scanStatus?.universe_size ?? data.universe_size ?? 0} symbols scanned.</div>}
    {data?.scan_status?.error && <div className="glass-card p-4 border border-red-500/20 text-sm text-red-400">Scan error: {data.scan_status.error}</div>}
    {error && <div className="glass-card p-4 border border-red-500/20 text-sm text-red-400">{error}</div>}
    <div className="glass-card p-3 text-xs text-titan-300 border border-titan-500/20">Intraday strict gate: <b>Intraday Technical Pillar Score ≥95</b>. Delivery is independent. Confidence is not used for the 95+ technical gate. Saved recommendations remain visible after logout/login.</div>

    {segment === "fno" && priorityIndices.length > 0 && <div className="glass-card p-4 border border-titan-500/20"><div className="text-xs uppercase tracking-wider text-titan-300 font-semibold mb-3">Major F&O Indices — Priority</div><div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">{priorityIndices.map((rec) => { const s = score(rec.technical_pillar_score ?? rec.technical_score ?? rec.score); return <div key={`priority-${String(rec.symbol)}`} className="rounded-lg bg-white/[0.03] border border-white/10 px-3 py-2"><div className="text-white font-semibold text-sm">{String(rec.symbol ?? "—")}</div><div className={`text-xs mt-1 ${rec.direction === "BUY" ? "text-emerald-400" : rec.direction === "SELL" ? "text-red-400" : "text-gray-400"}`}>{rec.direction ?? "WAIT"} · Technical {s.toFixed(0)}</div></div> })}</div></div>}

    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500"><span>Sort:</span>{sortButton("technical", "Technical")}{sortButton("risk", "Risk")}{sortButton("confidence", "Confidence")}{sortButton("return", "Return")}{sortButton("symbol", "Symbol")}</div>
    {!data && !loading && !error && <div className="glass-card p-8 text-center text-sm text-gray-400">No scan has been run yet. Press <b className="text-white">Refresh / Scan</b> to scan the full available market.</div>}
    {loading && <div className="glass-card p-8 text-center text-sm text-gray-400">Scanning the full available market…</div>}
    {!loading && data && !data.scanning && !error && displayedRecommendations.length === 0 && <div className="glass-card p-8 text-center text-sm text-gray-400">No stock currently has an Intraday Technical Pillar Score of 95 or higher.</div>}
    {!loading && !error && !data?.scanning && displayedRecommendations.length > 0 && <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">{displayedRecommendations.map((rec, index) => <RecommendationCard key={`${String(rec.segment ?? segment)}-${String(rec.symbol ?? "unknown")}-${String(rec.instrument ?? "")}-${index}`} rec={rec} />)}</div>}
    <div className="text-[10px] text-gray-600 px-1">Six pillars are displayed for every strict recommendation: Technical, Fundamental, News, Regime, Historical Pattern and Risk.</div>
  </div>
}
