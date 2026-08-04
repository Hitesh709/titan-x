"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { TrendingUp, TrendingDown, Minus, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { SectorRanking, SectorRotation } from "@/types"
import { formatPercent, getChangeColor, formatDate } from "@/lib/utils"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"

const PERIODS = ["1M", "3M", "6M", "YTD"] as const

export default function SectorsPage() {
  const [ranking, setRanking] = useState<SectorRanking[]>([])
  const [rotation, setRotation] = useState<SectorRotation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [rankRes, rotRes] = await Promise.allSettled([
        api.get<SectorRanking[]>("/sectors/ranking"),
        api.get<SectorRotation>("/sectors/rotation"),
      ])
      if (!mounted.current) return
      if (rankRes.status === "fulfilled") setRanking(rankRes.value)
      if (rotRes.status === "fulfilled") setRotation(rotRes.value)
      if (rankRes.status === "rejected" && rotRes.status === "rejected") {
        setError(
          rankRes.reason instanceof Error
            ? rankRes.reason.message
            : "Failed to load sector data"
        )
      } else {
        setError(null)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load sector data")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  const rotationColor = (rotation?.rotation_breadth ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-gray-500 text-sm">
          {rotation ? `As of ${formatDate(rotation.as_of_date)}` : "Sector performance"}
        </p>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} onRetry={handleRefresh} />
      ) : (
        <>
          {/* Rotation summary */}
          {rotation && (
            <div className="grid gap-4 md:grid-cols-3">
              <RotationCard title="Leading" sectors={rotation.leading} tone="up" />
              <RotationCard title="Neutral" sectors={rotation.neutral} tone="neutral" />
              <RotationCard title="Lagging" sectors={rotation.lagging} tone="down" />
            </div>
          )}

          {/* Ranking table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Sector Ranking</h3>
              <span className={`text-xs font-medium ${rotationColor}`}>
                Rotation breadth: {rotation?.rotation_breadth?.toFixed(2) ?? "—"}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Rank</th>
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Sector</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Momentum</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Rel. Strength</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">YTD</th>
                    {PERIODS.map((p) => (
                      <th key={p} className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">{p}</th>
                    ))}
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.map((s) => (
                    <tr key={s.sector} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                      <td className="py-3 px-4">
                        <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-white/5 text-xs font-semibold text-gray-300">
                          {s.rank ?? "—"}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-white font-medium">{s.sector}</span>
                        {s.constituent_count ? (
                          <span className="ml-2 text-xs text-gray-600">{s.constituent_count} stocks</span>
                        ) : null}
                      </td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(s.momentum_score ?? 0)}`}>
                        {s.momentum_score?.toFixed(1) ?? "—"}
                      </td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor((s.relative_strength ?? 50) - 50)}`}>
                        {s.relative_strength?.toFixed(1) ?? "—"}
                      </td>
                      <td className={`py-3 px-4 text-right font-medium ${getChangeColor(s.ytd_return ?? 0)}`}>
                        {s.ytd_return !== null && s.ytd_return !== undefined ? formatPercent(s.ytd_return) : "—"}
                      </td>
                      {PERIODS.map((p) => (
                        <td key={p} className={`py-3 px-4 text-right font-medium ${getChangeColor(s.periods?.[p] ?? 0)}`}>
                          {s.periods?.[p] !== null && s.periods?.[p] !== undefined ? formatPercent(s.periods[p]) : "—"}
                        </td>
                      ))}
                      <td className="py-3 px-4 text-right">
                        <SignalBadge signal={s.rotation_signal} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function RotationCard({
  title,
  sectors,
  tone,
}: {
  title: string
  sectors: Array<Record<string, unknown>>
  tone: "up" | "neutral" | "down"
}) {
  const toneIcon =
    tone === "up" ? <TrendingUp size={14} className="text-emerald-400" /> :
    tone === "down" ? <TrendingDown size={14} className="text-red-400" /> :
    <Minus size={14} className="text-gray-400" />
  const toneBorder =
    tone === "up" ? "border-emerald-500/20" :
    tone === "down" ? "border-red-500/20" : "border-white/10"

  return (
    <div className={`glass-card p-5 border-t-2 ${toneBorder}`}>
      <div className="flex items-center gap-2 mb-3">
        {toneIcon}
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <span className="ml-auto text-xs text-gray-500">{sectors.length}</span>
      </div>
      {sectors.length === 0 ? (
        <p className="text-xs text-gray-600">No sectors</p>
      ) : (
        <ul className="space-y-1.5">
          {sectors.slice(0, 6).map((s, i) => {
            const name = String(s["sector"] ?? `Sector ${i + 1}`)
            const pct = (s["momentum_score"] as number | undefined)
            return (
              <li key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{name}</span>
                <span className={`font-medium ${pct === undefined ? "text-gray-600" : getChangeColor(pct)}`}>
                  {pct === undefined ? "—" : pct.toFixed(1)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-xs text-gray-600">—</span>
  const lower = signal.toLowerCase()
  const cls =
    lower.includes("leading") || lower.includes("strong") || lower.includes("buy")
      ? "badge-green"
      : lower.includes("lagging") || lower.includes("weak") || lower.includes("sell")
        ? "badge-red"
        : "badge-blue"
  return <span className={`${cls} text-[10px]`}>{signal}</span>
}
