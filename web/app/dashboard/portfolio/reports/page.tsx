"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Download, FileSpreadsheet, FileText, RefreshCw, CalendarRange } from "lucide-react"
import api from "@/lib/api"
import type { PaginatedResponse, PaperPosition, PaperTradeRow } from "@/types"
import { formatCurrency, formatDate, getChangeColor } from "@/lib/utils"
import { WidgetError, WidgetLoading } from "@/components/dashboard/widget"

const PAGE_SIZE = 100

type ReportType = "trading" | "pnl" | "portfolio"

type ReportRow = Record<string, string | number>

function isoDate(d: Date) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

export default function PortfolioReportsPage() {
  const today = isoDate(new Date())
  const first = new Date()
  first.setDate(1)
  const [from, setFrom] = useState(isoDate(first))
  const [to, setTo] = useState(today)
  const [type, setType] = useState<ReportType>("trading")
  const [trades, setTrades] = useState<PaperTradeRow[]>([])
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (from > to) {
      setError("From date must be before or equal to To date")
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [portfolio, firstPage] = await Promise.all([
        api.get<PaperPosition[]>("/paper-trading/portfolio"),
        api.get<PaginatedResponse<PaperTradeRow>>(`/paper-trading/trades?skip=0&limit=${PAGE_SIZE}`),
      ])
      const all = [...firstPage.items]
      for (let skip = PAGE_SIZE; skip < firstPage.total; skip += PAGE_SIZE) {
        const page = await api.get<PaginatedResponse<PaperTradeRow>>(`/paper-trading/trades?skip=${skip}&limit=${PAGE_SIZE}`)
        all.push(...page.items)
        if (!page.items.length) break
      }
      setPositions(portfolio)
      setTrades(all.filter((t) => {
        if (!t.trade_time) return false
        const day = new Date(t.trade_time).toISOString().slice(0, 10)
        return day >= from && day <= to
      }))
      setLoaded(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to build report")
    } finally {
      setLoading(false)
    }
  }, [from, to])

  useEffect(() => {
    void load()
  }, [load])

  const pnl = useMemo(() => trades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0), [trades])
  const commissions = useMemo(() => trades.reduce((sum, t) => sum + (t.commission ?? 0), 0), [trades])
  const buys = trades.filter((t) => t.side === "buy").length
  const sells = trades.filter((t) => t.side === "sell").length

  const rows: ReportRow[] = useMemo(() => {
    if (type === "portfolio") {
      return positions.map((p) => ({
        Symbol: p.symbol,
        Sector: p.sector ?? "",
        "Cost Basis": p.cost_basis,
        "Market Value": p.market_value,
        "Unrealized PnL": p.unrealized_pnl,
        "Unrealized %": p.unrealized_pnl_pct,
        "Realized PnL": p.realized_pnl,
        "Total PnL": p.realized_pnl + p.unrealized_pnl,
      }))
    }
    if (type === "pnl") {
      const bySymbol = new Map<string, number>()
      for (const t of trades) bySymbol.set(t.symbol, (bySymbol.get(t.symbol) ?? 0) + (t.realized_pnl ?? 0))
      return [...bySymbol.entries()].sort((a, b) => b[1] - a[1]).map(([symbol, value]) => ({ Symbol: symbol, "Realized PnL": value }))
    }
    return trades.map((t) => ({
      Date: t.trade_time ? formatDate(t.trade_time) : "",
      Symbol: t.symbol,
      Side: t.side.toUpperCase(),
      Quantity: t.quantity,
      Price: t.price,
      Commission: t.commission,
      "Realized PnL": t.realized_pnl ?? 0,
    }))
  }, [positions, trades, type])

  const title = type === "trading" ? "Daily Trading Report" : type === "pnl" ? "P&L Report" : "Portfolio Report"

  const download = (kind: "csv" | "xls") => {
    const headers = rows.length ? Object.keys(rows[0]) : ["Message"]
    const data = rows.length ? rows : [{ Message: "No records for selected date range" }]
    if (kind === "csv") {
      const esc = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`
      const csv = [headers.map(esc).join(","), ...data.map((r) => headers.map((h) => esc(r[h])).join(","))].join("\n")
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
      saveBlob(blob, `titan-x-${type}-${from}-to-${to}.csv`)
      return
    }
    const html = `<html><head><meta charset="utf-8"></head><body><h2>${title}</h2><p>${from} to ${to}</p><table border="1"><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr>${data.map((r) => `<tr>${headers.map((h) => `<td>${String(r[h] ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")}</td>`).join("")}</tr>`).join("")}</table></body></html>`
    saveBlob(new Blob([html], { type: "application/vnd.ms-excel" }), `titan-x-${type}-${from}-to-${to}.xls`)
  }

  const printPdf = () => window.print()

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 print:hidden">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-white">Trading Reports & Export</h2>
            <p className="text-xs text-gray-500 mt-1">Select a date range and export daily trading, P&amp;L or portfolio data.</p>
          </div>
          <button onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-titan-600/20 text-titan-300 border border-titan-500/30 text-sm disabled:opacity-50">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh report
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-5">
          <label className="text-xs text-gray-500">Report type<select value={type} onChange={(e) => setType(e.target.value as ReportType)} className="mt-1 w-full rounded-lg bg-black/20 border border-white/10 text-gray-200 px-3 py-2 text-sm"><option value="trading">Daily Trading</option><option value="pnl">P&amp;L</option><option value="portfolio">Portfolio</option></select></label>
          <label className="text-xs text-gray-500">From date<div className="mt-1 relative"><CalendarRange size={15} className="absolute left-3 top-2.5 text-gray-500" /><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-full rounded-lg bg-black/20 border border-white/10 text-gray-200 pl-9 pr-3 py-2 text-sm" /></div></label>
          <label className="text-xs text-gray-500">To date<div className="mt-1 relative"><CalendarRange size={15} className="absolute left-3 top-2.5 text-gray-500" /><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-full rounded-lg bg-black/20 border border-white/10 text-gray-200 pl-9 pr-3 py-2 text-sm" /></div></label>
          <div className="flex items-end gap-2"><button onClick={() => download("csv")} disabled={!loaded || loading} className="flex-1 inline-flex justify-center items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-gray-300 text-sm disabled:opacity-40"><Download size={14} /> CSV</button><button onClick={() => download("xls")} disabled={!loaded || loading} className="flex-1 inline-flex justify-center items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-gray-300 text-sm disabled:opacity-40"><FileSpreadsheet size={14} /> XLS</button><button onClick={printPdf} disabled={!loaded || loading} className="flex-1 inline-flex justify-center items-center gap-1.5 px-3 py-2 rounded-lg bg-titan-600 text-white text-sm disabled:opacity-40"><FileText size={14} /> PDF</button></div>
        </div>
      </div>

      {loading ? <WidgetLoading lines={6} /> : error ? <WidgetError message={error} /> : loaded ? (
        <div className="space-y-4 print-report">
          <div className="hidden print:block mb-4"><h1 className="text-2xl font-bold">Titan X — {title}</h1><p>{from} to {to}</p></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="Records" value={rows.length.toLocaleString()} />
            <Metric label="Realized P&L" value={formatCurrency(pnl)} tone={getChangeColor(pnl)} />
            <Metric label="Commissions" value={formatCurrency(commissions)} />
            <Metric label="Buy / Sell" value={`${buys} / ${sells}`} />
          </div>
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30"><h3 className="text-sm font-semibold text-white">{title} · {from} → {to}</h3></div>
            <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{(rows.length ? Object.keys(rows[0]) : ["Message"]).map((h) => <th key={h} className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">{h}</th>)}</tr></thead><tbody>{rows.length ? rows.map((r, i) => <tr key={i} className="border-b border-titan-800/20">{Object.keys(rows[0]).map((h) => <td key={h} className={`py-3 px-4 text-gray-300 ${h.toLowerCase().includes("pnl") ? getChangeColor(Number(r[h]) || 0) : ""}`}>{typeof r[h] === "number" ? r[h].toLocaleString(undefined, { maximumFractionDigits: 2 }) : r[h]}</td>)}</tr>) : <tr><td className="py-8 px-4 text-center text-gray-500">No records for selected date range.</td></tr>}</tbody></table></div>
          </div>
          {type === "pnl" && <p className="text-xs text-gray-500">P&amp;L report uses realized P&amp;L from trades executed inside the selected date range. Current unrealized P&amp;L is available in the Portfolio report.</p>}
          <p className="text-xs text-gray-600 print:hidden">PDF uses your browser's print dialog — choose “Save as PDF”.</p>
        </div>
      ) : null}
    </div>
  )
}

function Metric({ label, value, tone = "text-white" }: { label: string; value: string; tone?: string }) {
  return <div className="glass-card p-4"><p className="text-xs text-gray-500">{label}</p><p className={`mt-1 text-lg font-bold ${tone}`}>{value}</p></div>
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
