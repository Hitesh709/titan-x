"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Activity, Radio } from "lucide-react"
import api from "@/lib/api"

type Q = { symbol:string; name?:string|null; last_price?:number|null; change_percent?:number|null; change?:number|null }
const NIFTY50 = [
 ["RELIANCE",9.2],["HDFCBANK",8.8],["ICICIBANK",7.7],["BHARTIARTL",5.9],["TCS",4.1],["INFY",3.0],["SBIN",3.1],["ITC",3.0],["LT",3.0],["AXISBANK",2.8],
 ["KOTAKBANK",2.7],["M&M",2.7],["BAJFINANCE",2.5],["HINDUNILVR",2.3],["MARUTI",1.9],["SUNPHARMA",1.8],["NTPC",1.8],["BEL",1.6],["TITAN",1.6],["ADANIENT",1.5],
 ["ADANIPORTS",1.4],["POWERGRID",1.5],["ULTRACEMCO",1.4],["ONGC",1.3],["WIPRO",1.2],["TATASTEEL",1.2],["JSWSTEEL",1.2],["HCLTECH",1.2],["TECHM",1.1],["NESTLEIND",1.1],
 ["ASIANPAINT",1.0],["TATAMOTORS",1.0],["COALINDIA",0.9],["HINDALCO",0.9],["GRASIM",0.9],["CIPLA",0.9],["EICHERMOT",0.8],["DRREDDY",0.8],["TRENT",0.8],["SBILIFE",0.8],
 ["HDFCLIFE",0.8],["BRITANNIA",0.7],["APOLLOHOSP",0.7],["HEROMOTOCO",0.7],["BAJAJFINSV",0.7],["INDUSINDBK",0.7],["BPCL",0.7],["SHRIRAMFIN",0.7],["JIOFIN",0.7],["ETERNAL",0.7]
] as const

export default function NiftyHeatmap(){
 const [quotes,setQuotes]=useState<Q[]>([]),[loading,setLoading]=useState(true),[updated,setUpdated]=useState<Date|null>(null);const mounted=useRef(true)
 const load=useCallback(async()=>{try{const r=await api.get<{quotes:Q[]}>(`/market-data/quotes?symbols=${encodeURIComponent(NIFTY50.map(x=>x[0]).join(","))}`);if(mounted.current){setQuotes(r.quotes??[]);setUpdated(new Date())}}catch{}finally{if(mounted.current)setLoading(false)}},[])
 useEffect(()=>{mounted.current=true;void load();const t=setInterval(()=>void load(),30000);return()=>{mounted.current=false;clearInterval(t)}},[load])
 const by=useMemo(()=>new Map(quotes.map(q=>[q.symbol.toUpperCase(),q])),[quotes]);const maxMove=Math.max(1,...quotes.map(q=>Math.abs(q.change_percent??q.change??0)))
 return <div className="nifty-heatmap-wrap">
  <div className="nifty-heatmap-head"><div><div className="panel-title"><Activity size={13}/> NIFTY 50 HEATMAP <span>DAILY MOVE / INDEX IMPORTANCE</span></div><p>Live constituents · green = up · red = down · tile size is a visual weight proxy.</p></div><div className="nifty-live"><Radio size={10}/> {loading?"LOADING":"LIVE"} {updated&&<small>{updated.toLocaleTimeString("en-IN")}</small>}</div></div>
  {quotes.length===0?<div className="nifty-empty">Loading real NIFTY 50 market quotes…</div>:<div className="nifty-tiles">{NIFTY50.map(([symbol,weight],i)=>{const q=by.get(symbol),ch=q?.change_percent??q?.change??0,positive=ch>=0,alpha=.18+Math.min(Math.abs(ch)/maxMove,1)*.68,span=weight>=5?3:weight>=2.5?2:1;return <Link key={`${symbol}-${i}`} href={`/dashboard/stocks/${symbol}`} className="nifty-tile" style={{gridColumn:`span ${span}`,gridRow:`span ${span}`,backgroundColor:positive?`rgba(0,240,160,${alpha})`:`rgba(255,55,85,${alpha})`}} title={`${q?.name??symbol} · ${positive?"+":""}${ch.toFixed(2)}% · ₹${q?.last_price?.toFixed(2)??"—"}`}><strong>{symbol}</strong><span>{positive?"+":""}{ch.toFixed(2)}%</span>{q?.last_price!=null&&<small>₹{q.last_price.toLocaleString("en-IN",{maximumFractionDigits:0})}</small>}</Link>})}</div>}
  <div className="nifty-heatmap-foot"><span><i className="gain-dot"/> GAIN</span><span><i className="loss-dot"/> LOSS</span><span className="heatmap-note">Real quotes · refresh 30s · click tile for stock chart</span></div>
  <style jsx>{` .nifty-heatmap-wrap{height:100%;min-height:330px;display:flex;flex-direction:column;gap:10px}.nifty-heatmap-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.nifty-heatmap-head p{margin:5px 0 0;color:#60758d;font-size:9px;line-height:1.4}.nifty-live{display:flex;align-items:center;gap:5px;color:#3fe2a0;font:700 8px 'JetBrains Mono',monospace;white-space:nowrap}.nifty-live small{color:#61758e;font-weight:500}.nifty-tiles{flex:1;min-height:245px;display:grid;grid-template-columns:repeat(10,minmax(0,1fr));grid-auto-rows:24px;gap:3px;align-content:start;background:repeating-linear-gradient(0deg,rgba(70,140,230,.025) 0 1px,transparent 1px 24px);overflow:hidden}.nifty-tile{min-width:0;min-height:24px;padding:5px;border:1px solid rgba(255,255,255,.09);border-radius:5px;color:#fff;text-decoration:none;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;transition:transform .16s,border-color .16s,filter .16s}.nifty-tile:hover{transform:scale(1.04);z-index:3;border-color:rgba(255,255,255,.7);filter:brightness(1.15)}.nifty-tile strong{font:800 9px 'JetBrains Mono',monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nifty-tile span{font:800 10px 'JetBrains Mono',monospace}.nifty-tile small{font-size:7px;color:rgba(255,255,255,.62)}.nifty-heatmap-foot{display:flex;gap:14px;align-items:center;color:#657890;font:700 7px 'JetBrains Mono',monospace}.nifty-heatmap-foot i{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px}.gain-dot{background:#2ee39d;box-shadow:0 0 8px #2ee39d}.loss-dot{background:#ff526b;box-shadow:0 0 8px #ff526b}.heatmap-note{margin-left:auto}@media(max-width:760px){.nifty-heatmap-wrap{min-height:420px}.nifty-tiles{grid-template-columns:repeat(6,minmax(0,1fr));grid-auto-rows:27px}.nifty-tile strong{font-size:8px}.nifty-tile span{font-size:9px}.nifty-heatmap-head{flex-direction:column}.heatmap-note{margin-left:0}}`}</style>
 </div>
}
