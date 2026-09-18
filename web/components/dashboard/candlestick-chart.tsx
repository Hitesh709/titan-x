"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import api from "@/lib/api"

export type Candle = { time: string; open: number; high: number; low: number; close: number; volume: number }

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

const INTERVALS = ["5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]
const PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "5y", "max"]
const INDICATORS = [
  ["bb", "Bollinger Bands"], ["vwap", "VWAP"], ["ema9", "EMA 9"], ["ema20", "EMA 20"], ["ema50", "EMA 50"],
  ["sma20", "SMA 20"], ["sma50", "SMA 50"], ["sma200", "SMA 200"], ["rsi", "RSI"], ["macd", "MACD"],
  ["stoch", "Stochastic"], ["atr", "ATR"], ["adx", "ADX"], ["supertrend", "Supertrend"], ["ichimoku", "Ichimoku"],
  ["sar", "Parabolic SAR"], ["obv", "OBV"], ["vp", "Volume Profile"], ["pivot", "Pivot Points"], ["fib", "Fibonacci"]
] as const

const avg = (a: number[]) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0
const sma = (a: number[], n: number) => a.map((_, i) => i + 1 < n ? null : avg(a.slice(i + 1 - n, i + 1)))
const ema = (a: number[], n: number) => { const out: IndicatorSeries = []; const k = 2 / (n + 1); let e: number | null = null; a.forEach((v, i) => { e = e == null ? (i + 1 >= n ? avg(a.slice(i + 1 - n, i + 1)) : null) : v * k + e * (1 - k); out.push(e) }); return out }

export default function CandlestickChart({symbol}:{symbol:string}){
  const [interval,setInterval]=useState("5m"),[period,setPeriod]=useState("1d"),[candles,setCandles]=useState<Candle[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[selected,setSelected]=useState<string[]>(["bb","vwap","ema9","ema20"])

  useEffect(()=>{
    let active=true
    setLoading(true)
    setError(null)
    api.get<ChartData>(`/fusion/chart/${encodeURIComponent(symbol)}?interval=${interval}&period=${period}`).then(r=>{if(active){setCandles(r.candles??[]); setError(null)}}).catch(e=>active&&setError(e instanceof Error?e.message:"Chart data unavailable")).finally(()=>active&&setLoading(false))
    return()=>{active=false}
  },[symbol,interval,period])

  const data=useMemo(()=>candles.slice(-180),[candles])
  const fullIndicators=data.length?data[0].indicators:null
  const rsi=fullIndicators?.rsi??[]
  const macd=fullIndicators?.macd??[]
  const macdSignal=fullIndicators?.macd_signal??[]
  const macdHist=fullIndicators?.macd_hist??[]
  const atr=fullIndicators?.atr??[]
  const adx=fullIndicators?.adx??[]
  const volSma=fullIndicators?.volume_sma??0

  const fusionSignals=useMemo(()=>fullIndicators?.signals??[]||[],[fullIndicators])

  const W=1200,H=470,p={l:62,r:20,t:26,b:42}, pw=W-p.l-p.r,ph=330
  const lo=data.length?Math.min(...data.map(x=>x.low)):0
  const hi=data.length?Math.max(...data.map(x=>x.high)):1
  const y=(v:number)=>p.t+(hi-v)/Math.max(hi-lo,.000001)*ph
  const step=data.length?pw/data.length:pw
  const cw=Math.max(2,Math.min(10,step*.65))

  const lines=(key:string,color:string)=>{
    const vals=(fullIndicators as any)?.[key] as IndicatorSeries||[]
    return vals.map((v,i)=>v==null?null:`${p.l+i*step+step/2},${y(v)}`).filter(Boolean).join(" ")
  }

  const activeIndicators=INDICATORS.filter(([k])=>selected.includes(k))

  const stLine=fullIndicators?.supertrend??[] as IndicatorSeries

  return <div>
    <div className="flex flex-wrap gap-1.5 mb-3">{INTERVALS.map(x=><button key={x} onClick={()=>{setInterval(x);if(x==="5m"||x==="15m")setPeriod("1d")}} className={`px-3 py-1.5 rounded-md text-[11px] border ${interval===x?"bg-titan-600/25 text-titan-300 border-titan-500/40":"bg-white/5 text-gray-400 border-white/10"}`}>{x.toUpperCase()}</button>)}</div>
    <div className="flex flex-wrap gap-1.5 mb-3">{PERIODS.map(x=><button key={x} onClick={()=>setPeriod(x)} className={`px-2.5 py-1 rounded-md text-[10px] border ${period===x?"bg-white/10 text-white border-white/20":"text-gray-500 border-white/5"}`}>{x.toUpperCase()}</button>)}</div>
    <div className="mb-3 rounded-lg border border-cyan-500/15 bg-cyan-500/[0.03] p-2">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider text-cyan-300 font-bold">20 Technical Strategies / Indicators</span>
        <span className="text-[9px] text-gray-500">Select overlays & studies</span>
      </div>
      <div className="flex flex-wrap gap-1.5">{INDICATORS.map(([k,n])=><button key={k} onClick={()=>setSelected(s=>s.includes(k)?s.filter(x=>x!==k):[...s,k])} className={`px-2 py-1 rounded text-[9px] border ${selected.includes(k)?"bg-titan-500/15 text-cyan-200 border-cyan-500/30":"bg-white/[0.03] text-gray-500 border-white/10"}`}>{n}</button>)}</div>
    </div>
    <div className="rounded-xl border border-white/5 bg-[#070b18] overflow-hidden">
      {loading?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500">Loading real OHLCV candles…</div>:
      error?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500 px-6 text-center">{error}</div>:
      !data.length?<div className="h-[470px] flex items-center justify-center text-sm text-gray-500">No real candle data available.</div>:
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[470px]" preserveAspectRatio="none">
          {[0,.25,.5,.75,1].map(q=>{const v=hi-(hi-lo)*q;return <g key={q}><line x1={p.l} x2={W-p.r} y1={y(v)} y2={y(v)} stroke="rgba(255,255,255,.06)"/><text x="6" y={y(v)+4} fill="#718096" fontSize="12">{v.toFixed(2)}</text></g>})}
          {data.map((c,i)=>{const x=p.l+i*step+step/2,up=c.close>=c.open,col=up?"#00f0a0":"#ff4d67";return <g key={c.time+i} onMouseEnter={()=>setHover(i)} onMouseLeave={()=>setHover(null)}><line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={col} strokeWidth="1.5"/><rect x={x-cw/2} y={y(Math.max(c.open,c.close))} width={cw} height={Math.max(1.5,y(Math.min(c.open,c-close))-y(Math.max(c.open,c-close)))} fill={col} rx="1"/></g>})}
          {selected.includes("bb")&&<><polyline points={lines("bbU","cyan")} fill="none" stroke="#38bdf8" strokeWidth="1"/><polyline points={lines("bbL","cyan")} fill="none" stroke="#38bdf8" strokeWidth="1"/><polyline points={lines("s20","cyan")} fill="none" stroke="#38bdf8" strokeWidth=".7" opacity=".6"/></>}{selected.includes("vwap")&&<polyline points={lines("vwap","purple")} fill="none" stroke="#a855f7" strokeWidth="1.5"/>}{selected.includes("ema9")&&<polyline points={lines("e9","green")} fill="none" stroke="#22c55e" strokeWidth="1"/>}{selected.includes("ema20")&&<polyline points={lines("e20","blue")} fill="none" stroke="#60a5fa" strokeWidth="1"/>}{selected.includes("ema50")&&<polyline points={lines("e50","pink")} fill="none" stroke="#f472b6" strokeWidth="1"/>}{selected.includes("sma20")&&<polyline points={lines("s20","white")} fill="none" stroke="#e5e7eb" strokeWidth="1"/>}{selected.includes("sma50")&&<polyline points={lines("s50","white")} fill="none" stroke="#94a3b8" strokeWidth="1"/>}{selected.includes("sma200")&&<polyline points={lines("s200","yellow")} fill="none" stroke="#facc15" strokeWidth="1/>}
          {stLine.length&&selected.includes("supertrend")&&<polyline points={lines("supertrend","orange")} fill="none" stroke="#fb923c" strokeWidth="1.5/>}
          {fusionSignals.map((s,idx)=>{const c=data[idx];const x=p.l+idx*step+step/2,yy=y(c?.close??c?.open??0);return <g key={idx} onClick={()=>setHover(idx)} className="cursor-pointer"><circle cx={x} cy={yy} r="6" fill={s.side==="BUY"?"#00f0a0":"#ff4d67"}/><text x={x} y={s.side==="BUY"?yy+4:yy-9} textAnchor="middle" fill="#fff" fontSize="8" fontWeight="700">{s.side}</text></g>})}
          {data.filter((_,i)=>i%Math.max(1,Math.ceil(data.length/8))===0).map((c,i)=>{const j=data.indexOf(c);return <text key={i} x={p.l+j*step+step/2} y={H-12} textAnchor="middle" fill="#718096" fontSize="10">{new Date(c.time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}</text>})}</svg>
          {hover!=null&&!fusionSignals.find(s=>s.time===data[hover]?.time)&&<div className="absolute top-3 right-3 max-w-xs bg-slate-950/95 border border-cyan-500/20 rounded-lg px-3 py-2 text-[10px] shadow-xl"><div className="text-gray-400">{new Date(data[hover].time).toLocaleString("en-IN")}</div><div className="grid grid-cols-2 gap-x-3 text-white mt-1"><span>O {data[hover].open.toFixed(2)}</span><span>H {data[hover].high.toFixed(2)}</span><span>L {data[hover].low.toFixed(2)}</span><span>C {data[hover].close.toFixed(2)}</span><span>Vol {data[hover].volume.toLocaleString("en-IN")}</span></div></div>}</div>
        </svg>
        {hover!=null&&fusionSignals.find(s=>s.time===data[hover]?.time)&&<div className="absolute top-3 right-3 max-w-xs bg-slate-950/95 border border-cyan-500/20 rounded-lg px-3 py-2 text-[10px] shadow-xl"><div className="text-gray-400">{new Date(data[hover].time).toLocaleString("en-IN")}</div><div className="grid grid-cols-2 gap-x-3 text-white mt-1"><span>O {data[hover].open.toFixed(2)}</span><span>H {data[hover].high.toFixed(2)}</span><span>L {data[hover].low.toFixed(2)}</span><span>C {data[hover].close.toFixed(2)}</span><span>Vol {data[hover].volume.toLocaleString("en-IN")}</span></div>{fusionSignals.find(s=>s.time===data[hover]?.time)&&<div className="mt-2 text-cyan-200">{fusionSignals.find(s=>s.time===data[hover]?.time)!.side} · {fusionSignals.find(s=>s.time===data[hover]?.time)!.reason}</div>}</div>}</div>
      </div>
    </div>
    <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">{activeIndicators.slice(0,4).map(([k,n])=><div key={k} className="rounded-lg bg-white/[0.03] border border-white/5 p-2"><div className="text-[9px] text-gray-500">{n}</div><div className="text-xs text-cyan-200 mt-1">Active</div></div>)}<div className="rounded-lg bg-white/[0.03] border border-white/5 p-2"><div className="text-[9px] text-gray-500">Fusion Signals</div><div className="text-xs text-emerald-300 mt-1">{fusionSignals.filter(s=>s.side==="BUY").length} BUY · {fusionSignals.filter(s=>s.side==="SELL").length} SELL</div></div></div>
    <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-500"><span>● BUY / SELL markers from Titan X Fusion engine (no scores)</span><span className="ml-auto">Source: backend engine, 5m/15m intervals</span></div>
  </div>
}