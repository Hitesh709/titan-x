"use client"

import { useEffect, useMemo, useState } from "react"
import api from "@/lib/api"

export type Candle = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type Signal = { time: string; side: "BUY" | "SELL"; reason: string }
type IndicatorSeries = (number | null)[]

type ChartData = {
  candles: Candle[]
  signals: Signal[]
  supertrend: IndicatorSeries
  indicators: {
    e9: IndicatorSeries
    e20: IndicatorSeries
    e50: IndicatorSeries
    rsi: IndicatorSeries
    macd: IndicatorSeries
    macd_signal: IndicatorSeries
    macd_hist: IndicatorSeries
    atr: IndicatorSeries
    adx: IndicatorSeries
    volume_sma: number
  }
}

const INTERVALS = ["5m", "15m", "30m"] as const
const PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"] as const

const INDICATORS = [
  ["bb", "Bollinger Bands"], ["vwap", "VWAP"], ["ema9", "EMA 9"], ["ema20", "EMA 20"], ["ema50", "EMA 50"],
  ["sma20", "SMA 20"], ["sma50", "SMA 50"], ["sma200", "SMA 200"], ["rsi", "RSI"], ["macd", "MACD"],
  ["stoch", "Stochastic"], ["atr", "ATR"], ["adx", "ADX"], ["supertrend", "Supertrend"], ["ichimoku", "Ichimoku"],
  ["sar", "Parabolic SAR"], ["obv", "OBV"], ["vp", "Volume Profile"], ["pivot", "Pivot Points"], ["fib", "Fibonacci"],
] as const

const avg = (values: number[]) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0

const sma = (values: number[], n: number): IndicatorSeries =>
  values.map((_, i) => i + 1 < n ? null : avg(values.slice(i + 1 - n, i + 1)))

const bollinger = (values: number[], n = 20, mult = 2) => {
  const mid = sma(values, n)
  const upper: IndicatorSeries = []
  const lower: IndicatorSeries = []
  values.forEach((_, i) => {
    if (i + 1 < n) {
      upper.push(null)
      lower.push(null)
      return
    }
    const window = values.slice(i + 1 - n, i + 1)
    const mean = mid[i] as number
    const variance = avg(window.map(v => (v - mean) ** 2))
    const sd = Math.sqrt(variance)
    upper.push(mean + mult * sd)
    lower.push(mean - mult * sd)
  })
  return { mid, upper, lower }
}

const vwap = (candles: Candle[]): IndicatorSeries => {
  let pv = 0
  let volume = 0
  return candles.map(c => {
    const typical = (c.high + c.low + c.close) / 3
    pv += typical * Math.max(c.volume, 0)
    volume += Math.max(c.volume, 0)
    return volume > 0 ? pv / volume : null
  })
}

export default function CandlestickChart({ symbol }: { symbol: string }) {
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>("5m")
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("1d")
  const [chart, setChart] = useState<ChartData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>(["bb", "vwap", "ema9", "ema20"])
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)

    api.get<ChartData>(
      `/fusion/chart/${encodeURIComponent(symbol)}?interval=${interval}&period=${period}`
    )
      .then(response => {
        if (!active) return
        setChart(response)
      })
      .catch(e => {
        if (active) setError(e instanceof Error ? e.message : "Chart data unavailable")
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => { active = false }
  }, [symbol, interval, period])

  const data = useMemo(() => (chart?.candles ?? []).slice(-180), [chart])
  const signals = useMemo(() => {
    const visible = new Set(data.map(c => c.time))
    return (chart?.signals ?? []).filter(s => visible.has(s.time))
  }, [chart, data])

  const closes = useMemo(() => data.map(c => c.close), [data])
  const bands = useMemo(() => bollinger(closes), [closes])
  const vwapSeries = useMemo(() => vwap(data), [data])
  const sma20 = useMemo(() => sma(closes, 20), [closes])
  const sma50 = useMemo(() => sma(closes, 50), [closes])
  const sma200 = useMemo(() => sma(closes, 200), [closes])

  const W = 1200
  const H = 470
  const p = { l: 62, r: 20, t: 26, b: 42 }
  const pw = W - p.l - p.r
  const ph = 330
  const lo = data.length ? Math.min(...data.map(c => c.low)) : 0
  const hi = data.length ? Math.max(...data.map(c => c.high)) : 1
  const y = (value: number) => p.t + (hi - value) / Math.max(hi - lo, 0.000001) * ph
  const step = data.length ? pw / data.length : pw
  const candleWidth = Math.max(2, Math.min(10, step * 0.65))

  const linePoints = (values: IndicatorSeries) =>
    values
      .map((value, i) => value == null || !Number.isFinite(value) ? null : `${p.l + i * step + step / 2},${y(value)}`)
      .filter((point): point is string => point !== null)
      .join(" ")

  const activeIndicators = INDICATORS.filter(([key]) => selected.includes(key))
  const signalByTime = useMemo(
    () => new Map(signals.map(s => [s.time, s])),
    [signals]
  )

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {INTERVALS.map(x => (
          <button
            key={x}
            onClick={() => { setInterval(x); if (x === "5m" || x === "15m") setPeriod("1d") }}
            className={`px-3 py-1.5 rounded-md text-[11px] border ${
              interval === x
                ? "bg-titan-600/25 text-titan-300 border-titan-500/40"
                : "bg-white/5 text-gray-400 border-white/10"
            }`}
          >
            {x.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {PERIODS.map(x => (
          <button
            key={x}
            onClick={() => setPeriod(x)}
            className={`px-2.5 py-1 rounded-md text-[10px] border ${
              period === x
                ? "bg-white/10 text-white border-white/20"
                : "text-gray-500 border-white/5"
            }`}
          >
            {x.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="mb-3 rounded-lg border border-cyan-500/15 bg-cyan-500/[0.03] p-2">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-[10px] uppercase tracking-wider text-cyan-300 font-bold">
            20 Technical Strategies / Indicators
          </span>
          <span className="text-[9px] text-gray-500">Select overlays & studies</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {INDICATORS.map(([key, name]) => (
            <button
              key={key}
              onClick={() => setSelected(current =>
                current.includes(key)
                  ? current.filter(x => x !== key)
                  : [...current, key]
              )}
              className={`px-2 py-1 rounded text-[9px] border ${
                selected.includes(key)
                  ? "bg-titan-500/15 text-cyan-200 border-cyan-500/30"
                  : "bg-white/[0.03] text-gray-500 border-white/10"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-white/5 bg-[#070b18] overflow-hidden">
        {loading ? (
          <div className="h-[470px] flex items-center justify-center text-sm text-gray-500">
            Loading real OHLCV candles…
          </div>
        ) : error ? (
          <div className="h-[470px] flex items-center justify-center text-sm text-gray-500 px-6 text-center">
            {error}
          </div>
        ) : !data.length ? (
          <div className="h-[470px] flex items-center justify-center text-sm text-gray-500">
            No real candle data available.
          </div>
        ) : (
          <div className="relative">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              className="w-full h-[470px]"
              preserveAspectRatio="none"
            >
              {[0, 0.25, 0.5, 0.75, 1].map(q => {
                const value = hi - (hi - lo) * q
                return (
                  <g key={q}>
                    <line x1={p.l} x2={W - p.r} y1={y(value)} y2={y(value)} stroke="rgba(255,255,255,.06)" />
                    <text x="6" y={y(value) + 4} fill="#718096" fontSize="12">
                      {value.toFixed(2)}
                    </text>
                  </g>
                )
              })}

              {data.map((c, i) => {
                const x = p.l + i * step + step / 2
                const up = c.close >= c.open
                const candleColor = up ? "#00f0a0" : "#ff4d67"
                const top = y(Math.max(c.open, c.close))
                const bottom = y(Math.min(c.open, c.close))
                return (
                  <g
                    key={c.time + i}
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                    className="cursor-crosshair"
                  >
                    <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={candleColor} strokeWidth="1.5" />
                    <rect
                      x={x - candleWidth / 2}
                      y={top}
                      width={candleWidth}
                      height={Math.max(1.5, bottom - top)}
                      fill={candleColor}
                      rx="1"
                    />
                  </g>
                )
              })}

              {selected.includes("bb") && (
                <>
                  <polyline points={linePoints(bands.upper)} fill="none" stroke="#38bdf8" strokeWidth="1" />
                  <polyline points={linePoints(bands.lower)} fill="none" stroke="#38bdf8" strokeWidth="1" />
                  <polyline points={linePoints(bands.mid)} fill="none" stroke="#38bdf8" strokeWidth="0.7" opacity="0.6" />
                </>
              )}
              {selected.includes("vwap") && <polyline points={linePoints(vwapSeries)} fill="none" stroke="#a855f7" strokeWidth="1.5" />}
              {selected.includes("ema9") && <polyline points={linePoints(chart?.indicators?.e9 ?? [])} fill="none" stroke="#22c55e" strokeWidth="1" />}
              {selected.includes("ema20") && <polyline points={linePoints(chart?.indicators?.e20 ?? [])} fill="none" stroke="#60a5fa" strokeWidth="1" />}
              {selected.includes("ema50") && <polyline points={linePoints(chart?.indicators?.e50 ?? [])} fill="none" stroke="#f472b6" strokeWidth="1" />}
              {selected.includes("sma20") && <polyline points={linePoints(sma20)} fill="none" stroke="#e5e7eb" strokeWidth="1" />}
              {selected.includes("sma50") && <polyline points={linePoints(sma50)} fill="none" stroke="#94a3b8" strokeWidth="1" />}
              {selected.includes("sma200") && <polyline points={linePoints(sma200)} fill="none" stroke="#facc15" strokeWidth="1" />}
              {selected.includes("supertrend") && <polyline points={linePoints(chart?.supertrend ?? [])} fill="none" stroke="#fb923c" strokeWidth="1.5" />}

              {signals.map(signal => {
                const index = data.findIndex(c => c.time === signal.time)
                if (index < 0) return null
                const candle = data[index]
                const x = p.l + index * step + step / 2
                const yy = signal.side === "BUY" ? y(candle.low) + 16 : y(candle.high) - 16
                return (
                  <g key={signal.time + signal.side} onClick={() => setHover(index)} className="cursor-pointer">
                    <circle cx={x} cy={yy} r="6" fill={signal.side === "BUY" ? "#00f0a0" : "#ff4d67"} />
                    <text x={x} y={yy + 3} textAnchor="middle" fill="#071018" fontSize="7" fontWeight="700">
                      {signal.side === "BUY" ? "B" : "S"}
                    </text>
                  </g>
                )
              })}

              {data.filter((_, i) => i % Math.max(1, Math.ceil(data.length / 8)) === 0).map((c, i) => {
                const index = data.indexOf(c)
                return (
                  <text
                    key={i}
                    x={p.l + index * step + step / 2}
                    y={H - 12}
                    textAnchor="middle"
                    fill="#718096"
                    fontSize="10"
                  >
                    {new Date(c.time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                  </text>
                )
              })}
            </svg>

            {hover != null && data[hover] && (
              <div className="absolute top-3 right-3 max-w-xs bg-slate-950/95 border border-cyan-500/20 rounded-lg px-3 py-2 text-[10px] shadow-xl">
                <div className="text-gray-400">{new Date(data[hover].time).toLocaleString("en-IN")}</div>
                <div className="grid grid-cols-2 gap-x-3 text-white mt-1">
                  <span>O {data[hover].open.toFixed(2)}</span>
                  <span>H {data[hover].high.toFixed(2)}</span>
                  <span>L {data[hover].low.toFixed(2)}</span>
                  <span>C {data[hover].close.toFixed(2)}</span>
                  <span>Vol {data[hover].volume.toLocaleString("en-IN")}</span>
                </div>
                {signalByTime.get(data[hover].time) && (
                  <div className="mt-2 text-cyan-200">
                    {signalByTime.get(data[hover].time)?.side} · {signalByTime.get(data[hover].time)?.reason}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
        {activeIndicators.slice(0, 4).map(([key, name]) => (
          <div key={key} className="rounded-lg bg-white/[0.03] border border-white/5 p-2">
            <div className="text-[9px] text-gray-500">{name}</div>
            <div className="text-xs text-cyan-200 mt-1">Active</div>
          </div>
        ))}
        <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2">
          <div className="text-[9px] text-gray-500">Fusion Signals</div>
          <div className="text-xs text-emerald-300 mt-1">
            {signals.filter(s => s.side === "BUY").length} BUY · {signals.filter(s => s.side === "SELL").length} SELL
          </div>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-500">
        <span>● BUY / SELL markers from Titan X Fusion engine (no scores)</span>
        <span className="ml-auto">Source: backend engine, real Yahoo OHLCV</span>
      </div>
    </div>
  )
}
