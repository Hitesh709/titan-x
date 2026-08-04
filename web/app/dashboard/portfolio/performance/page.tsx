"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PerformanceReport } from "@/types"
import { formatCurrency, formatPercent } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

export default function PortfolioPerformancePage() {
  const [report, setReport] = useState<PerformanceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await api.get<PerformanceReport>("/paper-trading/reports/performance")
      if (!mounted.current) return
      setReport(res)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load performance report")
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

  useLiveRefresh(() => void load(), [load])

  return (
    <div className="space-y-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : report ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Total Trades" value={report.total_trades.toString()} />
            <MetricCard label="Filled Orders" value={report.filled_orders.toString()} />
            <MetricCard label="Cancelled Orders" value={report.cancelled_orders.toString()} />
            <MetricCard label="Win Rate" value={formatPercent(report.win_rate)} />
          </div>

          {report.account && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Portfolio Value" value={formatCurrency(report.account.portfolio_value)} />
              <MetricCard
                label="Total PnL"
                value={formatCurrency(report.account.total_pnl)}
                tone={report.account.total_pnl >= 0 ? "positive" : "negative"}
              />
              <MetricCard
                label="Total Return"
                value={formatPercent(report.account.total_pnl_pct)}
                tone={report.account.total_pnl_pct >= 0 ? "positive" : "negative"}
              />
              <MetricCard label="Cash Balance" value={formatCurrency(report.account.cash_balance)} />
            </div>
          )}

          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Wins vs Losses</h3>
            <div className="flex items-center gap-4">
              <div className="flex-1 h-3 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${report.win_rate}%`,
                    background: report.win_rate >= 50 ? "#34d399" : "#f87171",
                  }}
                />
              </div>
              <span className="text-sm text-white font-medium whitespace-nowrap">
                {report.winning_trades}W / {report.losing_trades}L
              </span>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" }) {
  const cls =
    tone === "positive" ? "text-emerald-400" : tone === "negative" ? "text-red-400" : "text-white"
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${cls}`}>{value}</p>
    </div>
  )
}
