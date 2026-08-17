"use client"

import { memo } from "react"
import Link from "next/link"
import { Clock } from "lucide-react"
import type { StockRecommendation } from "@/types"
import { formatPercent } from "@/lib/utils"

interface ParsedMeta {
  signal?: string
  as_of_date?: string
  evidence?: string[]
  caution?: string[]
  returns?: Record<string, number | null>
}

function parseMeta(rec: StockRecommendation): ParsedMeta {
  if (!rec.metadata_json) return {}
  try {
    return JSON.parse(rec.metadata_json) as ParsedMeta
  } catch {
    return {}
  }
}

export function StatCard({
  label,
  value,
  tone,
  icon,
}: {
  label: string
  value: number
  tone: string
  icon: React.ReactNode
}) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 text-gray-500">
        <span className={tone}>{icon}</span>
        <span className="text-xs">{label}</span>
      </div>
      <div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div>
    </div>
  )
}

export function RiskBadge({ risk }: { risk?: string | null }) {
  const cls =
    risk === "High"
      ? "bg-red-500/10 text-red-400"
      : risk === "Medium"
        ? "bg-amber-500/10 text-amber-400"
        : "bg-emerald-500/10 text-emerald-400"
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{risk ?? "—"}</span>
  )
}

function RecommendationCardBase({ rec }: { rec: StockRecommendation }) {
  const meta = parseMeta(rec)
  const dirCls =
    rec.direction === "BUY" ? "badge-green" : rec.direction === "SELL" ? "badge-red" : "badge-blue"

  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between gap-3">
        <Link href={`/dashboard/stocks/${rec.symbol}`} className="flex items-center gap-3 group">
          <span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs">
            {rec.symbol.slice(0, 4)}
          </span>
          <div>
            <div className="text-white font-semibold group-hover:text-titan-400 transition-colors">{rec.symbol}</div>
            <div className="text-[11px] text-gray-500">₹{rec.current_price?.toLocaleString("en-IN") ?? "—"}</div>
          </div>
        </Link>
        <span className={`badge ${dirCls}`}>
          {rec.direction}
          {rec.signal ? ` · ${rec.signal.replaceAll("_", " ")}` : ""}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 mt-4">
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Confidence</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className={`h-full rounded-full ${rec.confidence! >= 50 ? "bg-emerald-500" : "bg-yellow-500"}`}
                style={{ width: `${Math.min(100, rec.confidence ?? 0)}%` }}
              />
            </div>
            <span className="text-xs text-gray-300">{Math.round(rec.confidence ?? 0)}%</span>
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Expected return</div>
          <div
            className={`text-sm font-semibold ${
              (rec.predicted_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {rec.predicted_return_pct !== null && rec.predicted_return_pct !== undefined
              ? formatPercent(rec.predicted_return_pct)
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Holding</div>
          <div className="text-sm text-gray-300">{rec.timeframe ?? "—"}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3">
        <RiskBadge risk={rec.risk_level} />
        {rec.price_target ? (
          <span className="text-[11px] text-gray-500">Target ₹{rec.price_target.toLocaleString("en-IN")}</span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-gray-500">
          <Clock size={12} />
          {rec.generated_at ? new Date(rec.generated_at).toLocaleTimeString() : "—"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-titan-800/20">
        <div>
          <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">
            Supporting evidence
          </div>
          <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
            {(meta.evidence ?? []).slice(0, 3).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] font-semibold text-red-400/90 uppercase tracking-wider mb-1.5">
            Reasons for caution
          </div>
          <ul className="space-y-1 text-xs text-gray-400 list-disc list-inside">
            {(meta.caution ?? []).slice(0, 3).map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export const RecommendationCard = memo(RecommendationCardBase)
