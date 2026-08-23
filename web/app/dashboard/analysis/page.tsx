"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Activity, BarChart3, RefreshCw, TrendingDown, TrendingUp } from "lucide-react"
import api from "@/lib/api"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import type { BatchQuotesResponse, IndexHistoryPoint, ResearchDetail } from "@/types"

type Recommendation = {
  id: number | string
  symbol: string
  direction?: string | null
  signal?: string | null
  confidence?: number | null
  price_target?: number | null
  current_price?: number | null
  timeframe?: string | null
  risk_level?: string | null
  score?: number | null
}

type AnalysisResponse = {
  symbol: string
  recommendation: {
    signal: string
    direction: string
    score: number
    confidence: number
    calibrated_probability: number
    conviction: string
    entry_price: number
    price_target: number
    stop_price: number
    risk_reward: number
    holding_period_days: number
    expected_return_pct: number
    risk_level: string
    no_trade: boolean
    rejection_reasons: string[]
    evidence: string[]
    caution: string[]
    as_of_date: string
    data_points: number
  }
  explainability?: unknown
}

type Metric = { label: string; value: string; signal?: string; positive?: boolean }

function sma(values: number[], period: number) {
  if (values.length < period) return null
  return values.slice(-period).reduce((a, b) => a + b, 0) / period
}

function ema(values: number[], period: number) {
  if (values.length < period) return null
  const k = 2 / (period + 1)
  let value = values.slice(0, period).reduce((a, b) => a + b, 0) / period
  for (let i = period; i < values.length; i += 1) value = values[i] * k + value * (1 - k)
  return value
}

function rsi(values: number[], period = 14) {
  if (values.length < period + 1) return null
  let gains = 0
  let losses = 0
  for (let i = 1; i <= period; i += 1) {
    const d = values[i] - values[i - 1]
    if (d >= 0) gains += d
    else losses -= d
  }
  let avgGain = gains / period
  let avgLoss = losses / period
  for (let i = period + 1; i < values.length; i += 1) {
    const d = values[i] - values[i - 1]
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
  }
  if (avgLoss === 0) return 100
  return 100 - 100 / (1 + avgGain / avgLoss)
}

function bollinger(values: number[], period = 20) {
  if (values.length < period) return null
  const window = values.slice(-period)
  const mid = window.reduce((a, b) => a + b, 0) / period
  const variance = window.reduce((sum, v) => sum + (v - mid) ** 2, 0) / period
  const sd = Math.sqrt(variance)
  return { mid, upper: mid + 2 * sd, lower: mid - 2 * sd }
}

function formatMetric(value: unknown) {
  if (value == null || value === "") return "—"
  if (typeof value === "number") return value.toLocaleString("en-IN", { maximumFractionDigits: 2 })
  return String(value)
}

export default function AnalysisPage() {
  const searchParams = useSearchParams()
  const requestedSymbol = searchParams.get("symbol")?.trim().toUpperCase() || ""
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [symbol, setSymbol] = useState(requestedSymbol || "RELIANCE")
  const [quote, setQuote] = useState<BatchQuotesResponse["quotes"][number] | null>(null)
  const [history, setHistory] = useState<IndexHistoryPoint[]>([])
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [research, setResearch] = useState<ResearchDetail | null>(null)
  const [financials, setFinancials] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadRecommendations = useCallback(async () => {
    try {
      const res = await api.get<{ items: Recommendation[] }>("/recommendations?status=active&limit=20")
      setRecommendations(res.items ?? [])
      if (!requestedSymbol && res.items?.[0]?.symbol) setSymbol(res.items[0].symbol)
    } catch {
      setRecommendations([])
    }
  }, [requestedSymbol])

  const loadStock = useCallback(async (nextSymbol: string) => {
    const clean = nextSymbol.trim().toUpperCase()
    if (!clean) return
    setLoading(true)
    setError(null)
    setSymbol(clean)
    try {
      const [quoteRes, historyRes, analysisRes] = await Promise.all([
        api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${encodeURIComponent(clean)}`),
        api.get<{ points: IndexHistoryPoint[] }>(`/market-data/history/${encodeURIComponent(clean)}`),
        api.get<AnalysisResponse>(`/recommendations/analyze/${encodeURIComponent(clean)}`),
      ])
      setQuote(quoteRes.quotes?.[0] ?? null)
      setHistory(historyRes.points ?? [])
      setAnalysis(analysisRes)

      try {
        const researchRes = await api.get<ResearchDetail>(`/research/${encodeURIComponent(clean)}`)
        setResearch(researchRes)
      } catch {
        setResearch(null)
      }

      try {
        const companyResearch = await api.get<{ financials?: unknown }>(`/company-research/${encodeURIComponent(clean)}`)
        const raw = companyResearch.financials
        setFinancials(raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {})
      } catch {
        setFinancials({})
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load live stock analysis")
      setQuote(null)
      setHistory([])
      setAnalysis(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRecommendations()
  }, [loadRecommendations])

  useEffect(() => {
    void loadStock(requestedSymbol || symbol)
    // Initial stock load only; changing the selector uses handleSelect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedSymbol])

  const technical = useMemo<Metric[]>(() => {
    const closes = history.map((p) => Number(p.close)).filter(Number.isFinite)
    const volumes = history.map((p) => Number(p.volume ?? 0)).filter(Number.isFinite)
    const last = closes.at(-1)
    const rsiValue = rsi(closes)
    const sma50 = sma(closes, 50)
    const sma200 = sma(closes, 200)
    const ema12 = ema(closes, 12)
    const ema26 = ema(closes, 26)
    const macd = ema12 != null && ema26 != null ? ema12 - ema26 : null
    const bb = bollinger(closes)
    const avgVolume = sma(volumes, 20)
    return [
      { label: "Current Price", value: last != null ? formatCurrency(last, "INR") : "—" },
      { label: "RSI (14)", value: rsiValue == null ? "—" : rsiValue.toFixed(2), signal: rsiValue == null ? "No data" : rsiValue >= 70 ? "Overbought" : rsiValue <= 30 ? "Oversold" : "Neutral", positive: rsiValue != null && rsiValue >= 50 && rsiValue < 70 },
      { label: "SMA (50)", value: sma50 == null ? "—" : formatCurrency(sma50, "INR"), signal: last != null && sma50 != null ? (last >= sma50 ? "Above" : "Below") : "No data", positive: last != null && sma50 != null && last >= sma50 },
      { label: "SMA (200)", value: sma200 == null ? "—" : formatCurrency(sma200, "INR"), signal: last != null && sma200 != null ? (last >= sma200 ? "Above" : "Below") : "No data", positive: last != null && sma200 != null && last >= sma200 },
      { label: "MACD", value: macd == null ? "—" : macd.toFixed(2), signal: macd == null ? "No data" : macd >= 0 ? "Bullish" : "Bearish", positive: macd != null && macd >= 0 },
      { label: "Bollinger Upper", value: bb == null ? "—" : formatCurrency(bb.upper, "INR"), signal: last != null && bb != null ? (last >= bb.upper ? "At/above upper" : "Inside band") : "No data", positive: undefined },
      { label: "Volume vs 20D Avg", value: volumes.length && avgVolume ? `${(volumes.at(-1)! / avgVolume * 100).toFixed(0)}%` : "—", signal: volumes.length && avgVolume ? (volumes.at(-1)! >= avgVolume ? "Above avg" : "Below avg") : "No data", positive: volumes.length && avgVolume ? volumes.at(-1)! >= avgVolume : undefined },
    ]
  }, [history])

  const livePrice = quote?.last_price ?? history.at(-1)?.close ?? null
  const ai = analysis?.recommendation
  const stored = recommendations.find((r) => r.symbol === symbol)
  const financialEntries = Object.entries(financials).filter(([, value]) => value != null && value !== "")

  const handleSelect = (value: string) => {
    void loadStock(value)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Technical & Fundamental Analysis</h1>
          <p className="text-gray-500 text-sm mt-1">Live price + stock-specific technical, fundamental and AI analysis</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={symbol} onChange={(e) => handleSelect(e.target.value)} className="bg-titan-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white min-w-44">
            {recommendations.length === 0 && <option value={symbol}>{symbol}</option>}
            {recommendations.map((r) => <option key={r.symbol} value={r.symbol}>{r.symbol}</option>)}
          </select>
          <button onClick={() => void loadStock(symbol)} disabled={loading || analyzing} className="inline-flex items-center gap-1.5 text-xs text-gray-400 border border-white/10 rounded-lg px-3 py-2 hover:text-white">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="glass-card p-4 border border-red-500/30 text-sm text-red-300">{error}</div>}

      <div className="glass-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2"><span className="text-xl font-bold text-white">{symbol}</span><span className="badge-blue">NSE</span></div>
            <p className="text-xs text-gray-500 mt-1">{quote?.name ?? symbol} · {quote?.source ?? "live market feed"}</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-white">{livePrice == null ? "—" : formatCurrency(livePrice, "INR")}</div>
            {quote?.change != null && <div className={`text-sm font-medium ${getChangeColor(quote.change)}`}>{quote.change >= 0 ? "+" : ""}{quote.change.toFixed(2)} ({quote.change_percent?.toFixed(2) ?? "—"}%)</div>}
            <div className="text-[11px] text-gray-500 mt-1">Latest live quote / latest available close</div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Activity size={16} className="text-titan-400" /> Technical Indicators — {symbol}</h3>
          {loading ? <div className="h-48 animate-pulse bg-white/5 rounded-lg" /> : <div className="space-y-3">{technical.map((item) => <div key={item.label} className="flex items-center justify-between border-b border-white/5 pb-3 last:border-0"><div><div className="text-xs text-gray-500">{item.label}</div><div className="text-sm font-semibold text-white mt-1">{item.value}</div></div>{item.signal && <span className={`text-xs px-2 py-1 rounded-full ${item.positive === true ? "badge-green" : item.positive === false ? "badge-red" : "badge-blue"}`}>{item.signal}</span>}</div>)}</div>}
        </div>

        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><BarChart3 size={16} className="text-titan-400" /> Fresh AI Recommendation — {symbol}</h3>
          {analyzing ? <div className="h-48 animate-pulse bg-white/5 rounded-lg" /> : ai ? <div className="space-y-3">
            <div className="flex items-center justify-between"><span className={`text-sm font-bold ${ai.direction === "BUY" ? "text-emerald-400" : ai.direction === "SELL" ? "text-red-400" : "text-yellow-400"}`}>{ai.signal.replaceAll("_", " ").toUpperCase()}</span><span className="text-sm text-white">{(ai.confidence * 100).toFixed(1)}% confidence</span></div>
            <div className="grid grid-cols-2 gap-3 text-xs"><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Entry</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.entry_price, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Target</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.price_target, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Stop</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.stop_price, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Risk/Reward</span><div className="text-white font-semibold mt-1">1:{ai.risk_reward.toFixed(2)}</div></div></div>
            <p className="text-xs text-gray-500">Model score {ai.score.toFixed(1)} · {ai.data_points} real price data points · {ai.holding_period_days} day horizon</p>
            {ai.no_trade && <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-xs text-yellow-300">NO-TRADE filter active. {ai.rejection_reasons.join(" ")}</div>}
            {ai.evidence.length > 0 && <div><div className="text-xs font-semibold text-gray-400 mb-2">Evidence</div><ul className="space-y-1">{ai.evidence.slice(0, 6).map((e, i) => <li key={i} className="text-xs text-gray-500">• {e}</li>)}</ul></div>}
          </div> : <p className="text-sm text-gray-500">No live AI analysis available.</p>}
        </div>
      </div>

      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4"><h3 className="text-sm font-semibold text-white">Fundamental Metrics — {symbol}</h3><span className="text-[11px] text-gray-500">Only sourced data is shown</span></div>
        {financialEntries.length === 0 ? <p className="text-sm text-gray-500 py-6 text-center">No company fundamental dataset is available for {symbol}. TitanX will not display placeholder P/E, EPS, ROE or margin values.</p> : <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{financialEntries.slice(0, 12).map(([key, value]) => <div key={key} className="bg-white/5 rounded-lg p-3"><div className="text-xs text-gray-500">{key.replaceAll("_", " ")}</div><div className="text-sm font-semibold text-white mt-1">{formatMetric(value)}</div></div>)}</div>}
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4">AI Recommendation Evidence & Cautions</h3>
        {ai ? <div className="grid md:grid-cols-2 gap-4"><div><div className="text-xs text-gray-500 mb-2">Evidence</div><ul className="space-y-1">{ai.evidence.map((e, i) => <li key={i} className="text-xs text-gray-400">• {e}</li>)}</ul></div><div><div className="text-xs text-gray-500 mb-2">Caution</div><ul className="space-y-1">{ai.caution.length ? ai.caution.map((e, i) => <li key={i} className="text-xs text-gray-400">• {e}</li>) : <li className="text-xs text-gray-500">No additional caution returned by the model.</li>}</ul></div></div> : <p className="text-sm text-gray-500">No recommendation evidence available.</p>}
      </div>

      {research?.reasoning && <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-2">Research Context — {symbol}</h3><p className="text-sm text-gray-400">{research.reasoning}</p></div>}

      {stored && <div className="text-[11px] text-gray-600">Stored recommendation exists for {symbol}, but the displayed AI result above is recalculated from the latest available market history.</div>}
    </div>
  )
}
