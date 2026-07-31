"use client"

import { Bell } from "lucide-react"
import type { DashboardAlert } from "@/types"
import { formatDate, formatTime } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError } from "./widget"

function severityDot(severity: string): string {
  const s = (severity || "info").toLowerCase()
  if (s === "critical") return "bg-red-500"
  if (s === "warning") return "bg-yellow-500"
  if (s === "positive") return "bg-emerald-500"
  return "bg-titan-500"
}

export function RecentAlertsWidget({
  data,
  loading,
  error,
  onRetry,
}: {
  data: DashboardAlert[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="Recent Alerts" icon={<Bell size={16} className="text-titan-400" />} className="lg:col-span-12">
      {loading ? (
        <WidgetLoading lines={4} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message="No alerts yet. Alerts will appear here when your watchlist conditions are triggered." />
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {data.map((alert) => (
            <div
              key={alert.id}
              className="flex items-start gap-3 rounded-lg bg-white/5 border border-white/5 p-3"
            >
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${severityDot(alert.severity)}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-white">{alert.symbol}</span>
                  <span className="badge-blue text-[10px]">{alert.event_type || "alert"}</span>
                  {!alert.is_read && <span className="w-1.5 h-1.5 rounded-full bg-titan-400 animate-pulse" />}
                </div>
                <p className="text-xs text-gray-400 mt-1">{alert.title}</p>
                {alert.message && <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{alert.message}</p>}
                {alert.triggered_at && (
                  <div className="text-[10px] text-gray-600 mt-1">
                    {formatDate(alert.triggered_at)} · {formatTime(alert.triggered_at)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  )
}
