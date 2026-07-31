"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Brain, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import type { AiPick } from "@/types"
import { formatPercent } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError, signalBadge } from "./widget"

const REFRESH_INTERVAL_MS = 30_000

export function AiRecommendations() {
  const [picks, setPicks] = useState<AiPick[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    try {
      const res = await api.get<AiPick[]>("/dashboard/ai-picks")
      if (!mounted.current) return
      setPicks(res)
      setError(null)
      setLastUpdated(new Date())
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load AI picks")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    load()
    const timer = setInterval(() => load(true), REFRESH_INTERVAL_MS)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [load])

  return (
    <WidgetCard
      title="Top Picks"
      icon={<Brain size={16} className="text-titan-400" />}
      className="lg:col-span-12"
      action={
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-gray-500">
            <span
              className={`w-1.5 h-1.5 rounded-full ${refreshing ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`}
            />
            Auto-refresh {REFRESH_INTERVAL_MS / 1000}s
          </span>
          {lastUpdated && (
            <span className="text-[11px] text-gray-600">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => load(true)}
            className="text-gray-500 hover:text-gray-200 transition-colors"
            title="Refresh now"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>
      }
    >
      {loading ? (
        <WidgetLoading lines={4} />
      ) : error ? (
        <WidgetError message={error} onRetry={() => load()} />
      ) : !picks || picks.length === 0 ? (
        <WidgetEmpty message="No AI picks yet. Add symbols to your watchlist to see top picks." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30">
                <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">AI Score</th>
                <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Confidence</th>
                <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Expected Return</th>
                <th className="text-center py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Risk</th>
                <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Holding Period</th>
                <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Evidence</th>
                <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Why Buy</th>
                <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase tracking-wider">Why Not Buy</th>
              </tr>
            </thead>
            <tbody>
              {picks.map((pick) => (
                <tr key={pick.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors align-top">
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <span className="w-8 h-8 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">
                        {pick.symbol.slice(0, 4)}
                      </span>
                      <div>
                        <div className="text-white font-semibold">{pick.symbol}</div>
                        <span className={`badge ${signalBadge(pick.combined_signal)}`}>{pick.combined_signal}</span>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <span className="text-base font-bold text-titan-400">{pick.combined_score.toFixed(1)}</span>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 min-w-[70px] h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${pick.combined_confidence >= 0.5 ? "bg-emerald-500" : "bg-yellow-500"}`}
                          style={{ width: `${Math.min(100, Math.round(pick.combined_confidence * 100))}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400 whitespace-nowrap">
                        {Math.round(pick.combined_confidence * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right text-emerald-400 font-medium">
                    {pick.expected_return_pct !== null && pick.expected_return_pct !== undefined
                      ? formatPercent(pick.expected_return_pct)
                      : "—"}
                  </td>
                  <td className="py-3 px-3 text-center">
                    <RiskBadge risk={pick.risk} />
                  </td>
                  <td className="py-3 px-3 text-right text-gray-300">
                    {pick.holding_period_days !== null && pick.holding_period_days !== undefined
                      ? `${pick.holding_period_days}d`
                      : "—"}
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex flex-wrap gap-1">
                      {(pick.evidence ?? []).map((e) => (
                        <span key={e} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-400">
                          {e}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <ul className="space-y-1 text-xs text-emerald-400/90 list-disc list-inside">
                      {(pick.why_buy ?? []).slice(0, 3).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </td>
                  <td className="py-3 px-3">
                    <ul className="space-y-1 text-xs text-red-400/80 list-disc list-inside">
                      {(pick.why_not_buy ?? []).slice(0, 3).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </WidgetCard>
  )
}

function RiskBadge({ risk }: { risk?: string | null }) {
  const cls =
    risk === "High"
      ? "bg-red-500/10 text-red-400"
      : risk === "Medium"
        ? "bg-amber-500/10 text-amber-400"
        : "bg-emerald-500/10 text-emerald-400"
  return <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{risk ?? "—"}</span>
}
