"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { EquityCurvePoint, PaperAccountSummary } from "@/types"
import { formatCurrency } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

export default function PortfolioProfitPage() {
  const [curve, setCurve] = useState<EquityCurvePoint[]>([])
  const [account, setAccount] = useState<PaperAccountSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const [curveRes, accRes] = await Promise.allSettled([
        api.get<EquityCurvePoint[]>("/paper-trading/equity-curve"),
        api.get<PaperAccountSummary>("/paper-trading/account"),
      ])
      if (!mounted.current) return
      if (curveRes.status === "fulfilled") setCurve(curveRes.value)
      if (accRes.status === "fulfilled") setAccount(accRes.value)
      if (curveRes.status === "rejected" && accRes.status === "rejected") {
        setError(curveRes.reason instanceof Error ? curveRes.reason.message : "Failed to load equity curve")
      } else {
        setError(null)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load equity curve")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(), [load])

  const chartData = useMemo(() => curve.map((p) => ({ date: p.date, equity: p.equity })), [curve])

  const peak = useMemo(() => (chartData.length ? Math.max(...chartData.map((p) => p.equity)) : 0), [chartData])
  const trough = useMemo(() => (chartData.length ? Math.min(...chartData.map((p) => p.equity)) : 0), [chartData])
  const start = chartData[0]?.equity ?? account?.initial_capital ?? 0
  const end = chartData[chartData.length - 1]?.equity ?? account?.portfolio_value ?? 0
  const gain = end - start
  const gainPct = start ? (gain / start) * 100 : 0

  return (
    <div className="space-y-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <ProfitStat label="Starting Equity" value={formatCurrency(start)} />
            <ProfitStat label="Current Equity" value={formatCurrency(end)} />
            <ProfitStat label="Total Profit" value={formatCurrency(gain)} positive={gain >= 0} />
            <ProfitStat label="Growth" value={`${gainPct >= 0 ? "+" : ""}${gainPct.toFixed(2)}%`} positive={gainPct >= 0} />
          </div>

          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Equity Curve</h3>
            <div className="h-80">
              {chartData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={(v) => v.slice(0, 10)} />
                    <YAxis
                      tick={{ fill: "#6b7280", fontSize: 11 }}
                      tickFormatter={(v) => formatCurrency(Number(v))}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      labelStyle={{ color: "#9ca3af" }}
                      formatter={(value: number | string, name: string) => [formatCurrency(Number(value)), name]}
                    />
                    <Area type="monotone" dataKey="equity" stroke="#22d3ee" strokeWidth={2} fill="url(#equityGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 text-sm">No equity curve data</div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-gray-500 text-xs">Peak Equity</p>
                <p className="text-white font-semibold mt-1">{formatCurrency(peak)}</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-gray-500 text-xs">Trough Equity</p>
                <p className="text-white font-semibold mt-1">{formatCurrency(trough)}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function ProfitStat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const cls = positive === undefined ? "text-white" : positive ? "text-emerald-400" : "text-red-400"
  return (
    <div className="glass-card p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${cls}`}>{value}</p>
    </div>
  )
}
