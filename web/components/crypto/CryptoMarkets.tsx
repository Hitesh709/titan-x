"use client"
import {useEffect,useMemo,useState} from "react"
import {ArrowDownRight,ArrowUpRight,RefreshCw,Search,SlidersHorizontal} from "lucide-react"
import Link from "next/link"
import api from "@/lib/api"
import {useCryptoLivePrices} from "./CryptoLiveTicker"
type Row={symbol:string;lastPrice:number;priceChangePercent:number;quoteVolume:number;highPrice:number;lowPrice:number}
const money=(n:number)=>n>=1000?n.toLocaleString("en-US",{maximumFractionDigits:2}):n.toLocaleString("en-US",{maximumFractionDigits:8})
export default function CryptoMarkets(){
 const [rows,setRows]=useState<Row[]>([]),[q,setQ]=useState(""),[sort,setSort]=useState<"volume"|"change"|"price">("volume"),[loading,setLoading]=useState(true),[error,setError]=useState("")
 const {prices}=useCryptoLivePrices()
 const load=async()=>{setLoading(true);try{const x=await api.get<{symbols:Row[]}>("/crypto-market/universe?limit=1000");setRows(x.symbols);setError("")}catch(e){setError(e instanceof Error?e.message:"Crypto universe unavailable")}finally{setLoading(false)}}
 useEffect(()=>{void load();const id=window.setInterval(load,60000);return()=>window.clearInterval(id)},[])
 const filtered=useMemo(()=>rows.filter(x=>!q||x.symbol.includes(q.toUpperCase())).sort((a,b)=>sort==="change"?b.priceChangePercent-a.priceChangePercent:sort==="price"?b.lastPrice-a.lastPrice:b.quoteVolume-a.quoteVolume),[rows,q,sort])
 return <div className="space-y-5">
  <div className="flex flex-wrap justify-between gap-3"><div><div className="tx-terminal-badge w-fit">CRYPTO MARKET UNIVERSE</div><h1 className="text-3xl font-black mt-3">Markets</h1><p className="text-sm text-slate-500 mt-1">Live spot universe · dynamic symbols · exchange-provider fallback</p></div><button className="btn-primary text-xs" onClick={()=>void load()}><RefreshCw size={13} className={loading?"animate-spin":""}/> Refresh</button></div>
  <div className="glass-card p-4 flex flex-wrap gap-3 items-center"><div className="relative flex-1 min-w-[220px]"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-cyan-500"/><input value={q} onChange={e=>setQ(e.target.value)} className="tx-input w-full pl-9" placeholder="Search BTC, ETH, SOL, meme coins, any USDT pair…"/></div><SlidersHorizontal size={16} className="text-slate-500"/>{(["volume","change","price"] as const).map(x=><button key={x} onClick={()=>setSort(x)} className={"tx-tab "+(sort===x?"tx-tab-active":"")}>{x.toUpperCase()}</button>)}</div>
  {error&&<div className="glass-card p-4 text-red-300 border border-red-500/30">{error}</div>}
  <div className="glass-card overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-xs"><thead><tr className="border-b border-blue-900/30 text-slate-600 uppercase tracking-wider"><th className="text-left p-4">Pair</th><th className="text-right p-4">Live Price</th><th className="text-right p-4">24h</th><th className="text-right p-4">24h Volume</th><th className="text-right p-4">High</th><th className="text-right p-4">Low</th><th className="p-4"></th></tr></thead><tbody>{filtered.slice(0,500).map(x=>{const live=prices[x.symbol]?.price??x.lastPrice;const ch=prices[x.symbol]?.changePercent??x.priceChangePercent;const up=ch>=0;return <tr key={x.symbol} className="border-b border-blue-900/15 hover:bg-cyan-500/[.03]"><td className="p-4"><b className="text-white">{x.symbol.replace("USDT","")}</b><span className="text-slate-600">/USDT</span></td><td className="p-4 text-right text-white">$ {money(live)}</td><td className={"p-4 text-right "+(up?"text-emerald-400":"text-red-400")}>{up?<ArrowUpRight size={12} className="inline"/>:<ArrowDownRight size={12} className="inline" />}{ch.toFixed(2)}%</td><td className="p-4 text-right text-slate-400">$ {money(x.quoteVolume)}</td><td className="p-4 text-right text-slate-500">$ {money(x.highPrice)}</td><td className="p-4 text-right text-slate-500">$ {money(x.lowPrice)}</td><td className="p-4 text-right"><Link className="tx-tab" href={"/crypto/markets?symbol="+x.symbol}>Analyze</Link></td></tr>})}</tbody></table></div></div>
 </div>
}
