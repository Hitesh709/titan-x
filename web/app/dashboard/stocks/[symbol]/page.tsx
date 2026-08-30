"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Building2,
  CalendarRange,
  CheckCircle2,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Activity,
} from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import CandlestickChart from "@/components/dashboard/candlestick-chart"
import { formatCompactNumber, formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

type Quote = {
  symbol: string
  last_price: number | null
  change: number | null
  change_percent: number | null
  prev_close?: number | null
  day_high?: number | null
  day_low?: number | null
  volume?: number | null
  market_cap?: number | null
  currency?: string | null
  name?: string | null
  exchange?: string | null
  market_state?: string | null
}

type Profile = {
  symbol?: string
  name?: string | null
  sector?: string | null
  industry?: string | null
  market_cap?: number | null
  exchange?: string | null
  currency?: string | null
}

type Research = {
  company_name?: string
  has_research?: boolean
  direction?: string
  signal?: string
  risk_level?: string
  timeframe?: string
  generated_at?: string
  days?: number
  score?: number | null
  confidence?: number | null
  predicted_return_pct?: number | null
  current_price?: number | null
  price_target?: number | null
  reasoning?: string | null
  evidence?: string[]
  caution?: string[]
}

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>()
  const router = useRouter()
  const symbol = String(params?.symbol ?? "").toUpperCase()
  const mounted = useRef(true)
  const [quote, setQuote] = useState<Quote | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [research, setResearch] = useState<Research | null>(null)
  const [researchLoaded, setResearchLoaded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [quoteRes, profileRes] = await Promise.all([
        api.get<{ quotes: Quote[] }>(`/market-data/quotes?symbols=${encodeURIComponent(symbol)}`),
        api.get<Profile>(`/market-data/profile/${encodeURIComponent(symbol)}`),
      ])

      if (!mounted.current) return
      setQuote(quoteRes.quotes?.[0] ?? null)
      setProfile(profileRes)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load stock data")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [symbol])

  const loadResearch = useCallback(async () => {
    setResearchLoaded(false)
    try {
      const res = await api.get<Research>(`/research/${encodeURIComponent(symbol)}`)
      if (mounted.current) setResearch(res)
    } catch {
      if (mounted.current) setResearch(null)
    } finally {
      if (mounted.current) setResearchLoaded(true)
    }
  }, [symbol])

  useEffect(() => {
    mounted.current = true
    void load()
    void loadResearch()
    return () => {
      mounted.current = false
    }
  }, [load, loadResearch])

  useLiveRefresh(() => void load(true), [load])

  const name = profile?.name ?? quote?.name ?? symbol
  const up = quote?.change == null ? null : quote.change >= 0
  const tradeSide = research?.direction === "SELL" ? "sell" : "buy"
  const tradeHref = `/dashboard/trading?symbol=${encodeURIComponent(symbol)}&side=${tradeSide}`

  if (loading && !quote) {
    return <WidgetLoading lines={8} />
  }

  if (error && !quote) {
    return <WidgetError message={error} onRetry={() => void load()} />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors"
        >
          <ArrowLeft size={13} />
          Back
        </button>
        <span className="text-[11px] text-gray-500">Live stock market data · {symbol}</span>
      </div>

      {error && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-300">
          {error}
        </div>
      )}

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
            <div className={`text-2xl font-bold ${quote?.last_price == null ? "text-white" : getChangeColor(quote.change ?? 0)}`}>
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
          <Stat label="Previous Close" value={quote?.prev_close} />
          <Stat label="Day High" value={quote?.day_high} />
          <Stat label="Day Low" value={quote?.day_low} />
          <Stat label="Volume" value={quote?.volume} compact />
        </div>

        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Market Cap" value={quote?.market_cap ?? profile?.market_cap} compact />
          <Stat label="Sector" text={profile?.sector ?? "—"} />
          <Stat label="Currency" text={quote?.currency ?? profile?.currency ?? "INR"} />
          <Stat label="Market State" text={quote?.market_state ?? "REGULAR"} />
        </div>
      </div>

      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity size={16} className="text-titan-400" />
            Price Chart
          </h3>
          <span className="text-[10px] text-gray-500">Candles · OHLCV · Up/Down</span>
        </div>
        <CandlestickChart symbol={symbol} />
      </div>

      <ResearchBlock
        symbol={symbol}
        research={research}
        loaded={researchLoaded}
        onRefresh={() => void loadResearch()}
      />

      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href={`/dashboard/trading?symbol=${encodeURIComponent(symbol)}&side=buy`}
          className="btn-primary text-sm px-6"
        >
          BUY {symbol}
        </Link>
        <Link
          href={`/dashboard/trading?symbol=${encodeURIComponent(symbol)}&side=sell`}
          className="btn-secondary text-sm px-6"
        >
          SELL {symbol}
        </Link>
        <Link href={tradeHref} className="text-xs text-gray-400 hover:text-titan-300 px-3 py-2">
          Trade Signal → {research?.direction ?? "BUY"}
        </Link>
      </div>
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
  value?: number | null
  text?: string
  compact?: boolean
}) {
  let displayValue = "—"
  if (text != null) {
    displayValue = text
  } else if (value != null) {
    displayValue = compact
      ? formatCompactNumber(Number(value))
      : formatCurrency(Number(value), "INR").replace("₹", "")
  }

  return (
    <div className="bg-white/5 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{displayValue}</p>
    </div>
  )
}

function ResearchBlock({
  symbol,
  research,
  loaded,
  onRefresh,
}: {
  symbol: string
  research: Research | null
  loaded: boolean
  onRefresh: () => void
}) {
  let content: React.ReactNode

  if (!loaded) {
    content = <div className="h-16 animate-pulse bg-white/5 rounded-lg" />
  } else if (!research) {
    content = (
      <p className="text-sm text-gray-500 py-4 text-center">
        No research yet for {symbol}. Run a market scan to generate an AI recommendation.
      </p>
    )
  } else if (!research.has_research) {
    content = (
      <p className="text-sm text-gray-500 py-4 text-center">
        {research.company_name ?? symbol} does not have a live recommendation yet.
      </p>
    )
  } else {
    content = (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={
              research.direction === "BUY"
                ? "badge-green"
                : research.direction === "SELL"
                  ? "badge-red"
                  : "badge-blue"
            }
          >
            {research.direction ?? "HOLD"}
            {research.signal ? ` · ${research.signal.replaceAll("_", " ")}` : ""}
          </span>
          {research.risk_level && <span className="text-xs text-gray-500">{research.risk_level} risk</span>}
          {research.timeframe && <span className="text-xs text-gray-500">{research.timeframe}</span>}
          {research.generated_at && (
            <span className="ml-auto text-[11px] text-gray-500">
              Generated {new Date(research.generated_at).toLocaleDateString("en-IN", {
                day: "numeric",
                month: "short",
              })}
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Score" text={research.score != null ? research.score.toFixed(1) : "—"} />
          <Stat label="Confidence" text={research.confidence != null ? `${Math.round(research.confidence)}%` : "—"} />
          <Stat
            label="Expected Return"
            text={research.predicted_return_pct != null ? formatPercent(research.predicted_return_pct) : "—"}
          />
          <Stat
            label="Current · Target"
            text={
              `${research.current_price != null ? formatCurrency(research.current_price, "INR") : "—"}` +
              `${research.price_target ? ` → ${formatCurrency(research.price_target, "INR")}` : ""}`
            }
          />
        </div>

        {research.reasoning && (
          <div className="mt-4 flex items-start gap-2 text-sm text-gray-300 bg-white/5 rounded-lg p-4">
            <Sparkles size={15} className="text-titan-400 shrink-0 mt-0.5" />
            <p>{research.reasoning}</p>
          </div>
        )}

        {(research.evidence?.length ?? 0) > 0 && (
          <div className="mt-3">
            <p className="text-xs text-gray-500 mb-2">Evidence</p>
            <ul className="space-y-1.5">
              {research.evidence!.slice(0, 8).map((e, i) => (
                <li key={i} className="text-xs text-gray-400 flex items-start gap-2">
                  <CheckCircle2 size={13} className="text-emerald-500 shrink-0 mt-0.5" />
                  {e}
                </li>
              ))}
            </ul>
          </div>
        )}

        {(research.caution?.length ?? 0) > 0 && (
          <div className="mt-3">
            <p className="text-xs text-gray-500 mb-2">Caution</p>
            <ul className="space-y-1.5">
              {research.caution!.slice(0, 5).map((c, i) => (
                <li key={i} className="text-xs text-amber-400/90 flex items-start gap-2">
                  <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            onClick={onRefresh}
            className="text-xs text-titan-400 hover:text-titan-300 inline-flex items-center gap-1"
          >
            <Activity size={12} />
            Refresh research
          </button>
        </div>
      </>
    )
  }

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <BookOpen size={16} className="text-titan-400" />
          Titan Research
        </h3>
        {research && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-titan-600/10 border border-titan-600/25 text-titan-300 text-xs font-medium">
            <CalendarRange size={12} />
            {research.days ? `${research.days.toLocaleString("en-IN")} data days` : "research"}
          </span>
        )}
      </div>
      {content}
    </div>
  )
}
