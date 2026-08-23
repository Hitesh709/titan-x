"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import api from "@/lib/api"

export type Candle = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const INTERVALS = [
  { key: "5m", label: "5m" },
  { key: "15m", label: "15m" },
  { key: "30m", label: "30m" },
  { key: "1h", label: "1h" },
  { key: "4h", label: "4h" },
  { key: "1d", label: "1D" },
  { key: "1w", label: "1W" },
  { key: "1mo", label: "1M" },
] as const

const PERIODS = [
  { key: "1d", label: "1D" },
  { key: "5d", label: "5D" },
  { key: "1mo", label: "1M" },
  { key: "3mo", label: "3M" },
  { key: "6mo", label: "6M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
  { key: "max", label: "From Beginning" },
] as const

function niceNumber(value: number) {
  if (value >= 1000) return value.toLocaleString("en-IN", { maximumFractionDigits: 2 })
  return value.toFixed(2)
}

export default function CandlestickChart({ symbol }: { symbol: string }) {
  const [interval, setInterval] = useState("1d")
  const [period, setPeriod] = useState("3mo")
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hovered, setHovered] = useState<Candle | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    api.get<{ candles: Candle[] }>(`/market-data/candles/${encodeURIComponent(symbol)}?interval=${interval}&period=${period}`)
      .then((res) => {
        if (!active) return
        setCandles(res.candles ?? [])
      })
      .catch((e) => {
        if (!active) return
        setCandles([])
        setError(e instanceof Error ? e.message : "Candle data unavailable")
      })
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [symbol, interval, period])

  const visible = useMemo(() => candles.slice(-180), [candles])
  const min = visible.length ? Math.min(...visible.map((c) => c.low)) : 0
  const max = visible.length ? Math.max(...visible.map((c) => c.high)) : 1
  const width = 1000
  const height = 360
  const pad = { left: 64, right: 20, top: 24, bottom: 34 }
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom
  const y = (value: number) => pad.top + ((max - value) / Math.max(max - min, 0.000001)) * plotH
  const step = visible.length ? plotW / visible.length : plotW
  const candleWidth = Math.max(2, Math.min(12, step * 0.62))

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {INTERVALS.map((item) => (
          <button
            key={item.key}
            onClick={() => setInterval(item.key)}
            className={`px-2.5 py-1.5 rounded-md text-[11px] font-medium border ${interval === item.key ? "bg-titan-600/25 text-titan-300 border-titan-500/40" : "bg-white/5 text-gray-400 border-white/10 hover:text-white"}`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5 mb-4">
        {PERIODS.map((item) => (
          <button
            key={item.key}
            onClick={() => setPeriod(item.key)}
            className={`px-2.5 py-1 rounded-md text-[10px] border ${period === item.key ? "bg-white/10 text-white border-white/20" : "text-gray-500 border-white/5 hover:text-gray-300"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-white/5 bg-[#070b18] overflow-hidden">
        {loading ? (
          <div className="h-80 flex items-center justify-center text-sm text-gray-500">Loading real OHLCV candles…</div>
        ) : error ? (
          <div className="h-80 flex flex-col items-center justify-center gap-2 text-sm text-gray-500 px-6 text-center">
            <span>{error}</span>
            {(interval === "5m" || interval === "15m" || interval === "30m") && <span className="text-xs text-amber-400/80">Intraday history is limited by the market-data provider. Try a shorter period.</span>}
          </div>
        ) : visible.length === 0 ? (
          <div className="h-80 flex items-center justify-center text-sm text-gray-500">No real candle data available.</div>
        ) : (
          <div className="relative">
            <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} className="w-full h-[360px]" preserveAspectRatio="none">
              {[0, 0.25, 0.5, 0.75, 1].map((p) => {
                const value = max - (max - min) * p
                const yy = y(value)
                return <g key={p}><line x1={pad.left} x2={width - pad.right} y1={yy} y2={yy} stroke="rgba(255,255,255,0.06)" /><text x={6} y={yy + 4} fill="#6b7280" fontSize="12">{niceNumber(value)}</text></g>
              })}
              {visible.map((candle, index) => {
                const x = pad.left + index * step + step / 2
                const rising = candle.close >= candle.open
                const bodyTop = y(Math.max(candle.open, candle.close))
                const bodyBottom = y(Math.min(candle.open, candle.close))
                const bodyHeight = Math.max(1.5, bodyBottom - bodyTop)
                const color = rising ? "#22c55e" : "#ef4444"
                return (
                  <g key={`${candle.time}-${index}`} onMouseEnter={() => setHovered(candle)} onMouseLeave={() => setHovered(null)}>
                    <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth={Math.max(1, candleWidth * 0.12)} />
                    <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={color} rx={0.7} />
                  </g>
                )
              })}
              {visible.filter((_, i) => i % Math.max(1, Math.ceil(visible.length / 7)) === 0).map((candle, i) => {
                const index = visible.indexOf(candle)
                const x = pad.left + index * step + step / 2
                const label = new Date(candle.time).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })
                return <text key={`${candle.time}-label-${i}`} x={x} y={height - 10} textAnchor="middle" fill="#6b7280" fontSize="11">{label}</text>
              })}
            </svg>
            {hovered && (
              <div className="absolute top-3 right-3 bg-slate-950/95 border border-white/10 rounded-lg px-3 py-2 text-[11px] shadow-xl">
                <div className="text-gray-400 mb-1">{new Date(hovered.time).toLocaleString("en-IN")}</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-white">
                  <span>O {niceNumber(hovered.open)}</span><span>H {niceNumber(hovered.high)}</span>
                  <span>L {niceNumber(hovered.low)}</span><span>C {niceNumber(hovered.close)}</span>
                  <span className="col-span-2 text-gray-400">Vol {hovered.volume.toLocaleString("en-IN")}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-500">
        <span><i className="inline-block w-2 h-2 rounded-sm bg-green-500 mr-1" />Up / Bullish</span>
        <span><i className="inline-block w-2 h-2 rounded-sm bg-red-500 mr-1" />Down / Bearish</span>
        <span className="ml-auto">Source: Yahoo Finance · real OHLCV</span>
      </div>
    </div>
  )
}
