"use client"

import { useEffect, useState } from "react"
import { Activity, ShieldCheck, Target, TrendingDown, TrendingUp } from "lucide-react"
import api from "@/lib/api"

type FrameResult = {
  decision: "BUY" | "SELL" | "HOLD"
  reason: string
  entry: number | null
  stop_loss: number | null
  target: number | null
  price: number | null
  regime: string
  gates?: Record<string, boolean | string>
}

type MtfSignal = {
  symbol: string
  decision: "BUY" | "SELL" | "HOLD"
  reason: string
  entry: number | null
  stop_loss: number | null
  target: number | null
  price: number | null
  regime: string
  confirmed: boolean
  timeframes: Record<"5m" | "15m" | "30m", FrameResult>
  rule: string
}

export default function TitanXFusion({ symbol }: { symbol: string }) {
  const [data, setData] = useState<MtfSignal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.get<MtfSignal>(
          `/fusion-mtf/signal?symbol=${encodeURIComponent(symbol)}`,
        )
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
  }, [symbol])

  const signal = data?.decision ?? "HOLD"
  const isBuy = signal === "BUY"
  const isSell = signal === "SELL"
  const frames = data?.timeframes

  return (
    <section className="glass-card p-5 border border-cyan-500/20 bg-cyan-500/[0.025]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity size={17} className="text-cyan-300" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Titan X Fusion</h3>
            <span className="text-[9px] rounded-full border border-cyan-500/25 px-2 py-0.5 text-cyan-300">PHASE 4 MTF</span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">5m + 15m + 30m independent confirmation</p>
        </div>
        <div className="text-[9px] text-gray-500 uppercase tracking-widest">
          {data?.confirmed ? "Alignment confirmed" : "Waiting for alignment"}
        </div>
      </div>

      {loading && !data ? (
        <div className="mt-4 h-32 animate-pulse rounded-lg bg-white/5" />
      ) : error ? (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-xs text-amber-300">{error}</div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className={`rounded-xl border p-4 md:col-span-1 ${
              isBuy ? "border-emerald-400/40 bg-emerald-400/10" :
              isSell ? "border-rose-400/40 bg-rose-400/10" :
              "border-white/10 bg-white/[0.03]"
            }`}>
              <div className="text-[9px] uppercase tracking-widest text-gray-500">MTF decision</div>
              <div className={`mt-1 text-2xl font-black ${
                isBuy ? "text-emerald-300" : isSell ? "text-rose-300" : "text-gray-200"
              }`}>
                {isBuy ? <TrendingUp className="inline mr-2" size={20} /> :
                 isSell ? <TrendingDown className="inline mr-2" size={20} /> :
                 <ShieldCheck className="inline mr-2" size={20} />}
                {signal}
              </div>
              <div className="text-[10px] text-gray-500 mt-1">{data?.regime ?? "UNKNOWN"}</div>
            </div>

            <div className="md:col-span-2 rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-[9px] uppercase tracking-widest text-gray-500">Confirmation rule</div>
              <div className="mt-2 text-sm text-gray-300">{data?.reason}</div>
              <div className="mt-2 text-[10px] text-gray-600">{data?.rule}</div>
              {isBuy || isSell ? (
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div><span className="text-gray-500">Entry</span><div className="text-white font-semibold">{data?.entry ?? "—"}</div></div>
                  <div><span className="text-gray-500">Stop</span><div className="text-white font-semibold">{data?.stop_loss ?? "—"}</div></div>
                  <div><span className="text-gray-500">Target</span><div className="text-cyan-200 font-semibold">{data?.target ?? "—"}</div></div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            {(["5m", "15m", "30m"] as const).map((tf) => {
              const frame = frames?.[tf]
              const value = frame?.decision ?? "HOLD"
              const active = value === signal && value !== "HOLD"
              return (
                <div key={tf} className={`rounded-lg border px-3 py-3 ${
                  active ? "border-cyan-400/30 bg-cyan-400/5" : "border-white/5 bg-white/[0.025]"
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] uppercase tracking-widest text-gray-500">{tf}</span>
                    <span className={`text-[10px] font-bold ${
                      value === "BUY" ? "text-emerald-300" : value === "SELL" ? "text-rose-300" : "text-gray-400"
                    }`}>{value}</span>
                  </div>
                  <div className="text-[9px] text-gray-600 mt-1 truncate">{frame?.regime ?? "UNKNOWN"}</div>
                </div>
              )
            })}
          </div>

          <div className="mt-3 text-[9px] text-gray-600">
            Real OHLCV · Same gate-based Fusion engine on each timeframe · no synthetic signal scoring
          </div>
        </>
      )}
    </section>
  )
}
