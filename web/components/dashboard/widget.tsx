import type { ReactNode } from "react"
import { RefreshCw, WifiOff } from "lucide-react"

export function WidgetCard({
  title,
  icon,
  action,
  children,
  className = "",
}: {
  title: string
  icon?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`glass-card p-5 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          {icon}
          {title}
        </h3>
        {action}
      </div>
      {children}
    </div>
  )
}

export function WidgetLoading({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-10 rounded-lg bg-white/5" />
      ))}
    </div>
  )
}

export function WidgetEmpty({ message }: { message: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  )
}

export function WidgetError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="py-8 text-center space-y-3">
      <WifiOff size={24} className="mx-auto text-gray-600" />
      <p className="text-sm text-gray-400">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 text-xs text-titan-400 hover:text-titan-300"
        >
          <RefreshCw size={12} /> Retry
        </button>
      )}
    </div>
  )
}

export function RefreshButton({ onClick, spinning }: { onClick: () => void; spinning: boolean }) {
  return (
    <button
      onClick={onClick}
      className="text-gray-500 hover:text-gray-200 transition-colors"
      title="Refresh"
    >
      <RefreshCw size={14} className={spinning ? "animate-spin" : ""} />
    </button>
  )
}

export function ChangePill({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-xs text-gray-500">—</span>
  }
  const up = value > 0
  const cls = up ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {up ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  )
}

export function signalBadge(signal: string): string {
  const s = signal.toLowerCase()
  if (s.includes("buy")) return "badge-green"
  if (s.includes("sell")) return "badge-red"
  return "badge-blue"
}

export function sentimentClass(sentiment: string | null | undefined): string {
  const s = (sentiment || "neutral").toLowerCase()
  if (s.includes("posit") || s === "bullish") return "badge-green"
  if (s.includes("negat") || s === "bearish") return "badge-red"
  return "badge-blue"
}
