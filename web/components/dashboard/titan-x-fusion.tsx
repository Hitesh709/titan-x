"use client"

import { useEffect, useState } from "react"
import { Activity, ShieldCheck, Target, TrendingDown, TrendingUp } from "lucide-react"
import api from "@/lib/api"

export type FusionSignal = {
  symbol: string
  strategy: "Titan X Fusion"
  signal: "BUY" | "SELL" | "HOLD"
  timeframe: string
  entry: number | null
  stop_loss: number | null
  target: number | null
  reason: string
  regime: string
  confirmed: boolean
  data_points: number
}

export default function TitanXFusion({ symbol }: { symbol: string }) {
  const [timeframe, setTimeframe] = useState<"5m" | "15m">("5m")
  const [data, setData] = useState<FusionSignal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.get<FusionSignal>(`/market-data/fusion/${encodeURIComponent(symbol)}?interval=${timeframe}`)
        if (active) setData(result)
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Fusion signal unavailable")
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    const timer = window.setInterval(load, 30000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [symbol, timeframe])

  const signal = data?.signal ?? "HOLD"
  const isBuy = signal === "BUY"
  const isSell = signal === "SELL"

  return (
    <section className="glass-card p-5 border border-cyan-500/20 bg-cyan-500/[0.025]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity size={17} className="text-cyan-300" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Titan X Fusion</h3>
            <span className="text-[9px] rounded-full border border-cyan-500/25 px-2 py-0.5 text-cyan-300">INTRADAY ONLY</span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">One confirmation-based engine · BUY / SELL / HOLD</p>
        </div>
        <div className="flex gap-1.5">
          {(["5m", "15m"] as const).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-1.5 rounded-md text-[10px] border ${timeframe === tf ? "bg-cyan-500/15 text-cyan-200 border-cyan-500/35" : "bg-white/5 text-gray-500 border-white/10"}`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? (
        <div className="mt-4 h-24 animate-pulse rounded-lg bg-white/5" />
      ) : error ? (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-xs text-amber-300">{error}</div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className={`rounded-xl border p-4 ${isBuy ? "border-emerald-400/40 bg-emerald-400/10" : isSell ? "border-rose-400/40 bg-rose-400/10" : "border-white/10 bg-white/[0.03]"}`}>
              <div className="text-[9px] uppercase tracking-widest text-gray-500">Current decision</div>
              <div className={`mt-1 text-2xl font-black ${isBuy ? "text-emerald-300" : isSell ? "text-rose-300" : "text-gray-200"}`}>
                {isBuy ? <TrendingUp className="inline mr-2" size={20} /> : isSell ? <TrendingDown className="inline mr-2" size={20} /> : <ShieldCheck className="inline mr-2" size={20} />}
                {signal}
              </div>
              <div className="text-[10px] text-gray-500 mt-1">{data?.regime ?? "UNKNOWN"} · {timeframe}</div>
            </div>

            {isBuy || isSell ? (
              <>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="text-[9px] uppercase tracking-widest text-gray-500">Entry / Stop</div>
                  <div className="mt-1 text-sm font-bold text-white">{data?.entry ?? "—"}</div>
                  <div className="text-xs text-gray-400 mt-1">Stop Loss: <span className="text-white">{data?.stop_loss ?? "—"}</span></div>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="text-[9px] uppercase tracking-widest text-gray-500">Target</div>
                  <div className="mt-1 text-sm font-bold text-cyan-200">{data?.target ?? "—"}</div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-1"><Target size={12} /> Protected by risk filter</div>
                </div>
              </>
            ) : (
              <div className="md:col-span-2 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[9px] uppercase tracking-widest text-gray-500">Why Titan X is waiting</div>
                <div className="mt-2 text-sm text-gray-300">{data?.reason ?? "Market structure is not sufficiently confirmed"}</div>
              </div>
            )}
          </div>

          {(isBuy || isSell) && data?.reason && (
            <div className="mt-3 rounded-lg bg-white/[0.025] border border-white/5 p-3 text-xs text-gray-400">{data.reason}</div>
          )}
          <div className="mt-3 text-[9px] text-gray-600">Real OHLCV · {data?.data_points ?? 0} data points · No signal score · Signal uses closed-candle confirmation</div>
        </>
      )}
    </section>
  )
}
