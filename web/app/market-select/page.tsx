"use client"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { BarChart3, Bitcoin, ArrowRight, ShieldCheck, Zap, Activity } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
export default function MarketSelectPage(){
 const router=useRouter();const {user,loading}=useAuth()
 useEffect(()=>{if(!loading&&!user)router.replace("/login")},[loading,user,router])
 if(loading||!user)return <main className="min-h-screen bg-[#020713] flex items-center justify-center text-cyan-300">Loading TITAN X…</main>
 const stock=["NIFTY 50","20 Indicators","Fusion AI"],crypto=["BTC / ETH","24/7 Market","Crypto AI"]
 return <main className="tx-market-select min-h-screen bg-[#020713] text-white flex items-center justify-center p-6 relative overflow-hidden"><div className="tx-select-grid"/>
  <div className="relative z-10 w-full max-w-6xl"><div className="text-center mb-10"><div className="tx-terminal-badge mx-auto w-fit mb-4">SELECT MARKET ENGINE</div><h1 className="text-4xl md:text-5xl font-black">Choose Your <span className="text-cyan-300">Market</span></h1><p className="text-slate-500 mt-3">Choose a dedicated trading environment. Stock and Crypto remain separate inside TITAN X.</p></div>
   <div className="grid md:grid-cols-2 gap-6">
    <button onClick={()=>router.push("/dashboard")} className="tx-market-choice text-left"><div className="tx-choice-glow"/><div className="flex items-start justify-between"><div className="tx-choice-icon"><BarChart3 size={32}/></div><span className="tx-choice-live">NSE • GLOBAL EQUITIES</span></div><h2 className="text-3xl font-bold mt-8">Stock Market</h2><p className="text-slate-400 mt-2">NSE equities, indices, technical analysis, Titan X Fusion, paper trading, strategies and research.</p><div className="grid grid-cols-3 gap-2 mt-8">{stock.map(x=><span key={x} className="tx-choice-chip">{x}</span>)}</div><div className="mt-8 flex items-center gap-2 text-cyan-300 font-bold">Enter Stock Terminal <ArrowRight size={18}/></div></button>
    <button onClick={()=>router.push("/crypto")} className="tx-market-choice tx-crypto-choice text-left"><div className="tx-choice-glow"/><div className="flex items-start justify-between"><div className="tx-choice-icon tx-crypto-icon"><Bitcoin size={32}/></div><span className="tx-choice-live tx-crypto-live">24/7 • DIGITAL ASSETS</span></div><h2 className="text-3xl font-bold mt-8">Crypto Market</h2><p className="text-slate-400 mt-2">24/7 digital-asset intelligence with live prices, market movers, technical analysis and a dedicated crypto terminal.</p><div className="grid grid-cols-3 gap-2 mt-8">{crypto.map(x=><span key={x} className="tx-choice-chip tx-crypto-chip">{x}</span>)}</div><div className="mt-8 flex items-center gap-2 text-fuchsia-300 font-bold">Enter Crypto Terminal <ArrowRight size={18}/></div></button>
   </div>
   <div className="flex flex-wrap justify-center gap-6 mt-8 text-[10px] uppercase tracking-widest text-slate-600"><span><ShieldCheck className="inline mr-1 text-emerald-400" size={13}/> Separate market data</span><span><Zap className="inline mr-1 text-cyan-400" size={13}/> Same neon engine</span><span><Activity className="inline mr-1 text-purple-400" size={13}/> Independent dashboards</span></div>
  </div>
 </main>
}