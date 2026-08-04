"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts"
import { TrendingUp, TrendingDown, Minus, Activity, Shield, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { BreadthSummary, ADLinePoint, OscillatorPoint, HighLowPoint, VolumeBreadthPoint } from "@/types"
import { getChangeColor, formatDate } from "@/lib/utils"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"

export default function BreadthPage() {
  const [summary, setSummary] = useState<BreadthSummary | null>(null)
  const [adLine, setAdLine] = useState<ADLinePoint[]>([])
  const [oscillator, setOscillator] = useState<OscillatorPoint[]>([])
  const [highLow, setHighLow] = useState<HighLowPoint[]>([])
  const [volumeBreadth, setVolumeBreadth] = useState<VolumeBreadthPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [sum, ad, osc, hl, vb] = await Promise.allSettled([
        api.get<BreadthSummary>("/market-breadth/summary"),
        api.get<ADLinePoint[]>("/market-breadth/advance-decline/line?limit=120"),
        api.get<OscillatorPoint[]>("/market-breadth/oscillator/history?limit=120"),
        api.get<HighLowPoint[]>("/market-breadth/high-low/history?limit=120"),
        api.get<VolumeBreadthPoint[]>("/market-breadth/volume-breadth/history?limit=120"),
      ])
      if (!mounted.current) return
      if (sum.status === "fulfilled") setSummary(sum.value)
      if (ad.status === "fulfilled") setAdLine(ad.value.slice().reverse())
      if (osc.status === "fulfilled") setOscillator(osc.value.slice().reverse())
      if (hl.status === "fulfilled") setHighLow(hl.value.slice().reverse())
      if (vb.status === "fulfilled") setVolumeBreadth(vb.value.slice().reverse())
      const failures = [sum, ad, osc, hl, vb].filter((r) => r.status === "rejected")
      if (failures.length === 5) {
        const first = failures[0] as PromiseRejectedResult
        setError(first.reason instanceof Error ? first.reason.message : "Failed to load market breadth")
      } else {
        setError(null)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load market breadth")
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

  const adChart = adLine.map((p) => ({ date: p.trade_date.slice(5), ad_line: p.advance_decline_line }))
  const oscChart = oscillator.map((p) => ({ date: p.trade_date.slice(5), oscillator: p.breadth_oscillator }))
  const hlChart = highLow.map((p) => ({ date: p.trade_date.slice(5), highs: p.new_highs, lows: p.new_lows }))
  const vbChart = volumeBreadth.map((p) => ({ date: p.trade_date.slice(5), advancing_volume: p.advancing_volume / 1e6, declining_volume: p.declining_volume / 1e6 }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-gray-500 text-sm">
          {summary ? `As of ${formatDate(summary.trade_date)}` : "Market breadth"}
        </p>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} onRetry={handleRefresh} />
      ) : (
        <>
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
              <BreadthStat label="Advancing" value={summary.advancing} positive />
              <BreadthStat label="Declining" value={summary.declining} negative />
              <BreadthStat
                label="Advance/Decline"
                value={summary.advance_decline_ratio?.toFixed(2) ?? "—"}
                tone={getChangeColor((summary.advance_decline_ratio ?? 1) - 1)}
              />
              <BreadthStat label="New Highs" value={summary.new_highs} tone="text-emerald-400" />
              <BreadthStat label="New Lows" value={summary.new_lows} tone="text-red-400" />
              <BreadthStat
                label="Breadth Osc."
                value={summary.breadth_oscillator?.toFixed(1) ?? "—"}
                tone={getChangeColor(summary.breadth_oscillator ?? 0)}
              />
              <BreadthStat
                label="Index Strength"
                value={summary.index_strength_score?.toFixed(1) ?? "—"}
                tone={getChangeColor((summary.index_strength_score ?? 50) - 50)}
              />
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Advance / Decline Line" icon={<TrendingUp size={14} className="text-titan-400" />}>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={adChart}>
                    <defs>
                      <linearGradient id="adFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
                    <Tooltip
                      contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      labelStyle={{ color: "#9ca3af" }}
                    />
                    <Area type="monotone" dataKey="ad_line" name="A/D Line" stroke="#22d3ee" strokeWidth={2} fill="url(#adFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Breadth Oscillator" icon={<Activity size={14} className="text-titan-400" />}>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={oscChart}>
                    <defs>
                      <linearGradient id="oscFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                    <Tooltip
                      contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      labelStyle={{ color: "#9ca3af" }}
                    />
                    <Area type="monotone" dataKey="oscillator" name="Oscillator" stroke="#a78bfa" strokeWidth={2} fill="url(#oscFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="New Highs vs New Lows" icon={<Minus size={14} className="text-titan-400" />}>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hlChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                    <Tooltip
                      contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      labelStyle={{ color: "#9ca3af" }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                    <Bar dataKey="highs" name="New Highs" fill="#10b981" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="lows" name="New Lows" fill="#ef4444" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Volume Breadth (millions)" icon={<Shield size={14} className="text-titan-400" />}>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={vbChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} width={50} />
                    <Tooltip
                      contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      labelStyle={{ color: "#9ca3af" }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                    <Bar dataKey="advancing_volume" name="Advancing Vol" fill="#22d3ee" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="declining_volume" name="Declining Vol" fill="#f43f5e" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}

function BreadthStat({ label, value, tone, positive, negative }: {
  label: string
  value: number | string
  tone?: string
  positive?: boolean
  negative?: boolean
}) {
  const finalTone =
    tone ??
    (positive ? "text-emerald-400" : negative ? "text-red-400" : "text-white")
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${finalTone}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  )
}

function ChartCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  )
}
