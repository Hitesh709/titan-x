"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { RefreshCw } from "lucide-react"
import api from "@/lib/api"
import type { IndexHistoryPoint, IndexSnapshot } from "@/types"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

const RANGES = ["1W", "1M", "3M", "6M", "YTD", "1Y"] as const
type Range = (typeof RANGES)[number]

export default function ChartsPage() {
  const [indices, setIndices] = useState<IndexSnapshot[]>([])
  const [symbol, setSymbol] = useState<string>("NIFTY")
  const [range, setRange] = useState<Range>("3M")
  const [points, setPoints] = useState<IndexHistoryPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const loadIndices = useCallback(async () => {
    try {
      const res = await api.get<{ items: IndexSnapshot[] }>("/indices")
      if (!mounted.current) return
      setIndices(res.items ?? [])
      if (res.items?.length && !res.items.some((i) => i.symbol === symbol)) {
        setSymbol(res.items[0].symbol)
      }
    } catch {
      // ignore index list errors on the charts page
    }
  }, [symbol])

  const loadHistory = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<{ points: IndexHistoryPoint[] }>(
        `/indices/${symbol}/history?range=${range}`
      )
      if (!mounted.current) return
      setPoints(res.points ?? [])
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load chart data")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [symbol, range])

  useEffect(() => {
    mounted.current = true
    loadIndices()
    return () => {
      mounted.current = false
    }
  }, [loadIndices])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  const chartData = points.map((p) => ({
    ...p,
    date: p.trade_date.slice(5),
    change: p.close,
  }))
  const first = points[0]?.close
  const last = points[points.length - 1]?.close
  const changePct = first ? ((last - first) / first) * 100 : 0
  const selected = indices.find((i) => i.symbol === symbol)

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          {indices.map((i) => (
            <button
              key={i.symbol}
              onClick={() => setSymbol(i.symbol)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                symbol === i.symbol
                  ? "bg-titan-600/20 text-titan-400 border-titan-600/30"
                  : "bg-white/5 text-gray-400 hover:text-gray-200 border-white/10"
              }`}
            >
              {i.name}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                range === r
                  ? "bg-titan-600/20 text-titan-400 border-titan-600/30"
                  : "bg-white/5 text-gray-400 hover:text-gray-200 border-white/10"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : (
        <div className="glass-card p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-white">{selected?.name ?? symbol}</h3>
              <p className="text-sm text-gray-500">
                {last !== undefined ? formatCurrency(last, "INR").replace("₹", "") : "—"}
                <span className={`ml-2 font-medium ${getChangeColor(changePct)}`}>
                  {formatPercent(changePct)} ({range})
                </span>
              </p>
            </div>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="indexFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => v.toLocaleString()}
                  width={80}
                />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                  labelStyle={{ color: "#9ca3af" }}
                  formatter={(value: number | string) => [
                    formatCurrency(Number(value), "INR").replace("₹", ""),
                    "Close",
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="change"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  fill="url(#indexFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <ChartStat label="Open" value={points[0]?.open} />
            <ChartStat label="High" value={points.reduce((m, p) => Math.max(m, p.high), points[0]?.high ?? 0)} />
            <ChartStat label="Low" value={points.reduce((m, p) => Math.min(m, p.low), points[0]?.low ?? 0)} />
            <ChartStat label="Close" value={points[points.length - 1]?.close} />
          </div>
        </div>
      )}
    </div>
  )
}

function ChartStat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bg-white/5 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">
        {value !== undefined ? formatCurrency(value, "INR").replace("₹", "") : "—"}
      </p>
    </div>
  )
}
