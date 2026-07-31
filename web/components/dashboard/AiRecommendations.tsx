"use client"

import { Brain } from "lucide-react"
import type { AiPick } from "@/types"
import { formatDate } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError, signalBadge, signalColor } from "./widget"

export function AiRecommendations({
  data,
  loading,
  error,
  onRetry,
}: {
  data: AiPick[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="AI Recommendations" icon={<Brain size={16} className="text-titan-400" />} className="lg:col-span-7">
      {loading ? (
        <WidgetLoading lines={4} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message="No AI recommendations yet. Add symbols to your watchlist to see AI picks." />
      ) : (
        <div className="space-y-3">
          {data.map((pick) => (
            <div key={pick.symbol} className="flex items-center gap-4 py-2 border-b border-titan-800/20 last:border-0">
              <div className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">
                {pick.symbol.slice(0, 4)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{pick.symbol}</span>
                  <span className={`badge ${signalBadge(pick.combined_signal)}`}>{pick.combined_signal}</span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${pick.combined_confidence >= 0.5 ? "bg-emerald-500" : "bg-yellow-500"}`}
                      style={{ width: `${Math.min(100, Math.round(pick.combined_confidence * 100))}%` }}
                    />
                  </div>
                  <span className="text-[11px] text-gray-500">{Math.round(pick.combined_confidence * 100)}% conf</span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className={`text-sm font-bold ${signalColor(pick.combined_signal)}`}>{pick.combined_score?.toFixed(1)}</div>
                <div className="text-[11px] text-gray-600">score</div>
              </div>
            </div>
          ))}
          {data[0]?.as_of_date && (
            <div className="text-[11px] text-gray-600">As of {formatDate(data[0].as_of_date)}</div>
          )}
        </div>
      )}
    </WidgetCard>
  )
}
