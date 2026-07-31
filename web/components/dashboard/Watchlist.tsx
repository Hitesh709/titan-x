"use client"

import { Star } from "lucide-react"
import type { WatchlistSummary } from "@/types"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError } from "./widget"

export function WatchlistWidget({
  data,
  loading,
  error,
  onRetry,
}: {
  data: WatchlistSummary[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="Watchlist" icon={<Star size={16} className="text-titan-400" />} className="lg:col-span-4">
      {loading ? (
        <WidgetLoading lines={4} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message="No watchlists yet. Create a watchlist to track your favorite symbols." />
      ) : (
        <div className="space-y-3">
          {data.map((wl) => (
            <div key={wl.id} className="rounded-lg bg-white/5 border border-white/5 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-white">{wl.name}</span>
                <span className="badge-blue text-[10px]">{wl.item_count} symbols</span>
              </div>
              {wl.description && <p className="text-xs text-gray-500 mb-2">{wl.description}</p>}
              {wl.symbols.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {wl.symbols.map((s) => (
                    <span key={s} className="px-2 py-0.5 rounded bg-titan-600/15 border border-titan-600/20 text-titan-300 text-[11px] font-medium">
                      {s}
                    </span>
                  ))}
                  {wl.item_count > wl.symbols.length && (
                    <span className="text-[11px] text-gray-600 self-center">+{wl.item_count - wl.symbols.length} more</span>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-600">No symbols added</p>
              )}
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  )
}
