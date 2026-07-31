"use client"

import { Newspaper, ExternalLink } from "lucide-react"
import type { NewsRow } from "./types"
import { formatDate, formatTime } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError, sentimentClass } from "./widget"

export function MarketNewsWidget({
  data,
  loading,
  error,
  onRetry,
}: {
  data: NewsRow[]
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="Market News" icon={<Newspaper size={16} className="text-titan-400" />} className="lg:col-span-8">
      {loading ? (
        <WidgetLoading lines={5} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data || data.length === 0 ? (
        <WidgetEmpty message="No news available right now." />
      ) : (
        <div className="space-y-3">
          {data.map((n) => (
            <div key={n.id} className="flex items-start gap-3 py-2 border-b border-titan-800/20 last:border-0">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {n.symbol && <span className="badge-blue text-[10px]">{n.symbol}</span>}
                  {n.sentiment && <span className={`badge ${sentimentClass(n.sentiment)} text-[10px]`}>{n.sentiment}</span>}
                </div>
                {n.url ? (
                  <a href={n.url} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-200 hover:text-titan-400 transition-colors mt-1 block">
                    {n.title}
                  </a>
                ) : (
                  <p className="text-sm text-gray-200 mt-1">{n.title}</p>
                )}
                <div className="text-[11px] text-gray-600 mt-1 flex items-center gap-2">
                  <span>{n.source}</span>
                  {n.published_at && (
                    <span>
                      {formatDate(n.published_at)} · {formatTime(n.published_at)}
                    </span>
                  )}
                  {n.url && (
                    <span className="inline-flex items-center gap-0.5 text-titan-500">
                      <ExternalLink size={10} />
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  )
}
