"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TrendingUp, TrendingDown, Radio } from "lucide-react"
import api from "@/lib/api"
import type { BatchQuotesResponse, MarketQuote } from "@/types"
import { formatCompactNumber, getChangeColor } from "@/lib/utils"
import { WidgetError, WidgetLoading } from "@/components/dashboard/widget"

const REFRESH_INTERVAL_MS = 5_000

const TICKERS = [
  "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "SBIN", "ITC",
  "LT", "HINDUNILVR", "KOTAKBANK", "BAJFINANCE", "AXISBANK", "MARUTI", "TITAN", "SUNPHARMA",
  "ADANIENT", "WIPRO", "ONGC", "NTPC", "POWERGRID", "ASIANPAINT", "ULTRACEMCO", "HCLTECH",
  "TATAMOTORS", "JSWSTEEL",
]

function num(v: number | null | undefined, digits = 2): string {
  return v == null ? "-" : v.toFixed(digits)
}

export default function LiveQuotes() {
  const [quotes, setQuotes] = useState<MarketQuote[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${TICKERS.join(",")}`)
      if (!mounted.current) return
      setQuotes(res.quotes ?? [])
      setLastUpdated(new Date())
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load live quotes")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void load()
    const timer = setInterval(() => void load(true), REFRESH_INTERVAL_MS)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [load])

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
          <h3 className="text-sm font-semibold text-white">Live Quotes</h3>
          <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 uppercase tracking-wider">
            <Radio size={12} /> Auto-refresh every {REFRESH_INTERVAL_MS / 1000}s
          </span>
        </div>
        <span className="text-[11px] text-gray-500">
          {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for live feed"}
        </span>
      </div>

      {loading && quotes.length === 0 ? (
        <WidgetLoading lines={6} />
      ) : error && quotes.length === 0 ? (
        <WidgetError message={error} onRetry={() => void load()} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30 text-gray-500 font-medium text-xs uppercase tracking-wider">
                <th className="text-left py-3 px-5">Symbol</th>
                <th className="text-left py-3 px-4 hidden md:table-cell">Company</th>
                <th className="text-right py-3 px-4">Last Price</th>
                <th className="text-right py-3 px-4">Change</th>
                <th className="text-right py-3 px-4">Change %</th>
                <th className="text-right py-3 px-4 hidden sm:table-cell">Volume</th>
              </tr>
            </thead>
            <tbody>
              {quotes.map((q) => {
                const up = (q.change ?? 0) >= 0
                const state = q.last_price == null ? "text-gray-500" : getChangeColor(q.change ?? 0)
                return (
                  <tr key={q.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                    <td className="py-3 px-5">
                      <span className="text-white font-semibold">{q.symbol}</span>
                      <span className="ml-2 text-[10px] text-emerald-500/80">{q.exchange}</span>
                    </td>
                    <td className="py-3 px-4 text-gray-400 hidden md:table-cell">{q.name}</td>
                    <td className={`py-3 px-4 text-right font-medium ${state}`}>{num(q.last_price)}</td>
                    <td className={`py-3 px-4 text-right font-medium ${state}`}>
                      {q.change == null ? "-" : `${up ? "+" : ""}${q.change.toFixed(2)}`}
                    </td>
                    <td className={`py-3 px-4 text-right font-medium ${state}`}>
                      {q.change_percent == null ? "-" : (
                        <span className="inline-flex items-center gap-1">
                          {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                          {up ? "" : ""}{q.change_percent.toFixed(2)}%
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-400 hidden sm:table-cell">{formatCompactNumber(q.volume ?? 0)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}