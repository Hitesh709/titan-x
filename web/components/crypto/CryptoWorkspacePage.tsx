"use client"

import { useEffect, useState } from "react"
import { ArrowRight, BarChart3, Bot, FlaskConical, ShieldCheck, Star } from "lucide-react"
import Link from "next/link"
import CryptoTechnicalPanel from "./CryptoTechnicalPanel"
import CryptoPaperTerminal from "./CryptoPaperTerminal"
import CryptoAnalytics from "./CryptoAnalytics"
import CryptoRecommendation from "./CryptoRecommendation"
import CryptoBotPanel from "./CryptoBotPanel"

const symbols=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"]

const info: Record<string,{title:string;description:string;icon:any}> = {
  backtesting:{title:"Crypto Backtesting",description:"Dedicated crypto strategy testing workspace. This route is isolated from the stock backtesting module.",icon:FlaskConical},
  risk:{title:"Crypto Risk Center",description:"Crypto-only position sizing, stop-loss, take-profit and paper execution controls.",icon:ShieldCheck},
  watchlists:{title:"Crypto Watchlists",description:"Crypto-native watchlist workspace for pairs and live market monitoring.",icon:Star},
  alerts:{title:"Crypto Alerts",description:"Crypto-only price and signal alert workspace.",icon:BarChart3},
  news:{title:"Crypto News & Insights",description:"Dedicated digital-asset research workspace.",icon:BarChart3},
  settings:{title:"Crypto Settings",description:"Settings for the Crypto Engine are kept separate from the Stock Market workspace.",icon:ShieldCheck},
}

export default function CryptoWorkspacePage({mode}:{mode:string}) {
  const [symbol,setSymbol]=useState("BTCUSDT")
  useEffect(()=>{ const value=new URLSearchParams(window.location.search).get("symbol")?.toUpperCase(); if(value && symbols.includes(value)) setSymbol(value) },[])

  if(mode==="markets") return <div className="space-y-5"><Header title="Crypto Markets" subtitle="Live 24/7 digital-asset market terminal" /><div className="glass-card p-4"><div className="tx-tabs">{symbols.map(s=><Link key={s} href={"/crypto/markets?symbol="+s} className={"tx-tab "+(s===symbol?"tx-tab-active":"")}>{s.replace("USDT","")}/USDT</Link>)}</div></div><CryptoTechnicalPanel symbol={symbol}/></div>
  if(mode==="analysis") return <div className="space-y-5"><Header title="Crypto Analysis" subtitle="Technical structure, multi-timeframe confirmation and performance" /><CryptoTechnicalPanel symbol={symbol}/><CryptoAnalytics/></div>
  if(mode==="research") return <div className="space-y-5"><Header title="Crypto Research" subtitle="Dedicated intraday and delivery/positional research signals" /><CryptoRecommendation symbol={symbol}/></div>
  if(mode==="recommendations") return <div className="space-y-5"><Header title="Crypto Recommendations" subtitle="Live research signals for digital assets" /><CryptoRecommendation symbol={symbol}/></div>
  if(mode==="portfolio") return <div className="space-y-5"><Header title="Crypto Portfolio" subtitle="Persistent crypto paper portfolio and performance" /><CryptoPaperTerminal symbol={symbol}/><CryptoAnalytics/></div>
  if(mode==="trading") return <div className="space-y-5"><Header title="Crypto Trading" subtitle="Dedicated crypto paper-trading terminal" /><CryptoPaperTerminal symbol={symbol}/></div>
  if(mode==="bot") return <div className="space-y-5"><Header title="Crypto Auto Bot" subtitle="Event-driven 24/7 crypto paper automation" /><CryptoBotPanel/><CryptoAnalytics/></div>

  const x=info[mode]||info.risk
  const Icon=x.icon
  return <div className="space-y-5"><Header title={x.title} subtitle={x.description}/><div className="glass-card p-8 max-w-4xl"><div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-300"><Icon size={22}/></div><h2 className="text-2xl font-black mt-5">{x.title}</h2><p className="text-sm text-slate-500 mt-2 max-w-2xl">{x.description}</p><div className="mt-6 rounded-xl border border-blue-900/30 bg-[#020b20] p-4"><div className="text-xs text-slate-400">Crypto workspace status</div><div className="text-emerald-300 font-bold mt-1">SEPARATE MODULE</div><p className="text-[11px] text-slate-600 mt-2">No stock dashboard components are mounted on this route.</p></div></div></div>
}

function Header({title,subtitle}:{title:string;subtitle:string}) {
 return <div className="flex flex-wrap items-end justify-between gap-3"><div><div className="tx-terminal-badge w-fit mb-3">CRYPTO ENGINE • 24/7</div><h1 className="text-3xl font-black">{title}</h1><p className="text-sm text-slate-500 mt-1">{subtitle}</p></div><Link href="/market-select" className="tx-tab">Market Hub <ArrowRight size={13}/></Link></div>
}
