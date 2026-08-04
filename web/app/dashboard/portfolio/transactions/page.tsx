"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowUpRight, ArrowDownRight } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PaginatedResponse, PaperTradeRow } from "@/types"
import { formatCurrency, formatDate, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

const PAGE_SIZE = 50

export default function PortfolioTransactionsPage() {
  const [trades, setTrades] = useState<PaperTradeRow[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async (nextSkip = 0) => {
    setLoading(true)
    try {
      const res = await api.get<PaginatedResponse<PaperTradeRow>>(
        `/paper-trading/trades?skip=${nextSkip}&limit=${PAGE_SIZE}`
      )
      if (!mounted.current) return
      setTrades(res.items)
      setTotal(res.total)
      setSkip(res.skip)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load trade history")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(skip), [load, skip])

  const hasPrev = skip > 0
  const hasNext = skip + trades.length < total

  return (
    <div className="space-y-6">
      {loading && skip === 0 ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : (
        <div className="glass-card overflow-hidden">
          <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Trade History</h3>
            <span className="text-xs text-gray-500">{total} total trades</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-titan-800/30">
                  <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Time</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Side</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Qty</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Price</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Commission</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Realized PnL</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                    <td className="py-3 px-4 text-gray-400">{t.trade_time ? formatDate(t.trade_time) : "—"}</td>
                    <td className="py-3 px-4">
                      <span className="text-white font-medium">{t.symbol}</span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md ${
                          t.side === "buy"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "bg-red-500/10 text-red-400"
                        }`}
                      >
                        {t.side === "buy" ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                        {t.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-gray-300">{t.quantity.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right text-gray-300">{formatCurrency(t.price)}</td>
                    <td className="py-3 px-4 text-right text-gray-500">{formatCurrency(t.commission)}</td>
                    <td className={`py-3 px-4 text-right font-medium ${getChangeColor(t.realized_pnl ?? 0)}`}>
                      {t.realized_pnl !== null ? formatCurrency(t.realized_pnl) : "—"}
                    </td>
                  </tr>
                ))}
                {trades.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-gray-500 text-sm">
                      No trades yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {(hasPrev || hasNext) && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-titan-800/30">
              <button
                disabled={!hasPrev}
                onClick={() => load(Math.max(0, skip - PAGE_SIZE))}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-white/5 text-gray-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="text-xs text-gray-500">
                {total ? skip + 1 : 0}–{Math.min(skip + trades.length, total)} of {total}
              </span>
              <button
                disabled={!hasNext}
                onClick={() => load(skip + PAGE_SIZE)}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-white/5 text-gray-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
