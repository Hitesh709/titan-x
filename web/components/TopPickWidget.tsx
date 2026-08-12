"use client"

import { useEffect, useState } from "react"
import {
  TrendingUp, TrendingDown, ShieldCheck, ShieldAlert, Sparkles,
  Bot, Newspaper, BarChart3, Globe, Activity, ChevronDown, ChevronUp,
} from "lucide-react"
import api from "@/lib/api"
import { formatPercent, getChangeColor } from "@/lib/utils"
import type { TopPicksResponse, TopPick, LayerScore } from "@/types"

const LAYER_META: { key: keyof TopPick["layers"]; label: string; icon: typeof Activity }[] = [
  { key: "trend", label: "L1 Trend", icon: TrendingUp },
  { key: "smart_money", label: "L2 Smart Money", icon: Bot },
  { key: "fundamentals", label: "L3 Fundamentals", icon: BarChart3 },
  { key: "news", label: "L4 News & Events", icon: Newspaper },
  { key: "regime", label: "L5 Market Regime", icon: Globe },
  { key: "risk", label: "L6 Risk Filter", icon: ShieldCheck },
]

function scoreColor(score: number) {
  if (score >= 60) return "text-emerald-400"
  if (score <= 40) return "text-red-400"
  return "text-yellow-400"
}

function signalBadge(signal: string, score: number) {
  const cls =
    score >= 60 ? "badge-green" :
    score <= 40 ? "badge-red" :
    "badge-yellow"
  return <span className={cls}>{signal}</span>
}

function LayerRow({ label, icon: Icon, layer }: { label: string; icon: typeof Activity; layer: LayerScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-titan-800/20 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between py-2 text-left"
      >
        <span className="flex items-center gap-2 text-sm text-gray-300">
          <Icon size={14} className="text-titan-400" />
          {label}
        </span>
        <span className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${scoreColor(layer.score)}`}>{layer.score.toFixed(0)}</span>
          {signalBadge(layer.signal, layer.score)}
          {open ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
        </span>
      </button>
      {open && (
        <ul className="pb-2 pl-6 space-y-1">
          {layer.evidence.map((e, i) => (
            <li key={i} className="text-xs text-gray-500 flex gap-1.5">
              <span className="text-titan-500">•</span>
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PickCard({ pick, rank }: { pick: TopPick; rank: number }) {
  const up = pick.change_pct >= 0
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-titan-600/30 border border-titan-500/30 flex items-center justify-center text-titan-300 font-bold">
            {rank}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-base font-semibold text-white">{pick.symbol.replace(".NS", "")}</h4>
              {pick.signal === "strong_buy" && <Sparkles size={14} className="text-emerald-400" />}
            </div>
            <p className="text-xs text-gray-500">{pick.name}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold text-white">₹{pick.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
          <div className={`text-xs font-medium flex items-center justify-end gap-1 ${getChangeColor(pick.change_pct)}`}>
            {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {formatPercent(pick.change_pct)} · 1M {formatPercent(pick.change_1m_pct)}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-titan-600 to-emerald-500"
            style={{ width: `${pick.composite}%` }}
          />
        </div>
        <span className={`text-sm font-bold ${scoreColor(pick.composite)}`}>{pick.composite.toFixed(0)}</span>
      </div>

      <p className="text-xs text-gray-400 mb-3">{pick.summary}</p>

      <div>
        {LAYER_META.map(({ key, label, icon }) => (
          <LayerRow key={key} label={label} icon={icon} layer={pick.layers[key]} />
        ))}
      </div>
    </div>
  )
}

export default function TopPickWidget() {
  const [data, setData] = useState<TopPicksResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<TopPicksResponse>("/top-picks?limit=3")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-titan-400" /> Top Picks
        </h3>
        <div className="space-y-3 animate-pulse">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 bg-white/5 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-titan-400" /> Top Picks
        </h3>
        <div className="flex items-center gap-2 text-sm text-red-400">
          <ShieldAlert size={16} /> Failed to load top picks: {error}
        </div>
      </div>
    )
  }

  if (!data || data.top_picks.length === 0) {
    return (
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-titan-400" /> Top Picks
        </h3>
        <p className="text-sm text-gray-500">
          No scored picks yet. Seed market data to generate the top-pick engine.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Sparkles size={16} className="text-titan-400" /> Top Picks
          <span className="badge-blue text-[10px]">{data.scored} scored</span>
        </h3>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Activity size={13} className="text-titan-400" />
          6-layer evidence · {data.generated_at}
        </div>
      </div>
      {data.top_picks.map((pick, i) => (
        <PickCard key={pick.symbol} pick={pick} rank={i + 1} />
      ))}
    </div>
  )
}