"use client"

import { useCallback, useRef, useState } from "react"
import { Search, Brain, TrendingUp, TrendingDown, Minus, AlertTriangle, ShieldCheck } from "lucide-react"
import api from "@/lib/api"
import { formatPercent } from "@/lib/utils"

interface Pillar {
  name: string
  weight: number
  score: number
  direction: number
  confidence: number
  detail: Record<string, unknown>
}

interface Explainability {
  symbol: string
  signal: string
  conviction: string
  direction: string
  score: number
  calibrated_probability: number
  entry: number
  target: number
  stop: number
  risk_reward: number
  min_required_rr: number
  model_agreement: string
  confident_pillars: number
  agreement_ratio: number
  data_quality: number
  missing_pillars: string[]
  no_trade: boolean
  rejection_reasons: string[]
  pillars: Pillar[]
  historical_evidence: Record<string, number | null>
  reasons: string[]
  risks: string[]
  disclaimer: string
}

interface AnalysisResult {
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
    as_of_date: string | null
    data_points: number
  }
  explainability: Explainability
}

const PILLAR_LABELS: Record<string, string> = {
  technical: "Technical",
  fundamental: "Fundamental",
  news: "News & Sentiment",
  regime: "Market Regime",
  similarity: "Historical Pattern",
  risk: "Risk Engine",
}

function dirIcon(direction: number) {
  if (direction > 0) return <TrendingUp size={13} className="text-emerald-400" />
  if (direction < 0) return <TrendingDown size={13} className="text-red-400" />
  return <Minus size={13} className="text-gray-400" />
}

function dirTone(value: number | string | null | undefined): string {
  if (value === "BUY" || value === "buy" || value === "strong_buy" || (typeof value === "number" && value > 0))
    return "text-emerald-400"
  if (value === "SELL" || value === "sell" || value === "strong_sell" || (typeof value === "number" && value < 0))
    return "text-red-400"
  return "text-gray-400"
}

export function SymbolAnalyzer() {
  const [symbol, setSymbol] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const mounted = useRef(true)

  const runAnalysis = useCallback(async () => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<AnalysisResult>(`/recommendations/analyze/${sym}`)
      if (mounted.current) setResult(res)
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : "Analysis failed")
        setResult(null)
      }
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [symbol])

  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={18} className="text-titan-400" />
        <h2 className="text-white font-semibold">AI Symbol Analyzer</h2>
        <span className="text-[11px] text-gray-500 ml-auto">6-pillar selective engine</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
            placeholder="Enter symbol (e.g. INFY)"
            className="input-field w-full text-sm pl-9 uppercase"
            aria-label="Symbol to analyze"
          />
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading || !symbol.trim()}
          className="btn-primary text-sm inline-flex items-center gap-2 disabled:opacity-50"
        >
          {loading ? <Search size={14} className="animate-spin" /> : <Brain size={14} />}
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </div>

      {error && (
        <div className="mt-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded p-3">
          {error}
        </div>
      )}

      {result && !error && (
        <div className="mt-5 space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="w-10 h-10 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-sm">
                {result.symbol.slice(0, 4)}
              </span>
              <div>
                <div className="text-white font-semibold">{result.symbol}</div>
                <div className="text-[11px] text-gray-500">
                  {result.recommendation.as_of_date
                    ? new Date(result.recommendation.as_of_date).toLocaleDateString()
                    : "—"}{" "}
                  · {result.recommendation.data_points} data points
                </div>
              </div>
            </div>

            <div className="ml-auto flex items-center gap-2">
              {result.recommendation.no_trade ? (
                <span className="badge badge-blue">NO-TRADE</span>
              ) : (
                <span
                  className={`badge ${
                    result.recommendation.direction === "BUY" ? "badge-green" : "badge-red"
                  }`}
                >
                  {result.recommendation.direction} · {result.recommendation.conviction}
                </span>
              )}
              <RiskBadge risk={result.recommendation.risk_level} />
            </div>
          </div>

          {result.recommendation.no_trade && (
            <div className="flex items-start gap-2 text-sm text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded p-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">No actionable signal — engine prefers to wait.</div>
                <div className="text-amber-200/80 text-xs mt-1">
                  {result.recommendation.rejection_reasons.join(", ")}
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Metric label="Conviction score" value={result.recommendation.score.toFixed(1)} />
            <Metric
              label="Win probability"
              value={formatPercent(result.recommendation.calibrated_probability * 100)}
              tone={dirTone(result.recommendation.calibrated_probability >= 0.6 ? 1 : -1)}
            />
            <Metric label="Entry" value={`₹${result.recommendation.entry_price.toLocaleString("en-IN")}`} />
            <Metric
              label="Target / Stop"
              value={`₹${result.recommendation.price_target.toLocaleString("en-IN")} / ₹${result.recommendation.stop_price.toLocaleString("en-IN")}`}
            />
            <Metric label="Risk : Reward" value={`1 : ${result.recommendation.risk_reward.toFixed(2)}`} />
            <Metric label="Expected return" value={formatPercent(result.recommendation.expected_return_pct)} tone={dirTone(result.recommendation.expected_return_pct)} />
            <Metric label="Holding period" value={`${result.recommendation.holding_period_days} days`} />
            <Metric label="Model agreement" value={result.explainability.model_agreement} />
          </div>

          <div>
            <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Pillar breakdown
            </div>
            <div className="space-y-2">
              {result.explainability.pillars.map((p) => (
                <div key={p.name} className="flex items-center gap-3">
                  <div className="w-32 shrink-0 flex items-center gap-1.5 text-xs text-gray-300">
                    {dirIcon(p.direction)}
                    {PILLAR_LABELS[p.name] ?? p.name}
                  </div>
                  <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        p.score >= 55 ? "bg-emerald-500" : p.score <= 45 ? "bg-red-500" : "bg-yellow-500"
                      }`}
                      style={{ width: `${Math.min(100, p.score)}%` }}
                    />
                  </div>
                  <div className="w-10 text-right text-xs text-gray-400 tabular-nums">{p.score.toFixed(0)}</div>
                  <div className="w-12 text-right text-[11px] text-gray-500 tabular-nums">
                    {(p.confidence * 100).toFixed(0)}% c
                  </div>
                </div>
              ))}
            </div>
          </div>

          {(result.explainability.reasons.length > 0 || result.explainability.risks.length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">
                  Supporting evidence
                </div>
                <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
                  {result.explainability.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-red-400/90 uppercase tracking-wider mb-1.5">
                  Reasons for caution
                </div>
                <ul className="space-y-1 text-xs text-gray-400 list-disc list-inside">
                  {result.explainability.risks.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <div className="flex items-start gap-2 text-[11px] text-gray-500 border-t border-titan-800/20 pt-3">
            <ShieldCheck size={14} className="mt-0.5 shrink-0 text-titan-500/60" />
            <span>{result.explainability.disclaimer}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, tone = "text-white" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="bg-white/[0.03] rounded-lg p-3">
      <div className="text-[11px] text-gray-500 mb-1">{label}</div>
      <div className={`text-sm font-semibold ${tone}`}>{value}</div>
    </div>
  )
}

function RiskBadge({ risk }: { risk?: string | null }) {
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
