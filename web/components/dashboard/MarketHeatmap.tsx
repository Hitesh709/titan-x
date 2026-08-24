"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Activity, Radio } from "lucide-react"
import api from "@/lib/api"
import type { BatchQuotesResponse, MarketQuote, ResearchCompanyPage } from "@/types"

const REFRESH_MS = 30_000
const MAX_COMPANIES = 100
const SIDE_COUNT = 50

export default function MarketHeatmap() {
  const [quotes, setQuotes] = useState<MarketQuote[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      // Universe = the 100 largest active companies. Quotes themselves are
      // fetched separately from the real-time market-data endpoint.
      const universe = await api.get<ResearchCompanyPage>(
        "/research/companies?sort_by=market_cap&sort_desc=true&limit=100&skip=0"
      )
      const symbols = (universe.items ?? [])
        .map((x) => x.symbol)
        .filter(Boolean)
        .slice(0, MAX_COMPANIES)

      if (!symbols.length) return

      const res = await api.get<BatchQuotesResponse & { live?: boolean; source?: string }>(
        `/market-data/quotes?symbols=${encodeURIComponent(symbols.join(","))}`
      )
      const live = (res.quotes ?? []).filter(
        (q) => q.last_price != null && q.change_percent != null
      )

      if (mounted.current) {
        setQuotes(live)
        setLastUpdated(new Date())
      }
    } catch {
      // Keep the last successful live snapshot during temporary feed failures.
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void load()
    const timer = setInterval(() => void load(true), REFRESH_MS)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [load])

  const ranked = [...quotes].sort(
    (a, b) => (b.change_percent ?? b.change ?? 0) - (a.change_percent ?? a.change ?? 0)
  )
  const winners = ranked.filter((q) => (q.change_percent ?? q.change ?? 0) > 0).slice(0, SIDE_COUNT)
  const losers = ranked
    .filter((q) => (q.change_percent ?? q.change ?? 0) < 0)
    .sort((a, b) => (a.change_percent ?? a.change ?? 0) - (b.change_percent ?? b.change ?? 0))
    .slice(0, SIDE_COUNT)

  const max = Math.max(
    ...ranked.map((q) => Math.abs(q.change_percent ?? q.change ?? 0)),
    1
  )

  const StockBox = ({ q, positive }: { q: MarketQuote; positive: boolean }) => {
    const change = q.change_percent ?? q.change ?? 0
    const intensity = Math.min(Math.abs(change) / max, 1)
    const alpha = 0.16 + intensity * 0.52

    return (
      <Link
        href={`/dashboard/stocks/${q.symbol}`}
        title={`${q.name ?? q.symbol} · ₹${q.last_price?.toFixed(2)} · ${positive ? "+" : ""}${change.toFixed(2)}%`}
        className="group aspect-square min-w-0 rounded-md border border-white/5 p-1.5 sm:p-2 flex flex-col justify-between transition-all hover:scale-[1.04] hover:z-10 hover:border-white/40"
        style={{
          background: positive
            ? `rgba(16,185,129,${alpha})`
            : `rgba(239,68,68,${alpha})`,
        }}
      >
        <span className="text-[9px] sm:text-[10px] lg:text-[11px] font-bold text-white truncate">
          {q.symbol}
        </span>
        <span className="text-[8px] sm:text-[9px] text-white/60 truncate">
          ₹{q.last_price?.toFixed(2)}
        </span>
        <span
          className={`text-[9px] sm:text-[10px] lg:text-[11px] font-bold ${
            positive ? "text-emerald-200" : "text-red-200"
          }`}
        >
          {positive ? "+" : ""}{change.toFixed(2)}%
        </span>
      </Link>
    )
  }

  return (
    <section className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-titan-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Market Heatmap</h2>
            <p className="text-[11px] text-gray-500">
              Top 100 NSE companies · live winners vs losers
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider">
          <Radio size={11} className="text-emerald-400" />
          <span className="text-emerald-400">LIVE</span>
          <span className="text-gray-600">
            {lastUpdated ? lastUpdated.toLocaleTimeString() : loading ? "loading" : "—"}
          </span>
        </div>
      </div>

      {ranked.length === 0 ? (
        <div className="p-8 text-center text-sm text-gray-600">
          Loading real market quotes…
        </div>
      ) : (
        <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] overflow-hidden">
            <div className="px-3 py-2 border-b border-emerald-500/10 flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-300">TOP 50 WINNERS</span>
              <span className="text-[10px] text-emerald-400">{winners.length}/50</span>
            </div>
            <div className="p-2 grid grid-cols-5 sm:grid-cols-7 lg:grid-cols-10 gap-1.5">
              {winners.map((q) => (
                <StockBox key={q.symbol} q={q} positive />
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-red-500/20 bg-red-500/[0.03] overflow-hidden">
            <div className="px-3 py-2 border-b border-red-500/10 flex items-center justify-between">
              <span className="text-xs font-bold text-red-300">TOP 50 LOSERS</span>
              <span className="text-[10px] text-red-400">{losers.length}/50</span>
            </div>
            <div className="p-2 grid grid-cols-5 sm:grid-cols-7 lg:grid-cols-10 gap-1.5">
              {losers.map((q) => (
                <StockBox key={q.symbol} q={q} positive={false} />
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="px-5 py-3 border-t border-titan-800/30 text-[10px] text-gray-600">
        Real Yahoo Finance quote feed · green = gain · red = loss · refreshes every 30 seconds.
        No synthetic prices are used in this heatmap.
      </div>
    </section>
  )
}
