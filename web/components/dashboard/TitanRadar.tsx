"use client"

import Link from "next/link"
import { Radar, Zap, TrendingUp, TrendingDown, Newspaper, Activity } from "lucide-react"
import type { ResearchCompany } from "@/types"

export default function TitanRadar({ items }: { items: ResearchCompany[] }) {
  const candidates = items.filter((x) => x.has_research).slice(0, 12)
  const breakouts = candidates.filter((x) => (x.predicted_return_pct ?? 0) >= 3).slice(0, 5)
  const momentum = [...candidates].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 5)
  const bullish = candidates.filter((x) => x.direction === "BUY").slice(0, 5)
  const bearish = candidates.filter((x) => x.direction === "SELL").slice(0, 5)

  const lanes = [
    { label: "BREAKOUTS", icon: <Zap size={14} />, items: breakouts },
    { label: "HIGH MOMENTUM", icon: <Activity size={14} />, items: momentum },
    { label: "BULLISH", icon: <TrendingUp size={14} />, items: bullish },
    { label: "BEARISH", icon: <TrendingDown size={14} />, items: bearish },
  ]

  return (
    <section className="glass-card overflow-hidden border border-titan-500/20 bg-[radial-gradient(circle_at_50%_0%,rgba(56,189,248,.12),transparent_45%)]">
      <div className="px-5 py-4 border-b border-titan-800/30 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-titan-500/10 border border-titan-400/20 flex items-center justify-center text-titan-300"><Radar size={19} /></div>
          <div><h2 className="text-base font-semibold text-white">TITAN X RADAR</h2><p className="text-[11px] text-gray-500">AI market opportunity scanner</p></div>
        </div>
        <span className="text-[10px] uppercase tracking-[.18em] text-emerald-400">Live research signals</span>
      </div>
      <div className="grid md:grid-cols-4 gap-px bg-titan-900/40">
        {lanes.map((lane) => (
          <div key={lane.label} className="bg-black/20 p-4 min-h-[170px]">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-3">{lane.icon}{lane.label}</div>
            {lane.items.length ? lane.items.slice(0, 4).map((x) => (
              <Link key={x.symbol} href={`/dashboard/stocks/${x.symbol}`} className="flex items-center justify-between py-2 border-b border-white/5 hover:bg-white/5 rounded px-1 transition-colors">
                <span className="text-xs font-medium text-white">{x.symbol}</span>
                <span className={x.direction === "SELL" ? "text-red-400 text-[11px]" : "text-emerald-400 text-[11px]"}>{x.predicted_return_pct != null ? `${x.predicted_return_pct >= 0 ? "+" : ""}${x.predicted_return_pct.toFixed(2)}%` : x.direction}</span>
              </Link>
            )) : <div className="text-xs text-gray-600 py-6">No active signal</div>}
          </div>
        ))}
      </div>
      <div className="px-5 py-3 border-t border-titan-800/30 flex items-center gap-2 text-[11px] text-gray-500"><Newspaper size={12} /> Radar ranks available research signals; it does not guarantee returns.</div>
    </section>
  )
}
