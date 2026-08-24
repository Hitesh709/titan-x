"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Activity } from "lucide-react"
import api from "@/lib/api"
import type { BatchQuotesResponse, MarketQuote, ResearchCompanyPage } from "@/types"

const REFRESH_MS = 30000
const MAX_COMPANIES = 100

export default function MarketHeatmap() {
  const [quotes, setQuotes] = useState<MarketQuote[]>([])
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      // Get the actual NSE universe from Titan X rather than a hard-coded watchlist.
      const universe = await api.get<ResearchCompanyPage>(
        "/research/companies?sort_by=market_cap&sort_desc=true&limit=100&skip=0"
      )
      const symbols = (universe.items ?? []).map((x) => x.symbol).filter(Boolean).slice(0, MAX_COMPANIES)
      if (!symbols.length) return

      const res = await api.get<BatchQuotesResponse>(
        `/market-data/quotes?symbols=${encodeURIComponent(symbols.join(","))}`
      )
      const live = (res.quotes ?? []).filter((q) => q.last_price != null)
      if (mounted.current) setQuotes(live.slice(0, MAX_COMPANIES))
    } catch {
      // Keep the last successful live snapshot visible during a transient provider/API failure.
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void load()
    const timer = setInterval(() => void load(), REFRESH_MS)
    return () => { mounted.current = false; clearInterval(timer) }
  }, [load])

  const items = quotes.slice(0, MAX_COMPANIES)
  const max = Math.max(...items.map((q) => Math.abs(q.change_percent ?? q.change ?? 0)), 1)

  return <section className="glass-card overflow-hidden">
    <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Activity size={16} className="text-titan-400" />
        <div><h2 className="text-sm font-semibold text-white">Market Heatmap</h2><p className="text-[11px] text-gray-500">Top 100 NSE companies · live price movement</p></div>
      </div>
      <span className="text-[10px] uppercase tracking-wider text-emerald-400">{loading ? "Loading live data" : `${items.length} live`}</span>
    </div>
    {items.length === 0 ? <div className="p-8 text-center text-sm text-gray-600">Live quote data unavailable. Retrying automatically.</div> : <div className="p-3 grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-1.5">
      {items.map((q) => {
        const change = q.change_percent ?? q.change ?? 0
        const positive = change >= 0
        const intensity = Math.min(Math.abs(change) / max, 1)
        const alpha = 0.16 + intensity * 0.42
        return <Link key={q.symbol} href={`/dashboard/stocks/${q.symbol}`} title={`${q.name ?? q.symbol}: ${positive ? "+" : ""}${change.toFixed(2)}%`} className="group aspect-square rounded-md border border-white/5 p-2 flex flex-col justify-between transition-all hover:scale-[1.03] hover:border-white/30" style={{ background: positive ? `rgba(16,185,129,${alpha})` : `rgba(239,68,68,${alpha})` }}>
          <span className="text-[10px] sm:text-[11px] font-bold text-white truncate">{q.symbol}</span>
          <span className={`text-[10px] sm:text-[11px] font-bold ${positive ? "text-emerald-200" : "text-red-200"}`}>{positive ? "+" : ""}{change.toFixed(2)}%</span>
        </Link>
      })}
    </div>}
    <div className="px-5 py-3 border-t border-titan-800/30 text-[10px] text-gray-600">Green = live gain · Red = live loss · intensity reflects the magnitude of today's percentage move · refreshes every 30 seconds.</div>
  </section>
}
