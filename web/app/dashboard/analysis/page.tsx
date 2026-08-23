"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Activity, BarChart3, RefreshCw, Search, TrendingDown, TrendingUp } from "lucide-react"
import api from "@/lib/api"
import { formatCurrency, getChangeColor } from "@/lib/utils"
import type { BatchQuotesResponse, IndexHistoryPoint } from "@/types"

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
}

type Metric = { label: string; value: string; signal?: string; positive?: boolean }
type Quote = BatchQuotesResponse["quotes"][number]

const COMMON_NSE_SCRIPTS = [
  "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL", "ITC", "LT", "HINDUNILVR",
  "KOTAKBANK", "BAJFINANCE", "AXISBANK", "MARUTI", "TITAN", "SUNPHARMA", "ADANIENT", "WIPRO", "ONGC", "NTPC",
  "POWERGRID", "ASIANPAINT", "ULTRACEMCO", "HCLTECH", "TATAMOTORS", "JSWSTEEL", "TATASTEEL", "M&M", "TECHM", "NESTLEIND",
  "COALINDIA", "TATACONSUM", "ADANIPORTS", "HINDALCO", "GRASIM", "CIPLA", "DRREDDY", "EICHERMOT", "HEROMOTOCO", "BAJAJFINSV",
  "BRITANNIA", "APOLLOHOSP", "DIVISLAB", "BPCL", "IOC", "TATAPOWER", "BEL", "HAL", "TRENT", "INDUSINDBK",
  "PIDILITIND", "DLF", "IRCTC", "ZOMATO", "DMART", "SIEMENS", "ABB", "CANBK", "PNB", "BANKBARODA",
]

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

function signalClass(direction?: string | null) {
  const d = String(direction ?? "").toUpperCase()
  if (d.includes("BUY") || d.includes("BULL")) return "badge-green"
  if (d.includes("SELL") || d.includes("BEAR")) return "badge-red"
  return "badge-yellow"
}

export default function AnalysisPage() {
  const searchParams = useSearchParams()
  const requestedSymbol = searchParams.get("symbol")?.trim().toUpperCase() || ""
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [topQuotes, setTopQuotes] = useState<Record<string, Quote>>({})
  const [searchTerm, setSearchTerm] = useState(requestedSymbol || "RELIANCE")
  const [symbol, setSymbol] = useState(requestedSymbol || "RELIANCE")
  const [searchOpen, setSearchOpen] = useState(false)
  const [quote, setQuote] = useState<Quote | null>(null)
  const [history, setHistory] = useState<IndexHistoryPoint[]>([])
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [financials, setFinancials] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const scriptOptions = useMemo(() => Array.from(new Set([...COMMON_NSE_SCRIPTS, ...recommendations.map((r) => r.symbol).filter(Boolean)])).sort(), [recommendations])
  const filteredScripts = useMemo(() => {
    const q = searchTerm.trim().toUpperCase()
    if (!q) return scriptOptions.slice(0, 12)
    return scriptOptions.filter((s) => s.includes(q)).slice(0, 12)
  }, [scriptOptions, searchTerm])

  const loadRecommendations = useCallback(async () => {
    try {
      const res = await api.get<{ items: Recommendation[] }>("/recommendations?status=active&limit=50")
      const items = res.items ?? []
      setRecommendations(items)
      const top = [...items].sort((a, b) => (b.score ?? b.confidence ?? 0) - (a.score ?? a.confidence ?? 0)).slice(0, 5)
      if (top.length) {
        try {
          const quoteRes = await api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${top.map((r) => r.symbol).join(",")}`)
          const map: Record<string, Quote> = {}
          for (const q of quoteRes.quotes ?? []) map[q.symbol] = q
          setTopQuotes(map)
        } catch {
          setTopQuotes({})
        }
      }
    } catch {
      setRecommendations([])
      setTopQuotes({})
    }
  }, [])

  const loadStock = useCallback(async (nextSymbol: string) => {
    const clean = nextSymbol.trim().toUpperCase()
    if (!clean) return
    setLoading(true)
    setError(null)
    setSymbol(clean)
    setSearchTerm(clean)
    setSearchOpen(false)
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
      setFinancials({})
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadRecommendations() }, [loadRecommendations])
  useEffect(() => { void loadStock(requestedSymbol || symbol) }, [requestedSymbol])

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
      { label: "Bollinger Upper", value: bb == null ? "—" : formatCurrency(bb.upper, "INR"), signal: last != null && bb != null ? (last >= bb.upper ? "At/above upper" : "Inside band") : "No data" },
      { label: "Volume vs 20D Avg", value: volumes.length && avgVolume ? `${(volumes.at(-1)! / avgVolume * 100).toFixed(0)}%` : "—", signal: volumes.length && avgVolume ? (volumes.at(-1)! >= avgVolume ? "Above avg" : "Below avg") : "No data", positive: volumes.length && avgVolume ? volumes.at(-1)! >= avgVolume : undefined },
    ]
  }, [history])

  const ai = analysis?.recommendation
  const livePrice = quote?.last_price ?? null
  const financialEntries = Object.entries(financials).filter(([, value]) => value != null && value !== "")
  const topFive = useMemo(() => [...recommendations].sort((a, b) => (b.score ?? b.confidence ?? 0) - (a.score ?? a.confidence ?? 0)).slice(0, 5), [recommendations])
  const submitSearch = () => { const clean = searchTerm.trim().toUpperCase(); if (clean) void loadStock(clean) }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-bold text-white">Technical & Fundamental Analysis</h1><p className="text-gray-500 text-sm mt-1">Search any NSE script for live price, technical, fundamental and AI analysis</p></div>
        <button onClick={() => void loadStock(symbol)} disabled={loading} className="inline-flex items-center gap-1.5 text-xs text-gray-400 border border-white/10 rounded-lg px-3 py-2 hover:text-white disabled:opacity-50"><RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh</button>
      </div>

      <div className="glass-card p-4">
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input value={searchTerm} onChange={(e) => { setSearchTerm(e.target.value.toUpperCase()); setSearchOpen(true) }} onFocus={() => setSearchOpen(true)} onKeyDown={(e) => { if (e.key === "Enter") submitSearch() }} placeholder="Search NSE script e.g. RELIANCE, TCS, INFY" className="w-full bg-titan-900 border border-white/10 rounded-lg pl-10 pr-4 py-3 text-sm text-white placeholder:text-gray-600 outline-none focus:border-titan-500" />
            {searchOpen && filteredScripts.length > 0 && <div className="absolute z-30 mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-white/10 bg-[#111525] shadow-2xl">{filteredScripts.map((item) => <button key={item} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => void loadStock(item)} className="w-full px-4 py-3 text-left text-sm text-gray-200 hover:bg-white/10 flex items-center justify-between"><span>{item}</span><span className="text-[10px] text-gray-500">NSE</span></button>)}</div>}
          </div>
          <button onClick={submitSearch} className="inline-flex items-center justify-center gap-2 rounded-lg bg-titan-600 px-5 py-3 text-sm font-semibold text-white hover:bg-titan-500"><Search size={15} /> Analyze Script</button>
        </div>
        <p className="text-[11px] text-gray-600 mt-2">Type a symbol directly even if it is not in the suggestions. TitanX will request the configured market-data feed for that script.</p>
      </div>

      {topFive.length > 0 && <section><div className="flex items-center justify-between mb-3"><div><h2 className="text-lg font-semibold text-white">Top 5 AI Recommendations</h2><p className="text-xs text-gray-500">Current ranked signals from TitanX AI · click any script to analyze it</p></div><span className="badge-blue">LIVE PRICE</span></div><div className="grid md:grid-cols-2 xl:grid-cols-5 gap-3">{topFive.map((rec, index) => { const q = topQuotes[rec.symbol]; const direction = rec.direction ?? rec.signal ?? "HOLD"; const score = rec.score ?? ((rec.confidence ?? 0) * 100); return <button key={rec.symbol} type="button" onClick={() => void loadStock(rec.symbol)} className="glass-card p-4 text-left hover:border-titan-500/40 transition-colors"><div className="flex items-center justify-between mb-2"><span className="w-7 h-7 rounded-lg bg-titan-600/30 text-titan-300 flex items-center justify-center text-xs font-bold">{index + 1}</span><span className={signalClass(direction)}>{String(direction).replaceAll("_", " ")}</span></div><div className="text-base font-bold text-white">{rec.symbol}</div><div className={`text-sm font-semibold mt-1 ${q?.change != null ? getChangeColor(q.change) : "text-gray-400"}`}>{q?.last_price != null ? formatCurrency(q.last_price, "INR") : "Price unavailable"}</div>{q?.change_percent != null && <div className="text-[11px] text-gray-500">{q.change_percent >= 0 ? "+" : ""}{q.change_percent.toFixed(2)}% today</div>}<div className="mt-3 flex items-center justify-between text-[11px]"><span className="text-gray-500">AI score</span><span className="text-titan-300 font-semibold">{score.toFixed(0)}</span></div><div className="mt-2 h-1.5 rounded-full bg-white/5 overflow-hidden"><div className="h-full bg-gradient-to-r from-titan-600 to-emerald-500" style={{ width: `${Math.max(0, Math.min(100, score))}%` }} /></div><div className="mt-2 text-[11px] text-gray-500">Confidence {rec.confidence != null ? `${(rec.confidence * 100).toFixed(1)}%` : "—"}</div></button> })}</div></section>}

      {error && <div className="glass-card p-4 border border-red-500/30 text-sm text-red-300">{error}</div>}

      <div className="glass-card p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className="text-xl font-bold text-white">{symbol}</span><span className="badge-blue">NSE</span></div><p className="text-xs text-gray-500 mt-1">{quote?.name ?? symbol} · {quote?.source ?? "live market feed"}</p></div><div className="text-right"><div className="text-2xl font-bold text-white">{livePrice == null ? "—" : formatCurrency(livePrice, "INR")}</div>{quote?.change != null && <div className={`text-sm font-medium flex items-center justify-end gap-1 ${getChangeColor(quote.change)}`}>{quote.change >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}{quote.change >= 0 ? "+" : ""}{quote.change.toFixed(2)} ({quote.change_percent?.toFixed(2) ?? "—"}%)</div>}<div className="text-[11px] text-gray-500 mt-1">Latest live quote / latest available close</div></div></div></div>

      <div className="grid lg:grid-cols-2 gap-6"><div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Activity size={16} className="text-titan-400" /> Technical Indicators — {symbol}</h3>{loading ? <div className="h-48 animate-pulse bg-white/5 rounded-lg" /> : <div className="space-y-3">{technical.map((item) => <div key={item.label} className="flex items-center justify-between border-b border-white/5 pb-3 last:border-0"><div><div className="text-xs text-gray-500">{item.label}</div><div className="text-sm font-semibold text-white mt-1">{item.value}</div></div>{item.signal && <span className={`text-xs px-2 py-1 rounded-full ${item.positive === true ? "badge-green" : item.positive === false ? "badge-red" : "badge-blue"}`}>{item.signal}</span>}</div>)}</div>}</div>

      <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><BarChart3 size={16} className="text-titan-400" /> Fresh AI Recommendation — {symbol}</h3>{!ai ? <div className="text-sm text-gray-500 py-10 text-center">No AI recommendation available for this script.</div> : <div className="space-y-3"><div className="flex items-center justify-between"><span className={`text-sm font-bold ${signalClass(ai.direction)}`}>{ai.signal.replaceAll("_", " ").toUpperCase()}</span><span className="text-sm text-white">{(ai.confidence * 100).toFixed(1)}% confidence</span></div><div className="grid grid-cols-2 gap-3 text-xs"><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Entry</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.entry_price, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Target</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.price_target, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Stop</span><div className="text-white font-semibold mt-1">{formatCurrency(ai.stop_price, "INR")}</div></div><div className="bg-white/5 rounded-lg p-3"><span className="text-gray-500">Risk/Reward</span><div className="text-white font-semibold mt-1">1:{ai.risk_reward.toFixed(2)}</div></div></div><p className="text-xs text-gray-500">Model score {ai.score.toFixed(1)} · {ai.data_points} real price data points · {ai.holding_period_days} day horizon</p>{ai.no_trade && <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-xs text-yellow-300">NO-TRADE filter active. {ai.rejection_reasons.join(" ")}</div>}{ai.evidence.length > 0 && <div><div className="text-xs font-semibold text-gray-400 mb-2">Evidence</div><ul className="space-y-1">{ai.evidence.slice(0, 6).map((item, i) => <li key={i} className="text-xs text-gray-500">• {item}</li>)}</ul></div>}</div>}</div></div>

      <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4">Fundamental Metrics — {symbol}</h3>{financialEntries.length === 0 ? <p className="text-sm text-gray-500">No verified company fundamental dataset is available for {symbol}. TitanX will not display placeholder P/E, EPS, ROE or margin values.</p> : <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{financialEntries.slice(0, 12).map(([key, value]) => <div key={key} className="bg-white/5 rounded-lg p-3"><div className="text-[11px] text-gray-500 capitalize">{key.replaceAll("_", " ")}</div><div className="text-sm font-semibold text-white mt-1">{typeof value === "number" ? value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : String(value)}</div></div>)}</div>}</div>
      <div className="text-[11px] text-gray-600 pb-4">TitanX displays market data only when returned by the configured market-data source. AI recommendations are model outputs, not guaranteed returns.</div>
    </div>
  )
}
