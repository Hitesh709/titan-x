"use client"

import { TrendingUp, TrendingDown } from "lucide-react"
import type { HeatmapMover } from "@/types"
import { formatCurrency } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError, ChangePill } from "./widget"

export function TopMoversWidget({
  title,
  type,
  data,
  loading,
  error,
  onRetry,
}: {
  title: string
  type: "gainers" | "losers"
  data: HeatmapMover[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  const icon =
    type === "gainers" ? (
      <TrendingUp size={16} className="text-emerald-400" />
    ) : (
      <TrendingDown size={16} className="text-red-400" />
    )
  return (
    <WidgetCard title={title} icon={icon} className="lg:col-span-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message={`No ${title.toLowerCase()} data available.`} />
      ) : (
        <div className="space-y-1">
          {data.map((m) => (
            <div key={m.symbol} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-white">{m.symbol}</span>
                <span className="text-xs text-gray-600">
                  {m.close !== null && m.close !== undefined ? formatCurrency(m.close) : "—"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[11px] text-gray-600">
                  {m.volume >= 1000 ? `${(m.volume / 1000).toFixed(0)}K` : m.volume} vol
                </span>
                <ChangePill value={m.return_pct} />
              </div>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  )
}
