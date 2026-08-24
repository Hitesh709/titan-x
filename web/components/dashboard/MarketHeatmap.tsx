"use client"

import Link from "next/link"
import { Activity } from "lucide-react"
import type { MarketQuote } from "@/types"

export default function MarketHeatmap({ quotes }: { quotes: MarketQuote[] }) {
  const items = quotes.filter((q) => q.last_price != null).slice(0, 24)
  const max = Math.max(...items.map((q) => Math.abs(q.change_percent ?? q.change ?? 0)), 1)

  return (
    <section className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
        <div className="flex items-center gap-2"><Activity size={16} className="text-titan-400" /><div><h2 className="text-sm font-semibold text-white">Market Heatmap</h2><p className="text-[11px] text-gray-500">Live relative performance across tracked equities</p></div></div>
        <span className="text-[10px] uppercase tracking-wider text-gray-500">Auto refreshed</span>
      </div>
      {items.length === 0 ? <div className="p-8 text-center text-sm text-gray-600">Live quote data unavailable.</div> : <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {items.map((q) => {
          const change = q.change_percent ?? q.change ?? 0
          const positive = change >= 0
          const intensity = Math.min(Math.abs(change) / max, 1)
          const alpha = 0.08 + intensity * 0.28
          return <Link key={q.symbol} href={`/dashboard/stocks/${q.symbol}`} className="group rounded-xl border border-white/5 p-3 min-h-[82px] flex flex-col justify-between transition-all hover:-translate-y-0.5 hover:border-white/15" style={{ background: positive ? `rgba(16,185,129,${alpha})` : `rgba(239,68,68,${alpha})` }}>
            <div className="flex justify-between gap-2"><span className="text-xs font-semibold text-white">{q.symbol}</span><span className="text-[10px] text-gray-500">{q.exchange}</span></div>
            <div className={`text-sm font-bold ${positive ? "text-emerald-300" : "text-red-300"}`}>{positive ? "+" : ""}{change.toFixed(2)}%</div>
            <div className="text-[10px] text-gray-500 truncate">{q.name}</div>
          </Link>
        })}
      </div>}
    </section>
  )
}
