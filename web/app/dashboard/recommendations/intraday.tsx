"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { RefreshCw, TrendingDown, TrendingUp, Zap, Clock3, AlertTriangle } from "lucide-react"
import api from "@/lib/api"
import type { IntradayRecommendation, IntradayRecommendationsResponse } from "@/types"

type StrictIntradayRecommendation = IntradayRecommendation & { technical_pillar_score?: number; technical_score?: number }
type StrictResponse = IntradayRecommendationsResponse & { scanning?: boolean; scan_status?: { scanned?: number; universe_size?: number; progress_pct?: number; error?: string | null } }

function money(value: number) {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
}

const FNO_INDEX_PRIORITY = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]

function fnoPriority(symbol: string) {
  const normalized = symbol.toUpperCase().replace(/[^A-Z0-9]/g, "")
  const index = FNO_INDEX_PRIORITY.findIndex((name) => normalized === name || normalized.startsWith(name))
  return index === -1 ? 999 : index
}

function RecommendationCard({ rec }: { rec: StrictIntradayRecommendation }) {
  const bullish = rec.direction === "BUY"
  const bearish = rec.direction === "SELL"
  const directionClass = bullish ? "badge-green" : bearish ? "badge-red" : "badge-blue"
  const technicalScore = rec.technical_pillar_score ?? rec.technical_score ?? rec.score
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">{rec.symbol.slice(0, 4)}</span><div><div className="text-white font-semibold">{rec.symbol}</div><div className="text-[11px] text-gray-500">{rec.instrument} · {rec.timeframe}</div></div></div></div><span className={`badge ${directionClass}`}>{bullish ? <TrendingUp size={12} className="inline mr-1" /> : bearish ? <TrendingDown size={12} className="inline mr-1" /> : null}{rec.direction}</span></div>
      <div className="mt-4 flex items-center justify-between"><div><div className="text-[11px] text-gray-500">Current</div><div className="text-lg font-semibold text-white">{money(rec.current_price)}</div></div><div className="text-right"><div className="text-[11px] text-gray-500">Technical Pillar Score</div><div className="text-sm font-semibold text-titan-300">{technicalScore.toFixed(0)} / 100</div></div></div>
      <div className="grid grid-cols-3 gap-2 mt-4"><div className="rounded-lg bg-white/[0.03] p-2"><div className="text-[10px] text-gray-500">Entry</div><div className="text-xs text-white mt-1">{money(rec.entry_price)}</div></div><div className="rounded-lg bg-emerald-500/[0.05] p-2"><div className="text-[10px] text-gray-500">Target</div><div className="text-xs text-emerald-300 mt-1">{money(rec.target_price)}</div></div><div className="rounded-lg bg-red-500/[0.05] p-2"><div className="text-[10px] text-gray-500">Stop</div><div className="text-xs text-red-300 mt-1">{money(rec.stop_price)}</div></div></div>
      <div className="grid grid-cols-4 gap-2 mt-3 text-[11px]"><div><span className="text-gray-500">RSI</span><div className="text-gray-200 mt-0.5">{rec.rsi?.toFixed(1) ?? "—"}</div></div><div><span className="text-gray-500">EMA20</span><div className="text-gray-200 mt-0.5">{rec.ema20 ? money(rec.ema20) : "—"}</div></div><div><span className="text-gray-500">EMA50</span><div className="text-gray-200 mt-0.5">{rec.ema50 ? money(rec.ema50) : "—"}</div></div><div><span className="text-gray-500">Vol</span><div className="text-gray-200 mt-0.5">{rec.volume_ratio.toFixed(1)}x</div></div></div>
      {rec.segment === "fno" && <div className="mt-4 rounded-lg border border-titan-500/20 bg-titan-500/[0.04] p-3"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-titan-300">F&O Strategy</span><span className="text-xs text-white">{rec.option_bias === "CALL" ? "CALL bias" : rec.option_bias === "PUT" ? "PUT bias" : "No option bias"}</span></div><div className="mt-1 text-[11px] text-gray-400">Futures: {bullish ? "LONG" : bearish ? "SHORT" : "WAIT"}{rec.option_strike ? ` · ATM candidate ${rec.option_strike}` : ""}</div><div className="mt-2 text-[10px] text-gray-500">Option premium/expiry is shown only when live derivatives-chain data is available.</div></div>}
      <div className="mt-4 pt-3 border-t border-white/5"><div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">Why</div><ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">{rec.evidence.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>{rec.caution.length > 0 && <div className="mt-2 flex gap-2 text-[11px] text-amber-300"><AlertTriangle size={13} className="shrink-0 mt-0.5" /><span>{rec.caution[0]}</span></div>}</div>
    </div>
  )
}

export function IntradayRecommendations() {
  const [segment, setSegment] = useState<"equity" | "fno">("equity")
  const [data, setData] = useState<StrictResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<StrictResponse>(`/recommendations/strict?mode=intraday&segment=${segment}&limit=2000`)
      setData(res)
      if (res.scanning) {
        window.setTimeout(() => void load(), 5000)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load strict intraday recommendations")
    } finally {
      setLoading(false)
    }
  }, [segment])

  useEffect(() => { void load() }, [load])

  const displayedRecommendations = useMemo(() => {
    const recommendations = (data?.recommendations ?? []) as StrictIntradayRecommendation[]
    if (segment !== "fno") return recommendations
    return [...recommendations].sort((a, b) => {
      const priorityDiff = fnoPriority(a.symbol) - fnoPriority(b.symbol)
      if (priorityDiff !== 0) return priorityDiff
      return (b.technical_pillar_score ?? b.technical_score ?? b.score ?? 0) - (a.technical_pillar_score ?? a.technical_score ?? a.score ?? 0)
    })
  }, [data?.recommendations, segment])

  const priorityIndices = useMemo(() => displayedRecommendations.filter((rec) => fnoPriority(rec.symbol) < 999), [displayedRecommendations])
  const scanStatus = data?.scan_status

  return (
    <div className="space-y-5">
      <div className="glass-card p-3 flex flex-wrap items-center justify-between gap-3"><div><div className="text-white font-semibold flex items-center gap-2"><Zap size={15} className="text-titan-400" /> Intraday AI</div><div className="text-xs text-gray-500 mt-1">5-minute market structure · momentum · volume · Technical pillar score ≥95 · full available universe</div></div><div className="flex items-center gap-2"><div className="flex rounded-lg border border-white/10 p-1 bg-white/[0.02]"><button onClick={() => setSegment("equity")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "equity" ? "bg-titan-600 text-white" : "text-gray-400"}`}>Equity Intraday</button><button onClick={() => setSegment("fno")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "fno" ? "bg-titan-600 text-white" : "text-gray-400"}`}>F&O Intraday</button></div><button onClick={() => void load()} className="btn-secondary text-xs inline-flex items-center gap-2"><RefreshCw size={13} /> Refresh</button></div></div>
      {data && <div className="grid grid-cols-2 md:grid-cols-4 gap-3"><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Universe</div><div className="text-xl text-white font-semibold mt-1">{data.universe_size}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Scanned</div><div className="text-xl text-white font-semibold mt-1">{data.scanned}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500">Strict Signals</div><div className="text-xl text-emerald-400 font-semibold mt-1">{displayedRecommendations.length}</div></div><div className="glass-card p-4"><div className="text-[11px] text-gray-500 flex items-center gap-1"><Clock3 size={12} /> Status</div><div className="text-xs text-gray-300 mt-2">{data.scanning ? `${Math.round(scanStatus?.progress_pct ?? 0)}% scanning` : data.generated_at ? new Date(data.generated_at).toLocaleTimeString() : "Starting…"}</div></div></div>}
      {data?.scanning && <div className="glass-card p-4 border border-titan-500/20 text-sm text-titan-300">Full-market scan is running in the background — {scanStatus?.scanned ?? 0} / {scanStatus?.universe_size ?? data.universe_size ?? 0} symbols scanned. This prevents the old API timeout on the free server.</div>}
      {data?.scan_status?.error && <div className="glass-card p-4 border border-red-500/20 text-sm text-red-400">Scan error: {data.scan_status.error}</div>}
      {segment === "fno" && priorityIndices.length > 0 && <div className="glass-card p-4 border border-titan-500/20"><div className="text-xs uppercase tracking-wider text-titan-300 font-semibold mb-3">Major F&O Indices — Priority</div><div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">{priorityIndices.map((rec) => { const score = rec.technical_pillar_score ?? rec.technical_score ?? rec.score; return <div key={`priority-${rec.symbol}`} className="rounded-lg bg-white/[0.03] border border-white/10 px-3 py-2"><div className="text-white font-semibold text-sm">{rec.symbol}</div><div className={`text-xs mt-1 ${rec.direction === "BUY" ? "text-emerald-400" : rec.direction === "SELL" ? "text-red-400" : "text-gray-400"}`}>{rec.direction} · Technical {score.toFixed(0)}</div></div> })}</div></div>}
      {loading && !data && <div className="glass-card p-8 text-center text-sm text-gray-400">Starting full-market scan…</div>}
      {!loading && !data?.scanning && !error && displayedRecommendations.length === 0 && <div className="glass-card p-8 text-center text-sm text-gray-400">No stock currently has a Technical pillar score of 95 or higher. Titan X will show a recommendation only when the Technical pillar score is ≥95.</div>}
      {!error && !data?.scanning && displayedRecommendations.length > 0 && <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">{displayedRecommendations.map((rec) => <RecommendationCard key={`${rec.segment}-${rec.symbol}-${rec.instrument}`} rec={rec} />)}</div>}
      {error && <div className="glass-card p-6 text-center text-sm text-red-400">{error}</div>}
      <div className="text-[10px] text-gray-600 px-1">Strict recommendations use the actual Technical Pillar Score shown in Titan X. Confidence is not used for the 95+ gate.</div>
    </div>
  )
}
