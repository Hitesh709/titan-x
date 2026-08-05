"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  ArrowDown, ArrowUp, BookOpen, Building2, Database, Loader2, Search, TrendingUp, TrendingDown, Minus, CalendarRange,
} from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { ResearchCompany, ResearchCompanyPage } from "@/types"
import { formatCompactNumber, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetError } from "@/components/dashboard/widget"

const PAGE_SIZE = 50

const SORT_OPTIONS: { label: string; sortBy: string; desc: boolean }[] = [
  { label: "Most data days (top) → fewest", sortBy: "days", desc: true },
  { label: "Fewest data days → most", sortBy: "days", desc: false },
  { label: "Symbol (A → Z)", sortBy: "symbol", desc: false },
  { label: "Company name (A → Z)", sortBy: "company_name", desc: false },
  { label: "Score (high → low)", sortBy: "score", desc: true },
  { label: "Confidence (high → low)", sortBy: "confidence", desc: true },
  { label: "Expected return (high → low)", sortBy: "predicted_return_pct", desc: true },
]

export default function ResearchPage() {
  const [items, setItems] = useState<ResearchCompany[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [sortBy, setSortBy] = useState("days")
  const [sortDesc, setSortDesc] = useState(true)
  const mounted = useRef(true)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(
    async (silent = false, append = false) => {
      if (!silent && !append) setLoading(true)
      if (append) setLoadingMore(true)
      try {
        const skip = append ? items.length : 0
        const q = query.trim()
        const res = await api.get<ResearchCompanyPage>(
          `/research/companies?sort_by=${sortBy}&sort_desc=${sortDesc}&limit=${PAGE_SIZE}&skip=${skip}${
            q ? `&search=${encodeURIComponent(q)}` : ""
          }`
        )
        if (!mounted.current) return
        setItems((prev) => (append ? [...prev, ...res.items] : res.items))
        setTotal(res.total ?? 0)
        setError(null)
      } catch (e) {
        if (!mounted.current) return
        if (!append) setError(e instanceof Error ? e.message : "Failed to load research")
      } finally {
        if (mounted.current) {
          setLoading(false)
          setLoadingMore(false)
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sortBy, sortDesc, query],
  )

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true, false), [load])

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => void load(false, false), 300)
  }

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value
    const opt = SORT_OPTIONS.find((o) => o.sortBy === key)
    setSortBy(key)
    setSortDesc(opt ? opt.desc : true)
    void load(false, false)
  }

  const toggleSortDesc = () => {
    setSortDesc((d) => !d)
    void load(false, false)
  }

  const withResearch = items.filter((i) => i.has_research).length
  const buys = items.filter((i) => i.direction === "BUY").length
  const sells = items.filter((i) => i.direction === "SELL").length
  const maxDays = items.reduce((m, i) => Math.max(m, i.days ?? 0), 0)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Company Research</h1>
          <p className="text-gray-500 text-sm mt-1">
            Full NSE universe with live analysis, sorted by how much price history each company has.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Companies" value={total} tone="text-titan-400" icon={<Building2 size={16} />} />
        <StatCard label="With research" value={withResearch} tone="text-emerald-400" icon={<BookOpen size={16} />} />
        <StatCard label="Buy signals" value={buys} tone="text-emerald-400" icon={<TrendingUp size={16} />} />
        <StatCard label="Sell signals" value={sells} tone="text-red-400" icon={<TrendingDown size={16} />} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={query}
            onChange={handleSearchChange}
            placeholder="Search any company by symbol or name (e.g. RELIANCE, TCS, HDFC Bank)…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/5 border border-titan-800/30 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-titan-500/50"
          />
        </div>
        <select
          value={sortBy}
          onChange={handleSortChange}
          className="px-3 py-2 rounded-lg bg-white/5 border border-titan-800/30 text-white text-sm focus:outline-none focus:border-titan-500/50"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.sortBy + (o.desc ? "d" : "a")} value={o.sortBy} className="bg-gray-900">
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={toggleSortDesc}
          title={sortDesc ? "Sorting descending — click for ascending" : "Sorting ascending — click for descending"}
          className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-white/5 border border-titan-800/30 text-gray-300 hover:bg-white/10 transition-colors"
        >
          {sortDesc ? <ArrowDown size={15} /> : <ArrowUp size={15} />}
        </button>
        {maxDays > 0 && (
          <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
            <Database size={13} className="text-titan-400" /> Top company has {maxDays.toLocaleString("en-IN")} data days
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="glass-card h-20 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <WidgetError message={error} onRetry={() => void load(false, false)} />
      ) : items.length === 0 ? (
        <div className="glass-card p-10 text-center">
          <Search size={28} className="mx-auto mb-3 text-gray-600" />
          <p className="text-sm text-gray-400">
            {query.trim()
              ? `No company matches "${query}". Try another name or symbol — the full NSE universe is searchable.`
              : "No companies found. Run a market scan to generate research."}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((c) => (
              <ResearchRow key={c.symbol} company={c} />
            ))}
          </div>
          {items.length < total && (
            <div className="flex justify-center pt-2">
              <button
                onClick={() => void load(true, true)}
                disabled={loadingMore}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white/5 border border-titan-800/30 text-sm text-white hover:bg-white/10 disabled:opacity-50 transition-colors"
              >
                {loadingMore ? <Loader2 size={15} className="animate-spin" /> : <ArrowDown size={15} />}
                Load more ({total - items.length} remaining)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({
  label, value, tone, icon,
}: {
  label: string
  value: number
  tone: string
  icon: React.ReactNode
}) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 text-gray-500">
        <span className={tone}>{icon}</span>
        <span className="text-xs">{label}</span>
      </div>
      <div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div>
    </div>
  )
}

function ResearchRow({ company: c }: { company: ResearchCompany }) {
  const dirCls =
    c.direction === "BUY"
      ? "badge-green"
      : c.direction === "SELL"
        ? "badge-red"
        : "badge-blue"
  const dirIcon =
    c.direction === "BUY" ? <TrendingUp size={12} /> : c.direction === "SELL" ? <TrendingDown size={12} /> : <Minus size={12} />

  return (
    <div className="glass-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-4 min-w-0">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-titan-600/20 to-titan-800/20 border border-titan-700/30 flex items-center justify-center shrink-0">
            <Building2 size={22} className="text-titan-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-semibold text-white truncate">{c.company_name}</h3>
              <Link href={`/dashboard/stocks/${c.symbol}`} className="badge-blue hover:bg-titan-600/30 transition-colors">
                {c.symbol}
              </Link>
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              {c.sector ?? "Equity"}
              {c.industry ? ` · ${c.industry}` : ""}
              {c.market_cap ? ` · MCap ${formatCompactNumber(c.market_cap)}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-titan-600/10 border border-titan-600/25 text-titan-300 text-xs font-medium">
            <CalendarRange size={12} />
            {c.days > 0 ? `${c.days.toLocaleString("en-IN")} data days` : "no price data"}
          </span>
          {c.has_research ? (
            <span className={`inline-flex items-center gap-1 ${dirCls}`}>
              {dirIcon}
              {c.direction}
              {c.signal ? ` · ${c.signal.replaceAll("_", " ")}` : ""}
            </span>
          ) : (
            <span className="badge text-gray-400">No research yet</span>
          )}
        </div>
      </div>

      {c.has_research && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            <div>
              <div className="text-[11px] text-gray-500 mb-1">Score</div>
              <div className="text-sm font-semibold text-white">{c.score != null ? c.score.toFixed(1) : "—"}</div>
            </div>
            <div>
              <div className="text-[11px] text-gray-500 mb-1">Confidence</div>
              <div className="text-sm font-semibold text-white">
                {c.confidence != null ? `${Math.round(c.confidence)}%` : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-gray-500 mb-1">Expected return</div>
              <div className={`text-sm font-semibold ${getChangeColor(c.predicted_return_pct ?? 0)}`}>
                {c.predicted_return_pct != null ? formatPercent(c.predicted_return_pct) : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-gray-500 mb-1">Current · Target</div>
              <div className="text-sm font-semibold text-white">
                {c.current_price != null ? `₹${c.current_price.toLocaleString("en-IN")}` : "—"}
                {c.price_target ? (
                  <span className="text-gray-500 font-normal"> · ₹{c.price_target.toLocaleString("en-IN")}</span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <RiskBadge risk={c.risk_level} />
            {c.timeframe && <span className="text-[11px] text-gray-500">{c.timeframe}</span>}
            <Link
              href={`/dashboard/stocks/${c.symbol}`}
              className="ml-auto text-xs text-titan-400 hover:text-titan-300 inline-flex items-center gap-1"
            >
              View full research →
            </Link>
          </div>
        </>
      )}
      {!c.has_research && (
        <div className="mt-3 flex justify-end">
          <Link
            href={`/dashboard/stocks/${c.symbol}`}
            className="text-xs text-titan-400 hover:text-titan-300 inline-flex items-center gap-1"
          >
            View company page →
          </Link>
        </div>
      )}
    </div>
  )
}

function RiskBadge({ risk }: { risk?: string | null }) {
  if (!risk) return null
  const cls =
    risk === "High"
      ? "bg-red-500/10 text-red-400"
      : risk === "Medium"
        ? "bg-amber-500/10 text-amber-400"
        : "bg-emerald-500/10 text-emerald-400"
  return <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{risk}</span>
}