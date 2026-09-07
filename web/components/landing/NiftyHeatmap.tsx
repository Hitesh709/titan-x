"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Activity, Radio } from "lucide-react"
import api from "@/lib/api"

type Q = { symbol:string; name?:string|null; last_price?:number|null; change_percent?:number|null; change?:number|null; volume?:number|null }

// NIFTY 50 trading symbols. Tile size is a visual proxy for index importance; colour/intensity is today's move.
const NIFTY50 = [
 ["RELIANCE",9.2],["HDFCBANK",8.8],["BHARTIARTL",5.9],["TCS",4.1],["ICICIBANK",7.7],["INFY",3.0],["SBIN",3.1],["ITC",3.0],["LT",3.0],["AXISBANK",2.8],
 ["KOTAKBANK",2.7],["M&M",2.7],["BAJFINANCE",2.5],["HINDUNILVR",2.3],["MARUTI",1.9],["SUNPHARMA",1.8],["NTPC",1.8],["BHCL",1.6],["TITAN",1.6],["ADANIENT",1.5],
 ["ADANIPORTS",1.4],["POWERGRID",1.5],["ULTRACEMCO",1.4],["ONGC",1.3],["WIPRO",1.2],["TATASTEEL",1.2],["JSWSTEEL",1.2],["HCLTECH",1.2],["TECHM",1.1],["NESTLEIND",1.1],
 ["ASIANPAINT",1.0],["TATAMOTORS",1.0],["BEL",1.0],["COALINDIA",0.9],["HINDALCO",0.9],["GRASIM",0.9],["CIPLA",0.9],["EICHERMOT",0.8],["DRREDDY",0.8],["TRENT",0.8],
 ["SBILIFE",0.8],["HDFCLIFE",0.8],["BRITANNIA",0.7],["APOLLOHOSP",0.7],["HEROMOTOCO",0.7],["BAJAJFINSV",0.7],["INDUSINDBK",0.7],["BPCL",0.7],["SHRIRAMFIN",0.7],["TATASTEEL",1.0]
] as const

export default function NiftyHeatmap(){
 const [quotes,setQuotes]=useState<Q[]>([]),[loading,setLoading]=useState(true),[updated,setUpdated]=useState<Date|null>(null); const mounted=useRef(true)
 const load=useCallback(async()=>{try{const symbols=[...new Set(NIFTY50.map(x=>x[0]))];const r=await api.get<{quotes:Q[]}>(`/market-data/quotes?symbols=${encodeURIComponent(symbols.join(","))}`);if(mounted.current){setQuotes(r.quotes??[]);setUpdated(new Date())}}catch{}finally{if(mounted.current)setLoading(false)}},[])
 useEffect(()=>{mounted.current=true;void load();const t=setInterval(()=>void load(),30000);return()=>{mounted.current=false;clearInterval(t)}},[load])
 const by=useMemo(()=>new Map(quotes.map(q=>[q.symbol.toUpperCase(),q])),[quotes]); const maxMove=Math.max(1,...quotes.map(q=>Math.abs(q.change_percent??q.change??0)))
 return <div className="nifty-heatmap-wrap">
  <div className="nifty-heatmap-head"><div><div className="panel-title"><Activity size={13}/> NIFTY 50 HEATMAP <span>DAILY MOVE / INDEX IMPORTANCE</span></div><p>Green = up · red = down · tile size = visual index weight · click any stock for full chart</p></div><div className="nifty-live"><Radio size={10}/> {loading?"LOADING":"LIVE"} {updated&&<small>{updated.toLocaleTimeString("en-IN")}</small>}</div></div>
  {quotes.length===0?<div className="nifty-empty">Loading real NIFTY 50 market quotes…</div>:<div className="nifty-tiles">{NIFTY50.map(([symbol,weight],i)=>{const q=by.get(symbol);const ch=q?.change_percent??q?.change??0;const positive=ch>=0;const alpha=.18+Math.min(Math.abs(ch)/maxMove,1)*.68;const span=weight>=5?3:weight>=2.5?2:1;return <Link key={`${symbol}-${i}`} href={`/dashboard/stocks/${symbol}`} className={`nifty-tile s${span} ${positive?"gain":"loss"}`} style={{backgroundColor:positive?`rgba(0,240,160,${alpha})`:`rgba(255,55,85,${alpha})`}} title={`${q?.name??symbol} · ${positive?"+":""}${ch.toFixed(2)}% · ₹${q?.last_price?.toFixed(2)??"—"}`}><strong>{symbol}</strong><span>{positive?"+":""}{ch.toFixed(2)}%</span>{q?.last_price!=null&&<small>₹{q.last_price.toLocaleString("en-IN",{maximumFractionDigits:0})}</small>}</Link>})}</div>}
  <div className="nifty-heatmap-foot"><span><i className="gain-dot"/> Gainers</span><span><i className="loss-dot"/> Losers</span><span className="heatmap-note">Real market quotes · refresh 30s</span></div>
 </div>
}
