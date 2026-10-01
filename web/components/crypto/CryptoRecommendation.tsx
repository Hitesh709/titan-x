"use client"

import { useEffect, useState } from "react"
import api from "@/lib/api"
import { RefreshCw, ShieldCheck, Target, Zap } from "lucide-react"
import { useCryptoLivePrices } from "./CryptoLiveTicker"

type Rec = {
  action: "BUY" | "SELL" | "HOLD"
  horizon: string
  entry: number | null
  stop_loss: number | null
  target: number | null
  rule: string
  summary: string
  timeframes: Array<{ timeframe: string; decision: string; price: number; rsi: number; atr: number; reason: string }>
}

const money=(n:number)=>n>=1000?n.toLocaleString("en-US",{maximumFractionDigits:2}):n.toLocaleString("en-US",{maximumFractionDigits:6})

export default function CryptoRecommendation({symbol}:{symbol:string}){
  const [mode,setMode]=useState<"intraday"|"delivery">("intraday")
  const [data,setData]=useState<Rec|null>(null)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState("")
  const {prices}=useCryptoLivePrices()
  const live=prices[symbol]?.price

  const load=async()=>{
    setLoading(true);setError("")
    try{
      const result=await api.get<Rec>("/crypto-recommendation?symbol="+encodeURIComponent(symbol)+"&mode="+mode)
      setData(result)
    }catch(e){setError(e instanceof Error?e.message:"Recommendation unavailable")}
    finally{setLoading(false)}
  }

  useEffect(()=>{void load();const id=window.setInterval(()=>void load(),60000);return()=>window.clearInterval(id)},[symbol,mode])

  const action=data?.action||"HOLD"
  const actionClass=action==="BUY"?"text-emerald-300 border-emerald-500/30 bg-emerald-500/5":action==="SELL"?"text-red-300 border-red-500/30 bg-red-500/5":"text-cyan-300 border-cyan-500/20 bg-cyan-500/5"

  return <section className="glass-card p-5">
    <div className="flex flex-wrap justify-between gap-3">
      <div>
        <div className="tx-section-title"><Target size={16}/> Crypto Recommendations</div>
        <p className="text-[11px] text-slate-600 mt-1">Rule-based research signals · separate intraday and delivery/positional horizons</p>
      </div>
      <button onClick={()=>void load()} className="btn-primary text-xs"><RefreshCw size={13} className={loading?"animate-spin":""}/> Refresh</button>
    </div>

    <div className="tx-tabs mt-4">
      <button className={"tx-tab "+(mode==="intraday"?"tx-tab-active":"")} onClick={()=>setMode("intraday")}><Zap size={13}/> Intraday</button>
      <button className={"tx-tab "+(mode==="delivery"?"tx-tab-active":"")} onClick={()=>setMode("delivery")}><ShieldCheck size={13}/> Delivery / Positional</button>
    </div>

    {error&&<div className="mt-4 text-xs text-red-300">{error}</div>}
    {data&&<div className="mt-4 grid lg:grid-cols-[.8fr_1.2fr] gap-4">
      <div className={"rounded-xl border p-5 "+actionClass}>
        <div className="text-[10px] uppercase tracking-wider opacity-70">{mode==="intraday"?"Intraday":"Delivery / Positional"} recommendation</div>
        <div className="text-4xl font-black mt-2">{action}</div>
        <div className="text-xs mt-2 opacity-70">{data.horizon}</div>
        <div className="grid grid-cols-2 gap-2 mt-5 text-xs">
          <div className="tx-kpi p-3"><span className="tx-kpi-label">LIVE PRICE</span><b className="block mt-1 text-white">{live?money(live):data.timeframes.at(-1)?.price?money(data.timeframes.at(-1)!.price):"—"}</b></div>
          <div className="tx-kpi p-3"><span className="tx-kpi-label">ENTRY</span><b className="block mt-1 text-white">{data.entry?money(data.entry):"WAIT"}</b></div>
          <div className="tx-kpi p-3"><span className="tx-kpi-label">STOP</span><b className="block mt-1 text-red-300">{data.stop_loss?money(data.stop_loss):"—"}</b></div>
          <div className="tx-kpi p-3"><span className="tx-kpi-label">TARGET</span><b className="block mt-1 text-emerald-300">{data.target?money(data.target):"—"}</b></div>
        </div>
        <p className="text-[10px] text-slate-500 mt-4">{data.rule}</p>
      </div>

      <div>
        <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">{data.summary}</div>
        <div className="grid md:grid-cols-3 gap-2">
          {data.timeframes.map(x=><div key={x.timeframe} className="tx-crypto-asset">
            <div className="flex justify-between"><span>{x.timeframe}</span><b className={x.decision==="BUY"?"text-emerald-400":x.decision==="SELL"?"text-red-400":"text-slate-400"}>{x.decision}</b></div>
            <strong className="!text-sm mt-2">$ {money(x.price)}</strong>
            <small>RSI {x.rsi.toFixed(1)} · ATR {money(x.atr)}</small>
            <small>{x.reason}</small>
          </div>)}
        </div>
      </div>
    </div>}
  </section>
}
