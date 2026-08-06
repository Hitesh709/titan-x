"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { IndexSnapshot } from "@/types"
import { formatCurrency, formatPercent, getChangeColor, formatDate } from "@/lib/utils"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"
import LiveQuotes from "@/components/dashboard/LiveQuotes"

const HERO_INDICES = ["NIFTY", "SENSEX", "BANKNIFTY"]

export default function MarketsPage() {
  const [indices, setIndices] = useState<IndexSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<{ items: IndexSnapshot[] }>("/indices", { cacheTTL: 20_000 })
      if (!mounted.current) return
      setIndices(res.items ?? [])
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load index data")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  const hero = indices.filter((i) => HERO_INDICES.includes(i.symbol))
  const others = indices.filter((i) => !HERO_INDICES.includes(i.symbol))
  const tradeDate = indices[0]?.trade_date

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-500 text-sm">
            {tradeDate ? `As of ${formatDate(tradeDate)}` : "Live market data"}
          </p>
        </div>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-3">
          <WidgetLoading lines={4} />
          <WidgetLoading lines={4} />
          <WidgetLoading lines={4} />
        </div>
      ) : error ? (
        <WidgetError message={error} onRetry={handleRefresh} />
      ) : (
        <>
          {/* Live stock quotes (auto-refresh every 5s) */}
          <LiveQuotes />

          {/* Hero index cards */}
          <div className="grid gap-4 md:grid-cols-3">
            {hero.map((idx) => {
              const up = idx.change_pct >= 0
              return (
                <div key={idx.symbol} className="glass-card p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{idx.name}</p>
                      <p className="mt-2 text-2xl font-bold text-white">
                        {formatCurrency(idx.close, "INR").replace("₹", "")}
                      </p>
                    </div>
                    <div
                      className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold ${
                        up ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {Math.abs(idx.change).toFixed(2)}
                    </div>
                  </div>
                  <div className={`mt-3 text-sm font-medium ${getChangeColor(idx.change_pct)}`}>
                    {up ? <TrendingUp size={14} className="inline mr-1" /> : <TrendingDown size={14} className="inline mr-1" />}
                    {formatPercent(idx.change_pct)} today
                  </div>
                  <div className="mt-3 pt-3 border-t border-titan-800/30 flex justify-between text-xs text-gray-500">
                    <span>High <span className="text-gray-300">{formatCurrency(idx.high, "INR").replace("₹", "")}</span></span>
                    <span>Low <span className="text-gray-300">{formatCurrency(idx.low, "INR").replace("₹", "")}</span></span>
                    <span>Vol <span className="text-gray-300">{idx.volume.toLocaleString()}</span></span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* All indices table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">All Indices</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Index</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Open</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">High</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Low</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Close</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Change</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Change %</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {[...hero, ...others].map((idx) => (
                    <tr key={idx.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                      <td className="py-3 px-4">
                        <span className="text-white font-medium">{idx.name}</span>
                        <span className="ml-2 text-xs text-gray-600">{idx.symbol}</span>
                      </td>
                      <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(idx.open, "INR").replace("₹", "")}</td>
                      <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(idx.high, "INR").replace("₹", "")}</td>
                      <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(idx.low, "INR").replace("₹", "")}</td>
                      <td className="py-3 px-4 text-right text-white font-medium">{formatCurrency(idx.close, "INR").replace("₹", "")}</td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(idx.change)}`}>
                        {idx.change >= 0 ? "+" : ""}{idx.change.toFixed(2)}
                      </td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(idx.change_pct)}`}>
                        {formatPercent(idx.change_pct)}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-400">{idx.volume.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
