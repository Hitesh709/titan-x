"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TrendingUp, TrendingDown } from "lucide-react"
import api from "@/lib/api"
import type { PaperPosition } from "@/types"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

export default function PortfolioPnlPage() {
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await api.get<PaperPosition[]>("/paper-trading/portfolio")
      if (!mounted.current) return
      setPositions(res)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load PnL")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    load()
    return () => {
      mounted.current = false
    }
  }, [load])

  const totalUnrealized = positions.reduce((s, p) => s + p.unrealized_pnl, 0)
  const totalRealized = positions.reduce((s, p) => s + p.realized_pnl, 0)
  const totalPnl = totalUnrealized + totalRealized
  const winners = positions.filter((p) => p.unrealized_pnl > 0)
  const losers = positions.filter((p) => p.unrealized_pnl < 0)
  const winnerValue = winners.reduce((s, p) => s + p.unrealized_pnl, 0)
  const loserValue = losers.reduce((s, p) => s + p.unrealized_pnl, 0)
  const totalCost = positions.reduce((s, p) => s + p.cost_basis, 0)
  const pnlPct = totalCost ? (totalPnl / totalCost) * 100 : 0

  return (
    <div className="space-y-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <PnlCard label="Total PnL" value={totalPnl} pct={pnlPct} />
            <PnlCard label="Unrealized PnL" value={totalUnrealized} />
            <PnlCard label="Realized PnL" value={totalRealized} />
            <div className="glass-card p-4">
              <p className="text-xs text-gray-500">Winners / Losers</p>
              <p className="mt-1 text-lg font-bold text-white">
                {winners.length} / {losers.length}
              </p>
              <div className="mt-1 flex items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-1 text-emerald-400">
                  <TrendingUp size={12} /> {formatCurrency(winnerValue)}
                </span>
                <span className="inline-flex items-center gap-1 text-red-400">
                  <TrendingDown size={12} /> {formatCurrency(loserValue)}
                </span>
              </div>
            </div>
          </div>

          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">Position PnL</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Cost Basis</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Market Value</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Unrealized PnL</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Unrealized %</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Realized PnL</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Total PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {positions
                    .slice()
                    .sort((a, b) => b.unrealized_pnl + b.realized_pnl - (a.unrealized_pnl + a.realized_pnl))
                    .map((p) => {
                      const total = p.unrealized_pnl + p.realized_pnl
                      return (
                        <tr key={p.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                          <td className="py-3 px-4">
                            <span className="text-white font-medium">{p.symbol}</span>
                            <span className="ml-2 text-xs text-gray-600">{p.sector ?? ""}</span>
                          </td>
                          <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(p.cost_basis)}</td>
                          <td className="py-3 px-4 text-right text-gray-300">{formatCurrency(p.market_value)}</td>
                          <td className={`py-3 px-4 text-right font-medium ${getChangeColor(p.unrealized_pnl)}`}>
                            {formatCurrency(p.unrealized_pnl)}
                          </td>
                          <td className={`py-3 px-4 text-right font-medium ${getChangeColor(p.unrealized_pnl_pct)}`}>
                            {formatPercent(p.unrealized_pnl_pct)}
                          </td>
                          <td className={`py-3 px-4 text-right font-medium ${getChangeColor(p.realized_pnl)}`}>
                            {formatCurrency(p.realized_pnl)}
                          </td>
                          <td className={`py-3 px-4 text-right font-medium ${getChangeColor(total)}`}>
                            {formatCurrency(total)}
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function PnlCard({ label, value, pct }: { label: string; value: number; pct?: number }) {
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${getChangeColor(value)}`}>{formatCurrency(value)}</p>
      {pct !== undefined && <p className={`text-xs mt-0.5 ${getChangeColor(pct)}`}>{formatPercent(pct)}</p>}
    </div>
  )
}
