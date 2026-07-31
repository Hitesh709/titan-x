"use client"

import { Grid3X3 } from "lucide-react"
import type { SectorData } from "@/types"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError } from "./widget"

function heatColor(returnPct: number | null | undefined): string {
  if (returnPct === null || returnPct === undefined || Number.isNaN(returnPct)) {
    return "bg-white/5"
  }
  const pct = Math.max(-8, Math.min(8, returnPct))
  const intensity = Math.round((Math.abs(pct) / 8) * 60)
  if (pct >= 0) {
    return `rgba(16, 185, 129, ${(0.15 + intensity / 100).toFixed(2)})`
  }
  return `rgba(239, 68, 68, ${(0.15 + intensity / 100).toFixed(2)})`
}

export function SectorHeatmap({
  data,
  loading,
  error,
  onRetry,
}: {
  data: SectorData[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  const totalConstituents = data.reduce((sum, s) => sum + (s.constituent_count || 0), 0) || data.length || 1

  return (
    <WidgetCard
      title="Sector Heatmap"
      icon={<Grid3X3 size={16} className="text-titan-400" />}
      className="lg:col-span-12"
    >
      {loading ? (
        <WidgetLoading lines={3} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message="No sector data available." />
      ) : (
        <div className="flex flex-wrap gap-2">
          {data.map((sector) => {
            const weight = Math.max(15, Math.round(((sector.constituent_count || 1) / totalConstituents) * 100))
            return (
              <div
                key={sector.name}
                className="rounded-lg p-3 border border-white/10 min-w-[140px] flex-1 flex flex-col justify-between"
                style={{
                  flexGrow: weight,
                  flexBasis: `${Math.min(240, Math.max(130, weight))}px`,
                  backgroundColor: heatColor(sector.return_pct),
                }}
                title={`${sector.name}: ${sector.return_pct?.toFixed(2) ?? "—"}% over period`}
              >
                <div className="text-xs font-semibold text-white">{sector.name}</div>
                <div className="mt-2">
                  <div className="text-lg font-bold text-white">
                    {sector.return_pct === null || sector.return_pct === undefined ? "—" : `${sector.return_pct >= 0 ? "+" : ""}${sector.return_pct.toFixed(2)}%`}
                  </div>
                  <div className="text-[10px] text-white/60">{sector.constituent_count} stocks</div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </WidgetCard>
  )
}
