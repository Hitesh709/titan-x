"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { ArrowLeft, Building2, TrendingUp, TrendingDown, Activity } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { BatchQuotesResponse, CompanyProfile, IndexHistoryPoint, StockHistoryResponse } from "@/types"
import { formatCompactNumber, formatCurrency, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

const RANGES = ["1M", "3M", "6M", "1Y"] as const
type Range = (typeof RANGES)[number]

const DAYS: Record<Range, number> = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 }

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>()
  const router = useRouter()
  const symbol = String(params?.symbol ?? "").toUpperCase()

  const [quote, setQuote] = useState<BatchQuotesResponse["quotes"][number] | null>(null)
  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [points, setPoints] = useState<IndexHistoryPoint[]>([])
  const [range, setRange] = useState<Range>("3M")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      try {
        const [quoteRes, profileRes, historyRes] = await Promise.all([
          api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${symbol}`),
          api.get<CompanyProfile>(`/market-data/profile/${symbol}`),
          api.get<StockHistoryResponse>(`/market-data/history/${symbol}`),
        ])
        if (!mounted.current) return
        setQuote(quoteRes.quotes?.[0] ?? null)
        setProfile(profileRes)
        setPoints(historyRes.points ?? [])
        setError(null)
      } catch (e) {
        if (!mounted.current) return
        setError(e instanceof Error ? e.message : "Failed to load stock data")
      } finally {
        if (mounted.current) setLoading(false)
      }
    },
    [symbol],
  )

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const chartData = useMemo(() => {
    const cutoff = Date.now() - DAYS[range] * 86_400_000
    return points
      .filter((p) => new Date(p.trade_date).getTime() >= cutoff)
      .map((p) => ({
        ...p,
        date: p.trade_date.slice(5),
        change: p.close,
      }))
  }, [points, range])

  const first = chartData[0]?.close
  const last = chartData[chartData.length - 1]?.close
  const changePct = first ? ((last - first) / first) * 100 : null
  const up = quote?.change == null ? null : quote.change >= 0
  const name = profile?.name ?? quote?.name ?? symbol

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors"
        >
          <ArrowLeft size={13} /> Back
        </button>
        <div className="flex items-center gap-3">
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

      {loading && !quote ? (
        <WidgetLoading lines={6} />
      ) : error && !quote ? (
        <WidgetError message={error} onRetry={() => void load()} />
      ) : (
        <div className="space-y-6">
          <div className="glass-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-titan-600/20 to-titan-800/20 border border-titan-700/30 flex items-center justify-center">
                  <Building2 size={24} className="text-titan-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h1 className="text-xl font-bold text-white">{name}</h1>
                    <span className="badge-blue">{symbol}</span>
                    <span className="text-[10px] text-emerald-500/80 font-medium uppercase tracking-wider">
                      {quote?.exchange ?? profile?.exchange ?? "NSE"}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">
                    {[profile?.sector, profile?.industry].filter(Boolean).join(" · ") || "Equity"}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className={`text-2xl font-bold ${quote?.last_price == null ? "text-white" : getChangeColor(quote?.change ?? 0)}`}>
                  {quote?.last_price != null ? formatCurrency(quote.last_price, "INR") : "—"}
                </div>
                {quote?.change != null && quote.change_percent != null && (
                  <div className="flex items-center gap-1 justify-end text-sm mt-1">
                    {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    <span className={`font-medium ${getChangeColor(quote.change)}`}>
                      {up ? "+" : ""}{quote.change.toFixed(2)} ({up ? "+" : ""}{quote.change_percent.toFixed(2)}%)
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Open" value={points[0]?.open} />
              <Stat label="High" value={points.reduce((m, p) => Math.max(m, p.high), points[0]?.high ?? 0)} />
              <Stat label="Low" value={points.reduce((m, p) => Math.min(m, p.low), points[0]?.low ?? 0)} />
              <Stat label="Volume" value={quote?.volume ?? points[points.length - 1]?.volume} compact />
            </div>

            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Market Cap" value={quote?.market_cap ?? profile?.market_cap} compact />
              <Stat label="Sector" value={undefined} text={profile?.sector ?? "—"} />
              <Stat label="Currency" value={undefined} text={quote?.currency ?? profile?.currency ?? "INR"} />
              <Stat label="Market State" value={undefined} text={quote?.market_state ?? "REGULAR"} />
            </div>
          </div>

          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <Activity size={16} className="text-titan-400" /> Price Chart
            </h3>
            {chartData.length === 0 ? (
              <p className="text-sm text-gray-500 py-10 text-center">No chart data available.</p>
            ) : (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1">
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
                    <Area type="monotone" dataKey="change" stroke="#22d3ee" strokeWidth={2} fill="url(#stockFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
            {changePct != null && (
              <p className="mt-3 text-xs text-gray-500">
                {symbol} {range} change:{" "}
                <span className={`font-medium ${getChangeColor(changePct)}`}>
                  {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                </span>
              </p>
            )}
          </div>

          <div className="flex justify-center">
            <Link href={`/dashboard/trading`} className="btn-primary text-sm px-6">
              Trade {symbol}
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  text,
  compact,
}: {
  label: string
  value: number | string | null | undefined
  text?: string
  compact?: boolean
}) {
  return (
    <div className="bg-white/5 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">
        {text ?? (value == null ? "—" : compact ? formatCompactNumber(Number(value)) : formatCurrency(Number(value), "INR").replace("₹", ""))}
      </p>
    </div>
  )
}
