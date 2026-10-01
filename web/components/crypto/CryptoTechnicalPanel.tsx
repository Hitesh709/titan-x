"use client"

import { useEffect, useMemo, useState } from "react"
import api from "@/lib/api"

type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number }
type Decision = "BUY" | "SELL" | "HOLD"
type Signal = { tf: string; decision: Decision; reason: string; trend: string }
type Marker = { index: number; decision: "BUY" | "SELL"; price: number; reason: string }

const TF = ["5m", "15m", "30m"] as const
const INDICATORS = [
  "Bollinger Bands", "VWAP", "EMA 9", "EMA 20", "EMA 50", "SMA 20", "SMA 50", "SMA 200",
  "RSI", "MACD", "Stochastic", "ATR", "ADX", "Supertrend", "Ichimoku Cloud", "Parabolic SAR",
  "OBV", "Volume Profile", "Pivot Points", "Fibonacci Retracement",
]

function ema(a: number[], n: number) {
  if (!a.length) return []
  const k = 2 / (n + 1)
  const o: number[] = []
  let e = a[0]
  for (let i = 0; i < a.length; i++) {
    e = i ? e + (a[i] - e) * k : a[i]
    o.push(e)
  }
  return o
}

function sma(a: number[], n: number) {
  return a.map((_, i) => i < n - 1 ? NaN : a.slice(i - n + 1, i + 1).reduce((x, y) => x + y, 0) / n)
}

function rsi(a: number[], n = 14) {
  const o = Array(a.length).fill(NaN) as number[]
  let gain = 0
  let loss = 0
  for (let i = 1; i < a.length; i++) {
    const d = a[i] - a[i - 1]
    if (i <= n) {
      gain += Math.max(d, 0)
      loss += Math.max(-d, 0)
      if (i === n) o[i] = loss ? 100 - 100 / (1 + gain / loss) : 100
    } else {
      gain = (gain * (n - 1) + Math.max(d, 0)) / n
      loss = (loss * (n - 1) + Math.max(-d, 0)) / n
      o[i] = loss ? 100 - 100 / (1 + gain / loss) : 100
    }
  }
  return o
}

function atr(c: Candle[], n = 14) {
  const tr = c.map((x, i) => i
    ? Math.max(x.high - x.low, Math.abs(x.high - c[i - 1].close), Math.abs(x.low - c[i - 1].close))
    : x.high - x.low)
  return sma(tr, n)
}

function macd(a: number[]) {
  const fast = ema(a, 12)
  const slow = ema(a, 26)
  const line = a.map((_, i) => fast[i] - slow[i])
  const signal = ema(line, 9)
  return { line, signal, hist: line.map((x, i) => x - signal[i]) }
}

function adx(c: Candle[], n = 14) {
  const tr = c.map((x, i) => i ? Math.max(x.high - x.low, Math.abs(x.high - c[i - 1].close), Math.abs(x.low - c[i - 1].close)) : x.high - x.low)
  const plus = c.map((x, i) => i ? Math.max(x.high - c[i - 1].high, 0) : 0)
  const minus = c.map((x, i) => i ? Math.max(c[i - 1].low - x.low, 0) : 0)
  const atrs = sma(tr, n)
  const p = sma(plus, n)
  const m = sma(minus, n)
  return c.map((_, i) => {
    if (!Number.isFinite(atrs[i])) return NaN
    const pdi = 100 * (p[i] || 0) / Math.max(atrs[i], 1e-9)
    const mdi = 100 * (m[i] || 0) / Math.max(atrs[i], 1e-9)
    return 100 * Math.abs(pdi - mdi) / Math.max(pdi + mdi, 1)
  })
}

function calc(c: Candle[]) {
  const close = c.map(x => x.close)
  const high = c.map(x => x.high)
  const low = c.map(x => x.low)
  const vol = c.map(x => x.volume)
  const i = c.length - 1

  const e9 = ema(close, 9)
  const e20 = ema(close, 20)
  const e50 = ema(close, 50)
  const s20 = sma(close, 20)
  const s50 = sma(close, 50)
  const s200 = sma(close, 200)
  const r = rsi(close)
  const a = atr(c)
  const { line: macdLine, signal: macdSignal } = macd(close)
  const adxLine = adx(c)
  const v = sma(vol, 20)

  const mean20 = s20[i]
  const sd = Math.sqrt(close.slice(Math.max(0, i - 19), i + 1).reduce((s, x) => s + (x - mean20) ** 2, 0) / Math.min(20, i + 1))
  const upper = mean20 + 2 * sd
  const lower = mean20 - 2 * sd

  const pv = c.reduce((s, x) => s + ((x.high + x.low + x.close) / 3) * x.volume, 0)
  const tv = c.reduce((s, x) => s + x.volume, 0)
  const vwap = pv / Math.max(tv, 1)

  const lo14 = Math.min(...low.slice(Math.max(0, i - 13), i + 1))
  const hi14 = Math.max(...high.slice(Math.max(0, i - 13), i + 1))
  const stoch = hi14 === lo14 ? 50 : ((close[i] - lo14) / (hi14 - lo14)) * 100

  const hi20 = Math.max(...high.slice(Math.max(0, i - 20), i))
  const lo20 = Math.min(...low.slice(Math.max(0, i - 20), i))
  const bullishBreakout = close[i] > hi20
  const bearishBreakout = close[i] < lo20

  const supertrendUp = close[i] > e20[i]
  const trendUp = e9[i] > e20[i] && e20[i] > e50[i] && close[i] > e20[i]
  const trendDown = e9[i] < e20[i] && e20[i] < e50[i] && close[i] < e20[i]
  const buyMomentum = (r[i] || 50) >= 52 && (r[i] || 50) <= 72 && macdLine[i] > macdSignal[i]
  const sellMomentum = (r[i] || 50) <= 48 && (r[i] || 50) >= 28 && macdLine[i] < macdSignal[i]
  const volumeOk = !Number.isFinite(v[i]) || vol[i] >= v[i] * 0.9
  const strongTrend = (adxLine[i] || 0) >= 20
  const buyVwap = close[i] > vwap
  const sellVwap = close[i] < vwap

  let decision: Decision = "HOLD"
  const buyGates = [trendUp, buyVwap, buyMomentum, strongTrend, volumeOk, supertrendUp, bullishBreakout]
  const sellGates = [trendDown, sellVwap, sellMomentum, strongTrend, volumeOk, !supertrendUp, bearishBreakout]
  if (buyGates.filter(Boolean).length >= 6) decision = "BUY"
  else if (sellGates.filter(Boolean).length >= 6) decision = "SELL"

  const reason = decision === "BUY"
    ? "Trend + VWAP + momentum + ADX + volume + breakout confirmation"
    : decision === "SELL"
      ? "Downtrend + VWAP + momentum + ADX + volume + breakdown confirmation"
      : "Waiting for multi-gate confirmation"

  const pivot = (high[i] + low[i] + close[i]) / 3
  const hi26 = Math.max(...high.slice(Math.max(0, i - 25), i + 1))
  const lo26 = Math.min(...low.slice(Math.max(0, i - 25), i + 1))
  const fib = hi26 - (hi26 - lo26) * 0.618
  const obv = vol.reduce((s, x, j) => s + (j && close[j] > close[j - 1] ? x : j && close[j] < close[j - 1] ? -x : 0), 0)

  const indicators: Record<string, string | number> = {
    "Bollinger Bands": lower.toFixed(2) + " — " + upper.toFixed(2),
    "VWAP": vwap.toFixed(2),
    "EMA 9": e9[i].toFixed(2),
    "EMA 20": e20[i].toFixed(2),
    "EMA 50": e50[i].toFixed(2),
    "SMA 20": s20[i].toFixed(2),
    "SMA 50": s50[i].toFixed(2),
    "SMA 200": Number.isFinite(s200[i]) ? s200[i].toFixed(2) : "N/A",
    "RSI": r[i].toFixed(2),
    "MACD": macdLine[i].toFixed(4) + " / " + macdSignal[i].toFixed(4),
    "Stochastic": stoch.toFixed(2),
    "ATR": a[i].toFixed(2),
    "ADX": (adxLine[i] || 0).toFixed(2),
    "Supertrend": supertrendUp ? "UP" : "DOWN",
    "Ichimoku Cloud": "Tenkan " + ((Math.max(...high.slice(-9)) + Math.min(...low.slice(-9))) / 2).toFixed(2),
    "Parabolic SAR": Math.min(...low.slice(-5)).toFixed(2),
    "OBV": obv.toFixed(0),
    "Volume Profile": "POC " + (pv / Math.max(tv, 1)).toFixed(2),
    "Pivot Points": pivot.toFixed(2),
    "Fibonacci Retracement": fib.toFixed(2),
  }

  return {
    decision, price: close[i], rsi: r[i], e9: e9[i], e20: e20[i], e50: e50[i],
    atr: a[i], volume: vol[i], volSma: v[i], adx: adxLine[i], vwap, reason, indicators,
  }
}

function buildMarkers(c: Candle[]): Marker[] {
  if (c.length < 60) return []
  const markers: Marker[] = []
  let lastDecision: Decision = "HOLD"

  for (let i = 50; i < c.length - 1; i++) {
    const window = c.slice(0, i + 1)
    const d = calc(window)

    // Signals are emitted only on closed candles and only on a fresh direction.
    if (d.decision !== "HOLD" && d.decision !== lastDecision) {
      markers.push({ index: i, decision: d.decision, price: c[i].close, reason: d.reason })
      lastDecision = d.decision
    } else if (d.decision === "HOLD") {
      lastDecision = "HOLD"
    }
  }
  return markers
}

async function fetchK(symbol: string, tf: string) {
  const x = await api.get<{ candles: Candle[] }>(
    "/crypto-market/candles?symbol=" + encodeURIComponent(symbol) + "&interval=" + tf + "&limit=220",
  )
  return x.candles
}

export default function CryptoTechnicalPanel({ symbol }: { symbol: string }) {
  const [candles, setCandles] = useState<Record<string, Candle[]>>({})
  const [tf, setTf] = useState<typeof TF[number]>("15m")
  const [indicator, setIndicator] = useState("EMA 20")
  const [err, setErr] = useState("")

  useEffect(() => {
    let alive = true
    setErr("")
    Promise.all(TF.map(async x => [x, await fetchK(symbol, x)] as const))
      .then(x => { if (alive) setCandles(Object.fromEntries(x)) })
      .catch(e => alive && setErr(e instanceof Error ? e.message : "Crypto data unavailable"))
    return () => { alive = false }
  }, [symbol])

  const current = candles[tf] || []
  const d = useMemo(() => current.length ? calc(current) : null, [current])
  const markers = useMemo(() => buildMarkers(current), [current])
  const indicatorValue = useMemo(() => d?.indicators?.[indicator] ?? "—", [d, indicator])

  const mtf = useMemo(() => TF.map(x => {
    const q = candles[x]
    const z = q?.length ? calc(q) : null
    return z
      ? { tf: x, decision: z.decision, reason: z.reason, trend: z.e9 > z.e20 && z.e20 > z.e50 ? "UP" : z.e9 < z.e20 && z.e20 < z.e50 ? "DOWN" : "MIXED" }
      : null
  }).filter(Boolean) as Signal[], [candles])

  const allBuy = mtf.length === 3 && mtf.every(x => x.decision === "BUY")
  const allSell = mtf.length === 3 && mtf.every(x => x.decision === "SELL")
  const final: Decision = allBuy ? "BUY" : allSell ? "SELL" : "HOLD"

  const visible = current.slice(-120)
  const offset = Math.max(0, current.length - visible.length)
  const values = visible.map(x => x.close)
  const max = Math.max(...visible.map(x => x.high), 1)
  const min = Math.min(...visible.map(x => x.low), 0)
  const range = max - min || 1
  const path = values.map((v, i) => (i ? "L" : "M") + " " + (i / Math.max(values.length - 1, 1) * 100).toFixed(2) + " " + (100 - ((v - min) / range) * 82 - 8).toFixed(2)).join(" ")

  const visibleMarkers = markers
    .filter(m => m.index >= offset)
    .map(m => ({ ...m, x: ((m.index - offset) / Math.max(visible.length - 1, 1)) * 100, y: 100 - ((m.price - min) / range) * 82 - 8 }))

  return (
    <section className="space-y-5">
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="tx-section-title">Crypto X-Fusion Signal Chart</div>
            <p className="text-[11px] text-slate-600">Closed-candle strategy · EMA + VWAP + RSI/MACD + ADX + volume + breakout</p>
          </div>
          <div className="tx-tabs">{TF.map(x =>
            <button key={x} className={"tx-tab " + (tf === x ? "tx-tab-active" : "")} onClick={() => setTf(x)}>{x}</button>
          )}</div>
        </div>

        {err && <div className="mt-3 text-xs text-red-300">{err}</div>}

        <div className="grid lg:grid-cols-[1.6fr_.8fr] gap-4 mt-4">
          <div>
            <div className="relative h-72 rounded-xl border border-blue-900/30 bg-[#020b20] p-3 overflow-hidden">
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
                <path d={path} fill="none" stroke="#28dfff" strokeWidth="1.15" vectorEffect="non-scaling-stroke" />
                <path d={path + " L 100 100 L 0 100 Z"} fill="rgba(40,223,255,.06)" />
                {visibleMarkers.map(m => (
                  <g key={m.index + "-" + m.decision}>
                    <line x1={m.x} x2={m.x} y1={m.decision === "BUY" ? m.y + 4 : 4} y2={m.decision === "BUY" ? 96 : m.y - 4}
                      stroke={m.decision === "BUY" ? "#34d399" : "#fb7185"} strokeOpacity=".18" strokeWidth=".7" vectorEffect="non-scaling-stroke" />
                    <circle cx={m.x} cy={m.y} r="2.2" fill={m.decision === "BUY" ? "#34d399" : "#fb7185"} stroke="#020b20" strokeWidth="1" vectorEffect="non-scaling-stroke" />
                    <text x={Math.min(96, Math.max(2, m.x + 1))} y={m.decision === "BUY" ? Math.max(8, m.y - 5) : Math.min(94, m.y + 8)}
                      fill={m.decision === "BUY" ? "#6ee7b7" : "#fda4af"} fontSize="4" fontWeight="700">
                      {m.decision}
                    </text>
                  </g>
                ))}
              </svg>
              <div className="absolute left-3 top-3 text-[9px] text-slate-600">LAST 120 CLOSED CANDLES</div>
              <div className="absolute right-3 top-3 flex gap-3 text-[9px]">
                <span className="text-emerald-300">● BUY</span>
                <span className="text-rose-300">● SELL</span>
              </div>
            </div>

            <div className="mt-2 flex items-center justify-between text-[9px] text-slate-600">
              <span>{markers.length} strategy transitions</span>
              <span>Signals are generated from closed candles; no intrabar trigger</span>
            </div>

            <div className="tx-tabs mt-3 overflow-x-auto flex-nowrap pb-1">
              {INDICATORS.map(x =>
                <button key={x} className={"tx-tab " + (indicator === x ? "tx-tab-active" : "")} onClick={() => setIndicator(x)}>{x}</button>
              )}
            </div>
            <div className="mt-3 text-[10px] text-slate-600">
              Selected indicator: <span className="text-cyan-300">{indicator}</span> · <b className="text-white">{indicatorValue}</b> · 20 indicators calculated from OHLCV
            </div>
          </div>

          <div className="space-y-3">
            {d && <>
              <div className={"rounded-xl border p-4 " + (d.decision === "BUY" ? "border-emerald-500/30 bg-emerald-500/5" : d.decision === "SELL" ? "border-red-500/30 bg-red-500/5" : "border-cyan-500/20 bg-cyan-500/5")}>
                <div className="text-[10px] text-slate-500 uppercase">{tf} / latest closed candle</div>
                <div className="text-3xl font-black mt-1">{d.decision}</div>
                <p className="text-xs text-slate-500 mt-1">{d.reason}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ["EMA 9", d.e9], ["EMA 20", d.e20], ["EMA 50", d.e50],
                  ["RSI", d.rsi], ["ADX", d.adx], ["VWAP", d.vwap],
                  ["ATR", d.atr], ["VOL SMA", d.volSma],
                ].map(x =>
                  <div className="tx-kpi p-3" key={x[0]}>
                    <span className="tx-kpi-label">{x[0]}</span>
                    <b className="block mt-1 text-white">{Number.isFinite(x[1]) ? Number(x[1]).toFixed(2) : "—"}</b>
                  </div>
                )}
              </div>
            </>}
          </div>
        </div>
      </div>

      <div className="glass-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="tx-section-title">Multi-Timeframe Confirmation</div>
            <p className="text-[11px] text-slate-600">5m + 15m + 30m must align before the terminal shows a directional confirmation.</p>
          </div>
          <span className={"tx-terminal-badge " + (final === "BUY" ? "text-emerald-300" : final === "SELL" ? "text-red-300" : "")}>{final}</span>
        </div>
        <div className="grid md:grid-cols-3 gap-3 mt-4">
          {TF.map(x => {
            const z = mtf.find(y => y.tf === x)
            return (
              <div key={x} className="tx-crypto-asset">
                <div className="flex justify-between">
                  <span>{x}</span>
                  <b className={z?.decision === "BUY" ? "text-emerald-400" : z?.decision === "SELL" ? "text-red-400" : "text-slate-400"}>{z?.decision || "WAIT"}</b>
                </div>
                <strong className="!text-sm mt-3">{z?.trend || "—"} TREND</strong>
                <small>{z?.reason || "Loading candles…"}</small>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
