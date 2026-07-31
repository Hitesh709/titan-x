"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/lib/api"
import type { PaperAnalytics } from "@/types"
import { formatCurrency, formatPercent } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

export default function PortfolioAnalyticsPage() {
  const [analytics, setAnalytics] = useState<PaperAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await api.get<PaperAnalytics>("/paper-trading/analytics")
      if (!mounted.current) return
      setAnalytics(res)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load analytics")
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

  return (
    <div className="space-y-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : analytics ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <AnalyticCard label="Win Rate" value={formatPercent(analytics.win_rate)} />
            <AnalyticCard label="Profit Factor" value={formatNumber(analytics.profit_factor)} />
            <AnalyticCard label="Expectancy" value={formatNumber(analytics.expectancy)} />
            <AnalyticCard label="CAGR" value={formatPercent(analytics.cagr ?? 0)} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <AnalyticCard label="Sharpe Ratio" value={formatNumber(analytics.sharpe_ratio)} />
            <AnalyticCard label="Sortino Ratio" value={formatNumber(analytics.sortino_ratio)} />
            <AnalyticCard label="Max Drawdown" value={formatPercent(analytics.max_drawdown ?? 0)} tone="negative" />
            <AnalyticCard label="Max Drawdown Amount" value={formatCurrency(analytics.max_drawdown_amount ?? 0)} tone="negative" />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <AnalyticCard label="Total Trades" value={analytics.total_trades.toString()} />
            <AnalyticCard label="Winning Trades" value={analytics.winning_trades.toString()} />
            <AnalyticCard label="Losing Trades" value={analytics.losing_trades.toString()} />
          </div>

          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Risk & Return Profile</h3>
            <div className="flex items-center gap-4">
              <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, Math.max(5, analytics.win_rate))}%`,
                    background: analytics.win_rate >= 50 ? "#34d399" : "#f87171",
                  }}
                />
              </div>
              <span className="text-sm text-gray-400 whitespace-nowrap">Win rate</span>
            </div>
            <div className="flex items-center gap-4 mt-3">
              <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, Math.max(5, (analytics.profit_factor ?? 0) * 20))}%`,
                    background: (analytics.profit_factor ?? 0) >= 1 ? "#34d399" : "#f87171",
                  }}
                />
              </div>
              <span className="text-sm text-gray-400 whitespace-nowrap">Profit factor</span>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}

function formatNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return v.toFixed(2)
}

function AnalyticCard({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" }) {
  const cls =
    tone === "positive" ? "text-emerald-400" : tone === "negative" ? "text-red-400" : "text-white"
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${cls}`}>{value}</p>
    </div>
  )
}
