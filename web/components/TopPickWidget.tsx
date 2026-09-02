"use client"

import { useEffect, useState } from "react"
import {
  TrendingUp, TrendingDown, ShieldCheck, ShieldAlert, Sparkles,
  Bot, Newspaper, BarChart3, Globe, Activity, ChevronDown, ChevronUp,
} from "lucide-react"
import api from "@/lib/api"
import { formatPercent, getChangeColor } from "@/lib/utils"
import type { BatchQuotesResponse, TopPicksResponse, TopPick, LayerScore } from "@/types"

const LAYER_META: { key: keyof TopPick["layers"]; label: string; icon: typeof Activity }[] = [
  { key: "trend", label: "L1 Trend", icon: TrendingUp },
  { key: "smart_money", label: "L2 Smart Money", icon: Bot },
  { key: "fundamentals", label: "L3 Fundamentals", icon: BarChart3 },
  { key: "news", label: "L4 News & Events", icon: Newspaper },
  { key: "regime", label: "L5 Market Regime", icon: Globe },
  { key: "risk", label: "L6 Risk Filter", icon: ShieldCheck },
]

function num(value: unknown, fallback = 0): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function safeLayer(value: unknown): LayerScore {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {}
  const evidence = Array.isArray(raw.evidence) ? raw.evidence.map(String) : []
  return {
    score: num(raw.score, 50),
    signal: typeof raw.signal === "string" ? raw.signal : "hold",
    confidence: num(raw.confidence, 0),
    evidence,
    metrics: raw.metrics && typeof raw.metrics === "object" ? raw.metrics as Record<string, number | string | null> : undefined,
    source: typeof raw.source === "string" ? raw.source : undefined,
  }
}

function safePick(value: unknown): TopPick {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {}
  const rawLayers = raw.layers && typeof raw.layers === "object" ? raw.layers as Record<string, unknown> : {}
  return {
    symbol: typeof raw.symbol === "string" ? raw.symbol : "UNKNOWN",
    name: typeof raw.name === "string" ? raw.name : "",
    sector: typeof raw.sector === "string" ? raw.sector : null,
    price: num(raw.price, 0),
    change_pct: num(raw.change_pct, 0),
    change_1m_pct: num(raw.change_1m_pct, 0),
    composite: Math.max(0, Math.min(100, num(raw.composite, 0))),
    signal: typeof raw.signal === "string" ? raw.signal : "hold",
    summary: typeof raw.summary === "string" ? raw.summary : "No summary available.",
    layers: {
      trend: safeLayer(rawLayers.trend),
      smart_money: safeLayer(rawLayers.smart_money),
      fundamentals: safeLayer(rawLayers.fundamentals),
      news: safeLayer(rawLayers.news),
      regime: safeLayer(rawLayers.regime),
      risk: safeLayer(rawLayers.risk),
    },
  }
}

function scoreColor(score: number) {
  if (score >= 60) return "text-emerald-400"
  if (score <= 40) return "text-red-400"
  return "text-yellow-400"
}

function signalBadge(signal: string, score: number) {
  const cls = score >= 60 ? "badge-green" : score <= 40 ? "badge-red" : "badge-yellow"
  return <span className={cls}>{signal}</span>
}

function LayerRow({ label, icon: Icon, layer }: { label: string; icon: typeof Activity; layer: LayerScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-titan-800/20 last:border-0">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full flex items-center justify-between py-2 text-left">
        <span className="flex items-center gap-2 text-sm text-gray-300"><Icon size={14} className="text-titan-400" />{label}</span>
        <span className="flex items-center gap-2"><span className={`text-sm font-semibold ${scoreColor(num(layer.score))}`}>{num(layer.score).toFixed(0)}</span>{signalBadge(String(layer.signal || "hold"), num(layer.score))}{open ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}</span>
      </button>
      {open && <ul className="pb-2 pl-6 space-y-1">{(Array.isArray(layer.evidence) ? layer.evidence : []).map((e, i) => <li key={i} className="text-xs text-gray-500 flex gap-1.5"><span className="text-titan-500">•</span>{String(e)}</li>)}</ul>}
    </div>
  )
}

function PickCard({ pick, rank, liveQuote }: { pick: TopPick; rank: number; liveQuote?: BatchQuotesResponse["quotes"][number] }) {
  const livePrice = liveQuote?.last_price ?? null
  const liveChange = liveQuote?.change_percent ?? null
  const pickChange = num(pick.change_pct)
  const up = num(liveChange ?? pickChange) >= 0
  const composite = num(pick.composite)
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-titan-600/30 border border-titan-500/30 flex items-center justify-center text-titan-300 font-bold">{rank}</div>
          <div><div className="flex items-center gap-2"><h4 className="text-base font-semibold text-white">{pick.symbol.replace(".NS", "")}</h4>{pick.signal === "strong_buy" && <Sparkles size={14} className="text-emerald-400" />}</div><p className="text-xs text-gray-500">{pick.name}</p></div>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold text-white">{livePrice != null ? `₹${num(livePrice).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"}</div>
          <div className={`text-xs font-medium flex items-center justify-end gap-1 ${getChangeColor(num(liveChange ?? pickChange))}`}>{up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}{liveChange != null ? formatPercent(num(liveChange)) : "Live quote unavailable"}</div>
          <div className="text-[10px] text-gray-600">live price</div>
        </div>
      </div>
      <div className="flex items-center gap-2 mb-3"><div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-titan-600 to-emerald-500" style={{ width: `${Math.max(0, Math.min(100, composite))}%` }} /></div><span className={`text-sm font-bold ${scoreColor(composite)}`}>{composite.toFixed(0)}</span></div>
      <p className="text-xs text-gray-400 mb-3">{pick.summary}</p>
      <div>{LAYER_META.map(({ key, label, icon }) => <LayerRow key={key} label={label} icon={icon} layer={safeLayer(pick.layers?.[key])} />)}</div>
    </div>
  )
}

export default function TopPickWidget() {
  const [data, setData] = useState<TopPicksResponse | null>(null)
  const [quotes, setQuotes] = useState<Record<string, BatchQuotesResponse["quotes"][number]>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    api.get<TopPicksResponse>("/top-picks?limit=3")
      .then(async (result) => {
        if (!mounted) return
        const rawPicks = Array.isArray((result as any)?.top_picks) ? (result as any).top_picks : []
        const normalized: TopPicksResponse = {
          generated_at: typeof (result as any)?.generated_at === "string" ? (result as any).generated_at : "",
          universe_size: num((result as any)?.universe_size),
          scored: num((result as any)?.scored),
          layers: Array.isArray((result as any)?.layers) ? (result as any).layers : [],
          top_picks: rawPicks.map(safePick),
        }
        setData(normalized)
        const symbols = normalized.top_picks.map((p) => p.symbol.replace(".NS", "")).filter(Boolean).join(",")
        if (!symbols) return
        try {
          const live = await api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${symbols}`)
          if (!mounted) return
          const map: Record<string, BatchQuotesResponse["quotes"][number]> = {}
          for (const q of live.quotes ?? []) {
            if (q?.symbol) map[String(q.symbol).replace(".NS", "")] = q
          }
          setQuotes(map)
        } catch {
          // Keep the ranking visible if live quotes are temporarily unavailable.
        }
      })
      .catch((e: Error) => { if (mounted) setError(e?.message || "Failed to load top picks") })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [])

  if (loading) return <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Sparkles size={16} className="text-titan-400" /> Top Picks</h3><div className="space-y-3 animate-pulse">{[0, 1, 2].map((i) => <div key={i} className="h-16 bg-white/5 rounded-lg" />)}</div></div>
  if (error) return <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Sparkles size={16} className="text-titan-400" /> Top Picks</h3><div className="flex items-center gap-2 text-sm text-red-400"><ShieldAlert size={16} /> Failed to load top picks: {error}</div></div>
  if (!data || data.top_picks.length === 0) return <div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Sparkles size={16} className="text-titan-400" /> Top Picks</h3><p className="text-sm text-gray-500">No scored picks yet. Run a real market-data scan to generate the top-pick engine.</p></div>

  return <div className="space-y-4"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-white flex items-center gap-2"><Sparkles size={16} className="text-titan-400" /> Top Picks <span className="badge-blue text-[10px]">{data.scored} scored</span></h3><div className="flex items-center gap-2 text-xs text-gray-500"><Activity size={13} className="text-titan-400" />6-layer evidence · {data.generated_at}</div></div>{data.top_picks.map((pick, i) => <PickCard key={`${pick.symbol}-${i}`} pick={pick} rank={i + 1} liveQuote={quotes[pick.symbol.replace(".NS", "")]}/>)}</div>
}
