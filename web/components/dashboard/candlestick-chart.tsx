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
type Series = (number | null)[]

type ChartData = {
  candles: Candle[]
  signals: Signal[]
  supertrend: Series
  indicators: {
    e9: Series
    e20: Series
    e50: Series
    rsi: Series
    macd: Series
    macd_signal: Series
    macd_hist: Series
    atr: Series
    adx: Series
    volume_sma: number
  }
}

const INTERVALS = ["5m", "15m", "30m"] as const
const PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"] as const

const INDICATORS = [
  ["bb", "Bollinger Bands"], ["vwap", "VWAP"], ["ema9", "EMA 9"], ["ema20", "EMA 20"], ["ema50", "EMA 50"],
  ["sma20", "SMA 20"], ["sma50", "SMA 50"], ["sma200", "SMA 200"], ["rsi", "RSI"], ["macd", "MACD"],
  ["stoch", "Stochastic"], ["atr", "ATR"], ["adx", "ADX"], ["supertrend", "Supertrend"], ["ichimoku", "Ichimoku Cloud"],
  ["sar", "Parabolic SAR"], ["obv", "OBV"], ["vp", "Volume Profile"], ["pivot", "Pivot Points"], ["fib", "Fibonacci Retracement"],
] as const

const avg = (a: number[]) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0
const sma = (v: number[], n: number): Series => v.map((_, i) => i + 1 < n ? null : avg(v.slice(i + 1 - n, i + 1)))

function ema(v: number[], n: number): Series {
  const out: Series = Array(Math.min(n - 1, v.length)).fill(null)
  if (v.length < n) return [...out, ...Array(v.length - out.length).fill(null)]
  let e = avg(v.slice(0, n)); out.push(e)
  const k = 2 / (n + 1)
  for (let i = n; i < v.length; i++) { e = v[i] * k + e * (1 - k); out.push(e) }
  return out
}

function bollinger(v: number[], n = 20, mult = 2) {
  const mid = sma(v, n), upper: Series = [], lower: Series = []
  v.forEach((_, i) => {
    if (mid[i] == null) { upper.push(null); lower.push(null); return }
    const w = v.slice(i + 1 - n, i + 1), m = mid[i] as number
    const sd = Math.sqrt(avg(w.map(x => (x - m) ** 2)))
    upper.push(m + mult * sd); lower.push(m - mult * sd)
  })
  return { upper, mid, lower }
}

function vwap(c: Candle[]): Series {
  let pv = 0, vol = 0
  return c.map(x => {
    const t = (x.high + x.low + x.close) / 3
    pv += t * Math.max(0, x.volume); vol += Math.max(0, x.volume)
    return vol ? pv / vol : null
  })
}

function rsi(v: number[], n = 14): Series {
  if (v.length <= n) return Array(v.length).fill(null)
  const out: Series = Array(n).fill(null)
  let gain = 0, loss = 0
  for (let i = 1; i <= n; i++) { const d = v[i] - v[i - 1]; gain += Math.max(d, 0); loss += Math.max(-d, 0) }
  let ag = gain / n, al = loss / n
  out.push(al === 0 ? 100 : 100 - 100 / (1 + ag / al))
  for (let i = n + 1; i < v.length; i++) {
    const d = v[i] - v[i - 1], g = Math.max(d, 0), l = Math.max(-d, 0)
    ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
    out.push(al === 0 ? 100 : 100 - 100 / (1 + ag / al))
  }
  return out
}

function macd(v: number[]) {
  const a = ema(v, 12), b = ema(v, 26), line: Series = v.map((_, i) => a[i] != null && b[i] != null ? (a[i] as number) - (b[i] as number) : null)
  const compact = line.filter((x): x is number => x != null), s = ema(compact, 9), signal: Series = Array(v.length).fill(null)
  let j = 0; for (let i = 0; i < v.length; i++) if (line[i] != null) signal[i] = s[j++]
  return { line, signal, hist: line.map((x, i) => x != null && signal[i] != null ? x - (signal[i] as number) : null) }
}

function atr(c: Candle[], n = 14): Series {
  if (c.length < 2) return Array(c.length).fill(null)
  const tr = c.map((x, i) => i ? Math.max(x.high - x.low, Math.abs(x.high - c[i - 1].close), Math.abs(x.low - c[i - 1].close)) : 0)
  const out: Series = Array(c.length).fill(null)
  if (c.length <= n) return out
  let a = avg(tr.slice(1, n + 1)); out[n] = a
  for (let i = n + 1; i < c.length; i++) { a = (a * (n - 1) + tr[i]) / n; out[i] = a }
  return out
}

function adx(c: Candle[], n = 14): Series {
  const out: Series = Array(c.length).fill(null)
  if (c.length < n * 2) return out
  const trs: number[] = [], plus: number[] = [], minus: number[] = []
  for (let i = 1; i < c.length; i++) {
    const up = c[i].high - c[i - 1].high, down = c[i - 1].low - c[i].low
    plus.push(up > down && up > 0 ? up : 0); minus.push(down > up && down > 0 ? down : 0)
    trs.push(Math.max(c[i].high - c[i].low, Math.abs(c[i].high - c[i - 1].close), Math.abs(c[i].low - c[i - 1].close)))
  }
  const dx: number[] = []
  let trA = avg(trs.slice(0, n)), pA = avg(plus.slice(0, n)), mA = avg(minus.slice(0, n))
  for (let i = n; i < trs.length; i++) {
    const pdi = trA ? 100 * pA / trA : 0, mdi = trA ? 100 * mA / trA : 0
    dx.push(pdi + mdi ? 100 * Math.abs(pdi - mdi) / (pdi + mdi) : 0)
    trA = (trA * (n - 1) + trs[i]) / n; pA = (pA * (n - 1) + plus[i]) / n; mA = (mA * (n - 1) + minus[i]) / n
  }
  if (dx.length >= n) {
    let a = avg(dx.slice(0, n)); out[2 * n] = a
    for (let i = n; i < dx.length; i++) { a = (a * (n - 1) + dx[i]) / n; out[2 * n + i - n + 1] = a }
  }
  return out
}

function stochastic(c: Candle[], n = 14) {
  const k: Series = Array(c.length).fill(null), d: Series = Array(c.length).fill(null)
  for (let i = n - 1; i < c.length; i++) {
    const hh = Math.max(...c.slice(i + 1 - n, i + 1).map(x => x.high)), ll = Math.min(...c.slice(i + 1 - n, i + 1).map(x => x.low))
    k[i] = hh === ll ? 50 : 100 * (c[i].close - ll) / (hh - ll)
  }
  const kv = k.map(x => x ?? 50), ds = sma(kv, 3); return { k, d: ds }
}

function obv(c: Candle[]): Series {
  if (!c.length) return []
  const out: Series = [c[0].volume]
  for (let i = 1; i < c.length; i++) out.push((out[i - 1] as number) + (c[i].close > c[i - 1].close ? c[i].volume : c[i].close < c[i - 1].close ? -c[i].volume : 0))
  return out
}

function psar(c: Candle[], step = 0.02, maxAf = 0.2): Series {
  if (c.length < 2) return Array(c.length).fill(null)
  const out: Series = [c[0].low]; let up = c[1].high >= c[0].high, sar = up ? c[0].low : c[0].high, ep = up ? c[0].high : c[0].low, af = step
  for (let i = 1; i < c.length; i++) {
    sar = sar + af * (ep - sar)
    if (up) {
      sar = Math.min(sar, c[i - 1].low, i > 1 ? c[i - 2].low : c[i - 1].low)
      if (c[i].low < sar) { up = false; sar = ep; ep = c[i].low; af = step } else if (c[i].high > ep) { ep = c[i].high; af = Math.min(maxAf, af + step) }
    } else {
      sar = Math.max(sar, c[i - 1].high, i > 1 ? c[i - 2].high : c[i - 1].high)
      if (c[i].high > sar) { up = true; sar = ep; ep = c[i].high; af = step } else if (c[i].low < ep) { ep = c[i].low; af = Math.min(maxAf, af + step) }
    }
    out.push(sar)
  }
  return out
}

function ichimoku(c: Candle[]) {
  const mid = (n: number, i: number) => {
    if (i + 1 < n) return null
    const w = c.slice(i + 1 - n, i + 1), h = Math.max(...w.map(x => x.high)), l = Math.min(...w.map(x => x.low))
    return (h + l) / 2
  }
  const tenkan: Series = [], kijun: Series = [], spanA: Series = [], spanB: Series = []
  for (let i = 0; i < c.length; i++) {
    const t = mid(9, i), k = mid(26, i), b = mid(52, i)
    tenkan.push(t); kijun.push(k); spanA.push(t != null && k != null ? (t + k) / 2 : null); spanB.push(b)
  }
  return { tenkan, kijun, spanA, spanB }
}

function volumeProfile(c: Candle[], bins = 12) {
  if (!c.length) return { poc: null, levels: [] as {price:number; volume:number}[] }
  const min = Math.min(...c.map(x => x.low)), max = Math.max(...c.map(x => x.high)), size = (max - min) / bins || 1
  const levels = Array.from({length: bins}, (_, i) => ({price: min + (i + .5) * size, volume: 0}))
  c.forEach(x => { const i = Math.min(bins - 1, Math.max(0, Math.floor((x.close - min) / size))); levels[i].volume += x.volume })
  const maxVol = Math.max(...levels.map(x => x.volume), 1)
  return { poc: levels.reduce((a,b) => a.volume > b.volume ? a : b).price, levels: levels.map(x => ({...x, volume:x.volume / maxVol})) }
}

function pivots(c: Candle[]) {
  if (!c.length) return null
  const last = c[c.length - 1], p = (last.high + last.low + last.close) / 3
  return { p, r1: 2*p-last.low, r2: p+(last.high-last.low), s1: 2*p-last.high, s2: p-(last.high-last.low) }
}

function fibonacci(c: Candle[]) {
  if (!c.length) return null
  const high = Math.max(...c.map(x => x.high)), low = Math.min(...c.map(x => x.low)), d = high-low
  return { high, low, levels: [0, .236, .382, .5, .618, .786, 1].map(r => ({r, price: high-d*r})) }
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
    setLoading(true); setError(null)
    api.get<ChartData>(`/fusion/chart/${encodeURIComponent(symbol)}?interval=${interval}&period=${period}`)
      .then(response => { if (active) setChart(response) })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : "Chart data unavailable") })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [symbol, interval, period])

  const data = useMemo(() => (chart?.candles ?? []).slice(-240), [chart])
  const closes = useMemo(() => data.map(x => x.close), [data])
  const bands = useMemo(() => bollinger(closes), [closes])
  const vw = useMemo(() => vwap(data), [data])
  const sma20 = useMemo(() => sma(closes,20), [closes]), sma50 = useMemo(() => sma(closes,50), [closes]), sma200 = useMemo(() => sma(closes,200), [closes])
  const ema9 = useMemo(() => ema(closes,9), [closes]), ema20 = useMemo(() => ema(closes,20), [closes]), ema50 = useMemo(() => ema(closes,50), [closes])
  const rsiS = useMemo(() => rsi(closes), [closes]), macdS = useMemo(() => macd(closes), [closes]), atrS = useMemo(() => atr(data), [data]), adxS = useMemo(() => adx(data), [data])
  const stoch = useMemo(() => stochastic(data), [data]), obvS = useMemo(() => obv(data), [data]), sarS = useMemo(() => psar(data), [data]), ichi = useMemo(() => ichimoku(data), [data])
  const vp = useMemo(() => volumeProfile(data), [data]), piv = useMemo(() => pivots(data), [data]), fib = useMemo(() => fibonacci(data), [data])

  const signals = useMemo(() => {
    const visible = new Set(data.map(c => c.time)); return (chart?.signals ?? []).filter(s => visible.has(s.time))
  }, [chart, data])
  const signalByTime = useMemo(() => new Map(signals.map(s => [s.time,s])), [signals])

  const W=1200, H=470, OH=170, p={l:62,r:20,t:24,b:38}, pw=W-p.l-p.r, ph=330
  const lo=data.length?Math.min(...data.map(c=>c.low)):0, hi=data.length?Math.max(...data.map(c=>c.high)):1
  const y=(v:number)=>p.t+(hi-v)/Math.max(hi-lo,.000001)*ph, step=data.length?pw/data.length:pw, cw=Math.max(2,Math.min(9,step*.65))
  const points=(values:Series)=>values.map((v,i)=>v!=null&&Number.isFinite(v)?`${p.l+i*step+step/2},${y(v)}`:null).filter((x):x is string=>!!x).join(" ")
  const subPoints=(values:Series,min:number,max:number)=>values.map((v,i)=>v!=null&&Number.isFinite(v)?`${p.l+i*step+step/2},${20+(max-v)/Math.max(max-min,.000001)*(OH-45)}`:null).filter((x):x is string=>!!x).join(" ")

  const priceOverlays = [
    selected.includes("bb") && <g key="bb"><polyline points={points(bands.upper)} fill="none" stroke="#38bdf8" strokeWidth="1"/><polyline points={points(bands.mid)} fill="none" stroke="#38bdf8" strokeWidth=".7" opacity=".5"/><polyline points={points(bands.lower)} fill="none" stroke="#38bdf8" strokeWidth="1"/></g>,
    selected.includes("vwap") && <polyline key="vwap" points={points(vw)} fill="none" stroke="#a855f7" strokeWidth="1.5"/>,
    selected.includes("ema9") && <polyline key="e9" points={points(ema9)} fill="none" stroke="#22c55e" strokeWidth="1"/>,
    selected.includes("ema20") && <polyline key="e20" points={points(ema20)} fill="none" stroke="#60a5fa" strokeWidth="1"/>,
    selected.includes("ema50") && <polyline key="e50" points={points(ema50)} fill="none" stroke="#f472b6" strokeWidth="1"/>,
    selected.includes("sma20") && <polyline key="s20" points={points(sma20)} fill="none" stroke="#e5e7eb" strokeWidth="1"/>,
    selected.includes("sma50") && <polyline key="s50" points={points(sma50)} fill="none" stroke="#94a3b8" strokeWidth="1"/>,
    selected.includes("sma200") && <polyline key="s200" points={points(sma200)} fill="none" stroke="#facc15" strokeWidth="1"/>,
    selected.includes("supertrend") && <polyline key="st" points={points(chart?.supertrend ?? [])} fill="none" stroke="#fb923c" strokeWidth="1.5"/>,
    selected.includes("sar") && <g key="sar">{sarS.map((v,i)=>v!=null?<circle key={i} cx={p.l+i*step+step/2} cy={y(v)} r="2" fill="#f59e0b"/>:null)}</g>,
    selected.includes("ichimoku") && <g key="ichi"><polyline points={points(ichi.tenkan)} fill="none" stroke="#ef4444" strokeWidth=".8"/><polyline points={points(ichi.kijun)} fill="none" stroke="#22d3ee" strokeWidth=".8"/><polyline points={points(ichi.spanA)} fill="none" stroke="#84cc16" strokeWidth=".7"/><polyline points={points(ichi.spanB)} fill="none" stroke="#f97316" strokeWidth=".7"/></g>,
    selected.includes("pivot") && piv && <g key="pivot">{[["P",piv.p],["R1",piv.r1],["R2",piv.r2],["S1",piv.s1],["S2",piv.s2]].map(([name,val])=><g key={String(name)}><line x1={p.l} x2={W-p.r} y1={y(Number(val))} y2={y(Number(val))} stroke="#64748b" strokeDasharray="5 4" strokeWidth=".8"/><text x={W-p.r-2} y={y(Number(val))-3} textAnchor="end" fill="#94a3b8" fontSize="9">{String(name)}</text></g>)}</g>,
    selected.includes("fib") && fib && <g key="fib">{fib.levels.map(x=><g key={x.r}><line x1={p.l} x2={W-p.r} y1={y(x.price)} y2={y(x.price)} stroke="#c084fc" strokeDasharray="3 4" strokeWidth=".7"/><text x={W-p.r-2} y={y(x.price)-3} textAnchor="end" fill="#c4b5fd" fontSize="8">{Math.round(x.r*100)}%</text></g>)}</g>,
    selected.includes("vp") && vp.levels.map((x,i)=><line key={i} x1={W-p.r-70} x2={W-p.r-70+x.volume*60} y1={y(x.price)} y2={y(x.price)} stroke="#06b6d4" strokeWidth="2" opacity=".45"/>),
  ]

  const subSeries: {key:string; name:string; values:Series; min:number; max:number}[] = []
  if (selected.includes("rsi")) subSeries.push({key:"rsi",name:"RSI",values:rsiS,min:0,max:100})
  if (selected.includes("macd")) {
    const vals=[...macdS.line,...macdS.signal].filter((x):x is number=>x!=null), m=Math.max(Math.abs(Math.min(...vals,0)),Math.abs(Math.max(...vals,0)),.0001)
    subSeries.push({key:"macd",name:"MACD",values:macdS.line,min:-m,max:m})
  }
  if (selected.includes("stoch")) subSeries.push({key:"stoch",name:"STOCH",values:stoch.k,min:0,max:100})
  if (selected.includes("atr")) { const vals=atrS.filter((x):x is number=>x!=null); subSeries.push({key:"atr",name:"ATR",values:atrS,min:0,max:Math.max(...vals,1)}) }
  if (selected.includes("adx")) subSeries.push({key:"adx",name:"ADX",values:adxS,min:0,max:100})
  if (selected.includes("obv")) { const vals=obvS.filter((x):x is number=>x!=null), m=Math.max(...vals.map(Math.abs),1); subSeries.push({key:"obv",name:"OBV",values:obvS,min:-m,max:m}) }

  return <div>
    <div className="flex flex-wrap gap-1.5 mb-3">
      {INTERVALS.map(x=><button key={x} onClick={()=>{setInterval(x);if(x!=="30m")setPeriod("1d")}} className={`px-3 py-1.5 rounded-md text-[11px] border ${interval===x?"bg-titan-600/25 text-titan-300 border-titan-500/40":"bg-white/5 text-gray-400 border-white/10"}`}>{x.toUpperCase()}</button>)}
    </div>
    <div className="flex flex-wrap gap-1.5 mb-3">
      {PERIODS.map(x=><button key={x} onClick={()=>setPeriod(x)} className={`px-2.5 py-1 rounded-md text-[10px] border ${period===x?"bg-white/10 text-white border-white/20":"text-gray-500 border-white/5"}`}>{x.toUpperCase()}</button>)}
    </div>
    <div className="mb-3 rounded-lg border border-cyan-500/15 bg-cyan-500/[0.03] p-2">
      <div className="flex items-center justify-between gap-2 mb-2"><span className="text-[10px] uppercase tracking-wider text-cyan-300 font-bold">20 Technical Indicators — Live Calculations</span><span className="text-[9px] text-gray-500">Real OHLCV</span></div>
      <div className="flex flex-wrap gap-1.5">{INDICATORS.map(([key,name])=><button key={key} onClick={()=>setSelected(s=>s.includes(key)?s.filter(x=>x!==key):[...s,key])} className={`px-2 py-1 rounded text-[9px] border ${selected.includes(key)?"bg-titan-500/15 text-cyan-200 border-cyan-500/30":"bg-white/[0.03] text-gray-500 border-white/10"}`}>{name}</button>)}</div>
    </div>
    <div className="rounded-xl border border-white/5 bg-[#070b18] overflow-hidden">
      {loading?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500">Loading real OHLCV candles…</div>:error?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500 px-6 text-center">{error}</div>:!data.length?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500">No real candle data available.</div>:
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[470px]" preserveAspectRatio="none">
          {[0,.25,.5,.75,1].map(q=>{const value=hi-(hi-lo)*q;return <g key={q}><line x1={p.l} x2={W-p.r} y1={y(value)} y2={y(value)} stroke="rgba(255,255,255,.06)"/><text x="6" y={y(value)+4} fill="#718096" fontSize="12">{value.toFixed(2)}</text></g>})}
          {data.map((c,i)=>{const x=p.l+i*step+step/2, up=c.close>=c.open, color=up?"#00f0a0":"#ff4d67", top=y(Math.max(c.open,c.close)), bottom=y(Math.min(c.open,c.close));return <g key={c.time+i} onMouseEnter={()=>setHover(i)} onMouseLeave={()=>setHover(null)} className="cursor-crosshair"><line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={color} strokeWidth="1.5"/><rect x={x-cw/2} y={top} width={cw} height={Math.max(1.5,bottom-top)} fill={color} rx="1"/></g>})}
          {priceOverlays}
          {signals.map(s=>{const i=data.findIndex(c=>c.time===s.time);if(i<0)return null;const c=data[i],x=p.l+i*step+step/2,yy=s.side==="BUY"?y(c.low)+16:y(c.high)-16;return <g key={s.time+s.side} onClick={()=>setHover(i)} className="cursor-pointer"><circle cx={x} cy={yy} r="6" fill={s.side==="BUY"?"#00f0a0":"#ff4d67"}/><text x={x} y={yy+3} textAnchor="middle" fill="#071018" fontSize="7" fontWeight="700">{s.side==="BUY"?"B":"S"}</text></g>})}
          {data.filter((_,i)=>i%Math.max(1,Math.ceil(data.length/8))===0).map(c=>{const i=data.indexOf(c);return <text key={c.time} x={p.l+i*step+step/2} y={H-12} textAnchor="middle" fill="#718096" fontSize="10">{new Date(c.time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}</text>})}
        </svg>
        {hover!=null&&data[hover]&&<div className="absolute top-3 right-3 max-w-xs bg-slate-950/95 border border-cyan-500/20 rounded-lg px-3 py-2 text-[10px] shadow-xl"><div className="text-gray-400">{new Date(data[hover].time).toLocaleString("en-IN")}</div><div className="grid grid-cols-2 gap-x-3 text-white mt-1"><span>O {data[hover].open.toFixed(2)}</span><span>H {data[hover].high.toFixed(2)}</span><span>L {data[hover].low.toFixed(2)}</span><span>C {data[hover].close.toFixed(2)}</span><span>Vol {data[hover].volume.toLocaleString("en-IN")}</span></div>{signalByTime.get(data[hover].time)&&<div className="mt-2 text-cyan-200">{signalByTime.get(data[hover].time)?.side} · {signalByTime.get(data[hover].time)?.reason}</div>}</div>}
      </div>}
    </div>
    {subSeries.length>0&&<div className="mt-2 rounded-xl border border-white/5 bg-[#070b18] overflow-hidden"><svg viewBox={`0 0 ${W} ${OH}`} className="w-full h-[170px]" preserveAspectRatio="none"><line x1={p.l} x2={W-p.r} y1="20" y2="20" stroke="rgba(255,255,255,.06)"/><line x1={p.l} x2={W-p.r} y1={OH-25} y2={OH-25} stroke="rgba(255,255,255,.06)"/>{subSeries.map((s,idx)=><g key={s.key}><polyline points={subPoints(s.values,s.min,s.max)} fill="none" stroke={["#22d3ee","#a855f7","#f59e0b","#fb7185","#84cc16","#60a5fa"][idx%6]} strokeWidth="1.2"/><text x={p.l+5} y={38+idx*18} fill="#94a3b8" fontSize="9">{s.name}</text></g>)}</svg></div>}
    <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
      {INDICATORS.filter(([k])=>selected.includes(k)).slice(0,7).map(([k,n])=><div key={k} className="rounded-lg bg-white/[0.03] border border-white/5 p-2"><div className="text-[9px] text-gray-500">{n}</div><div className="text-xs text-cyan-200 mt-1">Calculated</div></div>)}
      <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2"><div className="text-[9px] text-gray-500">Fusion Signals</div><div className="text-xs text-emerald-300 mt-1">{signals.filter(s=>s.side==="BUY").length} BUY · {signals.filter(s=>s.side==="SELL").length} SELL</div></div>
    </div>
    <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-500"><span>● BUY / SELL markers from Titan X Fusion engine</span><span className="ml-auto">Real OHLCV + client indicator calculations</span></div>
  </div>
}