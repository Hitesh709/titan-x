"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowUpRight, ArrowDownRight, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PaperAccountSummary, PaperPosition } from "@/types"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"

export default function PortfolioHoldingsPage() {
  const [account, setAccount] = useState<PaperAccountSummary | null>(null)
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)

  const ensureAccount = async () => {
    try {
      await api.get("/paper-trading/account")
    } catch {
      try {
        await api.post("/paper-trading/account?initial_capital=100000", {})
      } catch {
        /* account may already exist or creation failed; load() will surface errors */
      }
    }
  }

  const refreshPrices = async () => {
    try {
      await api.post("/paper-trading/portfolio/refresh", {})
    } catch {
      /* non-fatal: positions keep their last mark */
    }
  }

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      await ensureAccount()
      const [accRes, posRes] = await Promise.allSettled([
        api.get<PaperAccountSummary>("/paper-trading/account"),
        api.get<PaperPosition[]>("/paper-trading/portfolio"),
      ])
      if (!mounted.current) return
      if (accRes.status === "fulfilled") setAccount(accRes.value)
      if (posRes.status === "fulfilled") setPositions(posRes.value)
      if (accRes.status === "rejected" && posRes.status === "rejected") {
        setError(accRes.reason instanceof Error ? accRes.reason.message : "Failed to load portfolio")
      } else {
        setError(null)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load portfolio")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refreshPrices().finally(() => load(true))
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    refreshPrices().finally(() => load(true))
  }

  const totalValue = positions.reduce((s, p) => s + p.market_value, 0)
  const totalCost = positions.reduce((s, p) => s + p.cost_basis, 0)
  const totalPnl = totalValue - totalCost
  const totalPnlPct = totalCost ? (totalPnl / totalCost) * 100 : 0
  const sectors = new Set(positions.map((p) => p.sector).filter(Boolean))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-gray-500 text-sm">Current holdings and account summary</p>
          <span
            className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30"
            title="Simulated portfolio with virtual cash — no real broker, no real money"
          >
            Demo · Paper
          </span>
        </div>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} onRetry={handleRefresh} />
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid md:grid-cols-3 gap-4">
            <SummaryCard label="Portfolio Value" value={formatCurrency(account?.portfolio_value ?? totalValue)} />
            <SummaryCard label="Cost Basis" value={formatCurrency(totalCost)} sub={`${positions.length} positions across ${sectors.size} sectors`} />
            <SummaryCard
              label="Cash Balance"
              value={formatCurrency(account?.cash_balance ?? 0)}
              sub="Available for trading"
            />
          </div>

          {/* PnL strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <PnlStat label="Total PnL" value={account?.total_pnl ?? totalPnl} pct={account?.total_pnl_pct} />
            <PnlStat label="Realized" value={account?.total_realized_pnl ?? 0} />
            <PnlStat label="Unrealized" value={account?.total_unrealized_pnl ?? totalPnl} />
            <PnlStat label="Initial Capital" value={account?.initial_capital ?? 0} neutral />
          </div>

          {/* Holdings table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">Current Holdings</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Sector</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Qty</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Avg Price</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Current</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Market Value</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Unrealized PnL</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Realized PnL</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Allocation</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                      <td className="py-3 px-4">
                        <span className="text-white font-medium">{p.symbol}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="badge-blue text-[10px]">{p.sector ?? "—"}</span>
                      </td>
                      <td className="py-3 px-4 text-right text-gray-300">{p.quantity.toLocaleString()}</td>
                      <td className="py-3 px-4 text-right text-gray-400">{formatCurrency(p.average_price)}</td>
                      <td className="py-3 px-4 text-right text-gray-300">
                        {p.current_price !== null ? formatCurrency(p.current_price) : "—"}
                      </td>
                      <td className="py-3 px-4 text-right text-white font-medium">{formatCurrency(p.market_value)}</td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(p.unrealized_pnl)}`}>
                        <div className="flex items-center justify-end gap-1">
                          {p.unrealized_pnl >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                          {formatCurrency(p.unrealized_pnl)}
                          <span className="text-xs text-gray-500">({formatPercent(p.unrealized_pnl_pct)})</span>
                        </div>
                      </td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(p.realized_pnl)}`}>
                        {formatCurrency(p.realized_pnl)}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-400">{p.allocation_pct.toFixed(2)}%</td>
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

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass-card p-5">
      <p className="text-sm text-gray-400 mb-1">{label}</p>
      <h2 className="text-2xl font-bold text-white">{value}</h2>
      {sub && <p className="text-sm text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}

function PnlStat({ label, value, pct, neutral }: { label: string; value: number; pct?: number; neutral?: boolean }) {
  const cls = neutral ? "text-white" : getChangeColor(value)
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${cls}`}>{formatCurrency(value)}</p>
      {pct !== undefined && (
        <p className={`text-xs mt-0.5 ${getChangeColor(pct)}`}>{formatPercent(pct)}</p>
      )}
    </div>
  )
}
