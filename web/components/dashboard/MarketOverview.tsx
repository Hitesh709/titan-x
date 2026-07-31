"use client"

import { Globe } from "lucide-react"
import type { MarketHeatmapData } from "@/types"
import { formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError } from "./widget"

export function MarketOverview({
  heatmap,
  loading,
  error,
  onRetry,
}: {
  heatmap: MarketHeatmapData | null
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="Market Overview" icon={<Globe size={16} className="text-titan-400" />} className="lg:col-span-12">
      {loading ? (
        <WidgetLoading lines={2} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !heatmap ? (
        <WidgetEmpty message="No market overview data available" />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <OverviewStat
            label="Avg Sector Return"
            value={heatmap.summary.avg_sector_return_pct === null || heatmap.summary.avg_sector_return_pct === undefined ? "—" : formatPercent(heatmap.summary.avg_sector_return_pct)}
            className={getChangeColor(heatmap.summary.avg_sector_return_pct || 0)}
          />
          <OverviewStat
            label="Advancing Sectors"
            value={`${heatmap.summary.advancing_sectors ?? 0} / ${heatmap.summary.total_sectors ?? 0}`}
            className="text-emerald-400"
          />
          <OverviewStat
            label="Declining Sectors"
            value={`${heatmap.summary.declining_sectors ?? 0} / ${heatmap.summary.total_sectors ?? 0}`}
            className="text-red-400"
          />
          <OverviewStat
            label="Breadth Oscillator"
            value={heatmap.summary.market_breadth === null || heatmap.summary.market_breadth === undefined ? "—" : heatmap.summary.market_breadth.toFixed(2)}
            className={getChangeColor(heatmap.summary.market_breadth || 0)}
          />
          <OverviewStat
            label="Index Strength"
            value={heatmap.summary.index_strength === null || heatmap.summary.index_strength === undefined ? "—" : heatmap.summary.index_strength.toFixed(2)}
            className={getChangeColor(heatmap.summary.index_strength || 0)}
          />
          <OverviewStat
            label="Adv / Decl"
            value={heatmap.breadth.advance_decline_ratio === null || heatmap.breadth.advance_decline_ratio === undefined ? "—" : heatmap.breadth.advance_decline_ratio.toFixed(2)}
            className={getChangeColor((heatmap.breadth.advance_decline_ratio || 0) - 1)}
          />
        </div>
      )}
    </WidgetCard>
  )
}

function OverviewStat({ label, value, className }: { label: string; value: string; className: string }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/5 p-3">
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${className}`}>{value}</div>
    </div>
  )
}
