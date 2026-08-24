"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Radar, Zap, TrendingUp, TrendingDown, Activity, Target, ShieldCheck } from "lucide-react"
import api from "@/lib/api"
import type { ResearchCompany, ResearchCompanyPage } from "@/types"

const REFRESH_MS = 30000

function strategyScore(x: ResearchCompany) {
  const confidence = Math.max(0, Math.min(100, x.confidence ?? 0))
  const modelScore = Math.max(0, Math.min(100, x.score ?? 0))
  const expected = Math.max(-20, Math.min(20, x.predicted_return_pct ?? 0))
  const direction = x.direction === "BUY" ? 1 : x.direction === "SELL" ? -1 : 0
  // Titan Radar ranks the live recommendation using model score, confidence,
  // expected return and direction. It does not invent a signal when research is absent.
  return modelScore * 0.45 + confidence * 0.35 + expected * 2 * direction * 0.20
}

export default function TitanRadar({ items: initialItems }: { items: ResearchCompany[] }) {
  const [items, setItems] = useState<ResearchCompany[]>(initialItems)
  const [live, setLive] = useState(false)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await api.get<ResearchCompanyPage>(
        "/research/companies?sort_by=score&sort_desc=true&limit=100&skip=0"
      )
      if (mounted.current) {
        setItems((res.items ?? []).filter((x) => x.has_research))
        setLive(true)
      }
    } catch {
      // Keep the latest successful radar snapshot.
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void load()
    const timer = setInterval(() => void load(), REFRESH_MS)
    return () => { mounted.current = false; clearInterval(timer) }
  }, [load])

  const ranked = items.filter((x) => x.has_research).map((x) => ({ ...x, radarScore: strategyScore(x) })).sort((a, b) => b.radarScore - a.radarScore)
  const breakouts = ranked.filter((x) => x.direction === "BUY" && (x.predicted_return_pct ?? 0) > 0 && (x.confidence ?? 0) >= 60).slice(0, 5)
  const momentum = [...ranked].filter((x) => x.direction === "BUY").slice(0, 5)
  const bullish = [...ranked].filter((x) => x.direction === "BUY").sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)).slice(0, 5)
  const bearish = [...ranked].filter((x) => x.direction === "SELL").sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)).slice(0, 5)

  const lanes = [
    { label: "BREAKOUT SETUPS", icon: <Zap size={14} />, items: breakouts },
    { label: "HIGH MOMENTUM", icon: <Activity size={14} />, items: momentum },
    { label: "BULLISH", icon: <TrendingUp size={14} />, items: bullish },
    { label: "BEARISH", icon: <TrendingDown size={14} />, items: bearish },
  ]

  return <section className="glass-card overflow-hidden border border-titan-500/20 bg-[radial-gradient(circle_at_50%_0%,rgba(56,189,248,.12),transparent_45%)]">
    <div className="px-5 py-4 border-b border-titan-800/30 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-titan-500/10 border border-titan-400/20 flex items-center justify-center text-titan-300"><Radar size={19} /></div>
        <div><h2 className="text-base font-semibold text-white">TITAN X RADAR</h2><p className="text-[11px] text-gray-500">Live multi-factor opportunity scanner</p></div>
      </div>
      <span className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[.18em] ${live ? "text-emerald-400" : "text-gray-500"}`}><span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-emerald-400" : "bg-gray-500"}`} />{live ? "Live strategy" : "Connecting"}</span>
    </div>
    <div className="px-5 py-3 border-b border-titan-800/30 flex flex-wrap items-center gap-4 text-[10px] text-gray-500"><span className="inline-flex items-center gap-1"><Target size={12} className="text-titan-400" /> Score 45%</span><span>Confidence 35%</span><span>Expected return + direction 20%</span><span className="inline-flex items-center gap-1"><ShieldCheck size={12} className="text-emerald-400" /> Only active research signals</span></div>
    <div className="grid md:grid-cols-4 gap-px bg-titan-900/40">
      {lanes.map((lane) => <div key={lane.label} className="bg-black/20 p-4 min-h-[170px]">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-3">{lane.icon}{lane.label}</div>
        {lane.items.length ? lane.items.slice(0, 4).map((x) => <Link key={x.symbol} href={`/dashboard/stocks/${x.symbol}`} className="flex items-center justify-between py-2 border-b border-white/5 hover:bg-white/5 rounded px-1 transition-colors">
          <span className="text-xs font-medium text-white">{x.symbol}</span>
          <span className={x.direction === "SELL" ? "text-red-400 text-[11px]" : "text-emerald-400 text-[11px]"}>{x.predicted_return_pct != null ? `${x.predicted_return_pct >= 0 ? "+" : ""}${x.predicted_return_pct.toFixed(2)}%` : x.direction}</span>
        </Link>) : <div className="text-xs text-gray-600 py-6">No qualifying live signal</div>}
      </div>)}
    </div>
    <div className="px-5 py-3 border-t border-titan-800/30 text-[11px] text-gray-500">Radar uses Titan X's active research recommendation fields and refreshes every 30 seconds. It ranks signals; it does not guarantee returns.</div>
  </section>
}
