"use client"

import { Wallet } from "lucide-react"
import type { PortfolioSummary as PortfolioSummaryType } from "@/types"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetCard, WidgetLoading, WidgetEmpty, WidgetError, ChangePill } from "./widget"

export function PortfolioSummaryWidget({
  data,
  loading,
  error,
  onRetry,
}: {
  data: PortfolioSummaryType
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <WidgetCard title="Portfolio Summary" icon={<Wallet size={16} className="text-titan-400" />} className="lg:col-span-5">
      {loading ? (
        <WidgetLoading lines={5} />
      ) : error ? (
        <WidgetError message={error} onRetry={onRetry} />
      ) : !data?.has_account ? (
        <WidgetEmpty message="No paper account yet. Open a paper account to start tracking your portfolio." />
      ) : (
        <div className="space-y-4">
          <div>
            <p className="text-xs text-gray-500">Total Equity</p>
            <p className="text-2xl font-bold text-white">{formatCurrency(data.total_equity || 0)}</p>
            <div className="flex items-center gap-3 mt-1 text-sm">
              <span className={`font-medium ${getChangeColor(data.total_return_pct || 0)}`}>
                {formatPercent(data.total_return_pct || 0)}
              </span>
              <span className="text-xs text-gray-600">total return</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Stat label="Cash" value={formatCurrency(data.cash_balance || 0)} />
            <Stat label="Positions" value={formatCurrency(data.positions_value || 0)} />
            <Stat label="Unrealized P&L" value={formatCurrency(data.unrealized_pnl || 0)} valueClass={getChangeColor(data.unrealized_pnl || 0)} />
          </div>

          {(data.positions?.length || 0) > 0 && (
            <div>
              <div className="text-xs text-gray-500 mb-2">
                {data.positions_count} open position{(data.positions_count || 0) === 1 ? "" : "s"}
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {data.positions?.map((p) => (
                  <div key={p.symbol} className="flex items-center justify-between text-sm py-1.5 border-b border-titan-800/20 last:border-0">
                    <div>
                      <span className="text-white font-medium">{p.symbol}</span>
                      <span className="text-gray-500 text-xs ml-2">
                        {p.quantity} sh @ {p.current_price !== null && p.current_price !== undefined ? formatCurrency(p.current_price) : "—"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-300">{formatCurrency(p.market_value)}</span>
                      <ChangePill value={p.current_price && p.avg_price ? ((p.current_price - p.avg_price) / p.avg_price) * 100 : null} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </WidgetCard>
  )
}

function Stat({ label, value, valueClass = "text-white" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/5 p-3">
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">{label}</div>
      <div className={`text-sm font-bold ${valueClass}`}>{value}</div>
    </div>
  )
}
