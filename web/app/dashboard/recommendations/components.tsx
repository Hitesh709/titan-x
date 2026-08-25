"use client"

import { memo } from "react"
import Link from "next/link"
import { Clock, ExternalLink } from "lucide-react"
import type { StockRecommendation } from "@/types"
import { formatPercent } from "@/lib/utils"

interface StrictRecommendation extends StockRecommendation { technical_pillar_score?: number; technical_score?: number; intraday_technical_pillar_score?: number; intraday_technical_score?: number }
interface ParsedMeta { signal?: string; as_of_date?: string; evidence?: string[]; caution?: string[]; returns?: Record<string, number | null>; factors?: Record<string, { score?: number; direction?: number; confidence?: number }> }
interface PillarScore { name: string; score: number; direction: number }

const PILLAR_ORDER = ["technical", "fundamental", "news", "regime", "similarity", "risk"]
const PILLAR_LABELS: Record<string, string> = { technical: "Technical", fundamental: "Fundamental", news: "News", regime: "Regime", similarity: "Pattern", risk: "Risk" }

function parseMeta(rec: StockRecommendation): ParsedMeta { if (!rec.metadata_json) return {}; try { return JSON.parse(rec.metadata_json) as ParsedMeta } catch { return {} } }
function parsePillars(rec: StockRecommendation): PillarScore[] {
  const strict = rec as StrictRecommendation
  const technical = strict.technical_pillar_score ?? strict.technical_score ?? 0
  let factors: ParsedMeta["factors"] = {}
  if (rec.inputs_json) { try { factors = JSON.parse(rec.inputs_json) as ParsedMeta["factors"] } catch { factors = {} } }
  if (!Object.keys(factors ?? {}).length) factors = parseMeta(rec).factors ?? {}
  return PILLAR_ORDER.map((name) => { const raw = factors?.[name]; const score = name === "technical" && technical > 0 ? technical : (typeof raw?.score === "number" ? raw.score : 50); return { name, score, direction: typeof raw?.direction === "number" ? raw.direction : 0 } })
}

export function StatCard({ label, value, tone, icon }: { label: string; value: number; tone: string; icon: React.ReactNode }) { return <div className="glass-card p-4"><div className="flex items-center gap-2 text-gray-500"><span className={tone}>{icon}</span><span className="text-xs">{label}</span></div><div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div></div> }
export function RiskBadge({ risk }: { risk?: string | null }) { const cls = risk === "High" ? "bg-red-500/10 text-red-400" : risk === "Medium" ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"; return <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{risk ?? "—"}</span> }

function RecommendationCardBase({ rec }: { rec: StockRecommendation }) {
  const strictRec = rec as StrictRecommendation
  const meta = parseMeta(rec)
  const pillars = parsePillars(rec)
  const technicalPillar = strictRec.technical_pillar_score ?? strictRec.technical_score ?? pillars.find((p) => p.name === "technical")?.score ?? 0
  const dirCls = rec.direction === "BUY" ? "badge-green" : rec.direction === "SELL" ? "badge-red" : "badge-blue"
  const researchHref = `/dashboard/stocks/${encodeURIComponent(rec.symbol)}`
  const buyHref = `/dashboard/trading?symbol=${encodeURIComponent(rec.symbol)}&side=buy`
  const sellHref = `/dashboard/trading?symbol=${encodeURIComponent(rec.symbol)}&side=sell`

  return <div className="glass-card p-5 flex flex-col">
    <div className="flex items-center justify-between gap-3">
      <Link href={researchHref} className="flex items-center gap-3 group min-w-0 rounded-lg -m-1 p-1 hover:bg-white/[0.03]" aria-label={`Open research for ${rec.symbol}`}>
        <span className="w-9 h-9 rounded-lg bg-titan-600/20 border border-titan-600/30 flex items-center justify-center text-white font-semibold text-xs shrink-0">{rec.symbol.slice(0, 4)}</span>
        <div className="min-w-0"><div className="text-white font-semibold group-hover:text-titan-400 transition-colors">{rec.symbol}</div><div className="text-[11px] text-gray-500">₹{rec.current_price?.toLocaleString("en-IN") ?? "—"}</div></div>
      </Link>
      <div className="flex items-center gap-2 shrink-0">
        <Link href={researchHref} className="inline-flex items-center gap-1 text-[11px] text-titan-400 hover:text-titan-300 px-2.5 py-1.5 rounded-md border border-titan-500/25 hover:border-titan-500/50" aria-label={`Research ${rec.symbol}`}>Research <ExternalLink size={11} /></Link>
        <span className={`badge ${dirCls}`}>{rec.direction}{rec.signal ? ` · ${rec.signal.replaceAll("_", " ")}` : ""}</span>
      </div>
    </div>

    <div className="grid grid-cols-3 gap-3 mt-4">
      <div><div className="text-[11px] text-gray-500 mb-1">Technical Pillar</div><div className="flex items-center gap-2"><div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden"><div className={`h-full rounded-full ${technicalPillar >= 95 ? "bg-emerald-500" : "bg-titan-500"}`} style={{ width: `${Math.min(100, Math.max(0, technicalPillar))}%` }} /></div><span className="text-xs text-gray-200 font-semibold">{Math.round(technicalPillar)}</span></div></div>
      <div><div className="text-[11px] text-gray-500 mb-1">Confidence</div><div className="text-sm font-semibold text-gray-300">{Math.round(rec.confidence ?? 0)}%</div></div>
      <div><div className="text-[11px] text-gray-500 mb-1">Expected return</div><div className={`text-sm font-semibold ${(rec.predicted_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{rec.predicted_return_pct !== null && rec.predicted_return_pct !== undefined ? formatPercent(rec.predicted_return_pct) : "—"}</div></div>
    </div>

    <div className="mt-4"><div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Pillar scores</div><div className="grid grid-cols-2 md:grid-cols-3 gap-2">{pillars.map((p) => <div key={p.name} className="bg-white/[0.03] rounded-lg p-2.5 border border-white/5"><div className="flex items-center justify-between"><span className="text-[11px] text-gray-400">{PILLAR_LABELS[p.name]}</span><span className={`text-[12px] font-semibold ${p.score >= 70 ? "text-emerald-400" : p.score <= 40 ? "text-red-400" : "text-amber-400"}`}>{Math.round(p.score)}</span></div><div className="mt-1.5 h-1 rounded-full bg-white/5 overflow-hidden"><div className={`h-full rounded-full ${p.score >= 70 ? "bg-emerald-500" : p.score <= 40 ? "bg-red-500" : "bg-amber-500"}`} style={{ width: `${Math.min(100, Math.max(0, p.score))}%` }} /></div></div>)}</div></div>

    <div className="flex items-center gap-2 mt-3"><RiskBadge risk={rec.risk_level} />{rec.price_target ? <span className="text-[11px] text-gray-500">Target ₹{rec.price_target.toLocaleString("en-IN")}</span> : null}<span className="ml-auto inline-flex items-center gap-1 text-[11px] text-gray-500"><Clock size={12} />{rec.generated_at ? new Date(rec.generated_at).toLocaleTimeString() : "—"}</span></div>
    <div className="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-titan-800/20"><div><div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">Supporting evidence</div><ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">{(meta.evidence ?? []).slice(0, 3).map((e) => <li key={e}>{e}</li>)}</ul></div><div><div className="text-[11px] font-semibold text-red-400/90 uppercase tracking-wider mb-1.5">Reasons for caution</div><ul className="space-y-1 text-xs text-gray-400 list-disc list-inside">{(meta.caution ?? []).slice(0, 3).map((c) => <li key={c}>{c}</li>)}</ul></div></div>

    <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-white/5"><Link href={buyHref} className="btn-primary text-sm text-center">BUY {rec.symbol}</Link><Link href={sellHref} className="btn-secondary text-sm text-center">SELL {rec.symbol}</Link></div>
  </div>
}

export const RecommendationCard = memo(RecommendationCardBase)
