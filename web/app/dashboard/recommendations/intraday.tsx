"use client"

import { useCallback, useEffect, useState } from "react"
import { RefreshCw, TrendingDown, TrendingUp, Zap, Clock3, AlertTriangle } from "lucide-react"
import api from "@/lib/api"
import type { IntradayRecommendation, IntradayRecommendationsResponse } from "@/types"

function money(value: number) {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
}

function RecommendationCard({ rec }: { rec: IntradayRecommendation }) {
  const bullish = rec.direction === "BUY"
  const bearish = rec.direction === "SELL"
  const directionClass = bullish ? "badge-green" : bearish ? "badge-red" : "badge-blue"

  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">
              {rec.symbol.slice(0, 4)}
            </span>
            <div>
              <div className="text-white font-semibold">{rec.symbol}</div>
              <div className="text-[11px] text-gray-500">
                {rec.instrument} · {rec.timeframe}
              </div>
            </div>
          </div>
        </div>
        <span className={`badge ${directionClass}`}>
          {bullish ? <TrendingUp size={12} className="inline mr-1" /> : bearish ? <TrendingDown size={12} className="inline mr-1" /> : null}
          {rec.direction}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <div>
          <div className="text-[11px] text-gray-500">Current</div>
          <div className="text-lg font-semibold text-white">{money(rec.current_price)}</div>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-gray-500">AI score / confidence</div>
          <div className="text-sm font-semibold text-titan-300">{rec.score.toFixed(0)} / {rec.confidence.toFixed(0)}%</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-4">
        <div className="rounded-lg bg-white/[0.03] p-2">
          <div className="text-[10px] text-gray-500">Entry</div>
          <div className="text-xs text-white mt-1">{money(rec.entry_price)}</div>
        </div>
        <div className="rounded-lg bg-emerald-500/[0.05] p-2">
          <div className="text-[10px] text-gray-500">Target</div>
          <div className="text-xs text-emerald-300 mt-1">{money(rec.target_price)}</div>
        </div>
        <div className="rounded-lg bg-red-500/[0.05] p-2">
          <div className="text-[10px] text-gray-500">Stop</div>
          <div className="text-xs text-red-300 mt-1">{money(rec.stop_price)}</div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 mt-3 text-[11px]">
        <div><span className="text-gray-500">RSI</span><div className="text-gray-200 mt-0.5">{rec.rsi?.toFixed(1) ?? "—"}</div></div>
        <div><span className="text-gray-500">EMA20</span><div className="text-gray-200 mt-0.5">{rec.ema20 ? money(rec.ema20) : "—"}</div></div>
        <div><span className="text-gray-500">EMA50</span><div className="text-gray-200 mt-0.5">{rec.ema50 ? money(rec.ema50) : "—"}</div></div>
        <div><span className="text-gray-500">Vol</span><div className="text-gray-200 mt-0.5">{rec.volume_ratio.toFixed(1)}x</div></div>
      </div>

      {rec.segment === "fno" && (
        <div className="mt-4 rounded-lg border border-titan-500/20 bg-titan-500/[0.04] p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-titan-300">F&O Strategy</span>
            <span className="text-xs text-white">{rec.option_bias === "CALL" ? "CALL bias" : rec.option_bias === "PUT" ? "PUT bias" : "No option bias"}</span>
          </div>
          <div className="mt-1 text-[11px] text-gray-400">
            Futures: {bullish ? "LONG" : bearish ? "SHORT" : "WAIT"}
            {rec.option_strike ? ` · ATM candidate ${rec.option_strike}` : ""}
          </div>
          <div className="mt-2 text-[10px] text-gray-500">Option premium/expiry is shown only when live derivatives-chain data is available.</div>
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-white/5">
        <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">Why</div>
        <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
          {rec.evidence.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
        </ul>
        {rec.caution.length > 0 && (
          <div className="mt-2 flex gap-2 text-[11px] text-amber-300">
            <AlertTriangle size={13} className="shrink-0 mt-0.5" />
            <span>{rec.caution[0]}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function IntradayRecommendations() {
  const [segment, setSegment] = useState<"equity" | "fno">("equity")
  const [data, setData] = useState<IntradayRecommendationsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<IntradayRecommendationsResponse>(`/recommendations/intraday?segment=${segment}&limit=10`)
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load intraday recommendations")
    } finally {
      setLoading(false)
    }
  }, [segment])

  useEffect(() => { void load() }, [load])

  return (
    <div className="space-y-5">
      <div className="glass-card p-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-white font-semibold flex items-center gap-2"><Zap size={15} className="text-titan-400" /> Intraday AI</div>
          <div className="text-xs text-gray-500 mt-1">5-minute market structure · momentum · volume · risk filters</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-white/10 p-1 bg-white/[0.02]">
            <button onClick={() => setSegment("equity")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "equity" ? "bg-titan-600 text-white" : "text-gray-400"}`}>Equity Intraday</button>
            <button onClick={() => setSegment("fno")} className={`px-3 py-1.5 rounded-md text-xs ${segment === "fno" ? "bg-titan-600 text-white" : "text-gray-400"}`}>F&O Intraday</button>
          </div>
          <button onClick={() => void load()} className="btn-secondary text-xs inline-flex items-center gap-2"><RefreshCw size={13} /> Refresh</button>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="glass-card p-4"><div className="text-[11px] text-gray-500">Universe</div><div className="text-xl text-white font-semibold mt-1">{data.universe_size}</div></div>
          <div className="glass-card p-4"><div className="text-[11px] text-gray-500">Scanned</div><div className="text-xl text-white font-semibold mt-1">{data.scanned}</div></div>
          <div className="glass-card p-4"><div className="text-[11px] text-gray-500">Signals</div><div className="text-xl text-emerald-400 font-semibold mt-1">{data.recommendations.length}</div></div>
          <div className="glass-card p-4"><div className="text-[11px] text-gray-500 flex items-center gap-1"><Clock3 size={12} /> Generated</div><div className="text-xs text-gray-300 mt-2">{new Date(data.generated_at).toLocaleTimeString()}</div></div>
        </div>
      )}

      {loading && <div className="glass-card p-8 text-center text-sm text-gray-400">Scanning live 5m data…</div>}
      {error && !loading && <div className="glass-card p-6 text-center text-sm text-red-400">{error}</div>}
      {!loading && !error && data?.recommendations.length === 0 && (
        <div className="glass-card p-8 text-center text-sm text-gray-400">No qualified intraday signal right now. TitanX prefers NO-TRADE over weak signals.</div>
      )}
      {!loading && !error && data?.recommendations.length ? (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {data.recommendations.map((rec) => <RecommendationCard key={`${rec.segment}-${rec.symbol}-${rec.instrument}`} rec={rec} />)}
        </div>
      ) : null}

      <div className="text-[10px] text-gray-600 px-1">Intraday signals are generated from live 5-minute OHLCV data and are separate from TitanX delivery/short-term recommendations.</div>
    </div>
  )
}
