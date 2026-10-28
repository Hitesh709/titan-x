"use client"

import { useCallback, useEffect, useState } from "react"
import { RefreshCw, Activity, AlertTriangle } from "lucide-react"
import api from "@/lib/api"

type Contract = {
  symbol: string
  lastPrice: number | null
  priceChangePercent: number | null
  fundingRate: number | null
  openInterest: number | null
  volume24h: number | null
}
type Derivatives = {
  provider: string
  category: string
  contracts: number
  contracts_top: Contract[]
}

const money = (value: number | null | undefined) =>
  value == null || !Number.isFinite(Number(value))
    ? "N/A"
    : Number(value).toLocaleString("en-US", { maximumFractionDigits: 4 })

export default function CryptoDerivatives() {
  const [data, setData] = useState<Derivatives | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<Derivatives>("/crypto-market/derivatives?limit=100")
      setData(result)
      setError("")
      setUpdatedAt(Date.now())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Derivatives unavailable")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = window.setInterval(() => void load(), 15000)
    return () => window.clearInterval(id)
  }, [load])

  const hasLivePrices = Boolean(data?.contracts_top?.some(x => Number(x.lastPrice) > 0))
  const provider = data?.provider?.toUpperCase() || "UNAVAILABLE"
  const dataState = !data ? "UNAVAILABLE" : hasLivePrices ? "PRICE FEED OK" : "NO LIVE PRICES"

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <div className="tx-terminal-badge w-fit">DERIVATIVES ENGINE</div>
          <h1 className="text-3xl font-black mt-3">Futures &amp; Derivatives</h1>
          <p className="text-sm text-slate-500 mt-1">Perpetual contract market data. Fields are only labelled available when the provider returns them.</p>
        </div>
        <button className="btn-primary text-xs" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {error && <div className="glass-card p-4 text-red-300 border border-red-500/30">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="tx-kpi p-4"><span className="tx-kpi-label">CONTRACTS RETURNED</span><b className="tx-kpi-value text-cyan-300">{data?.contracts ?? "—"}</b></div>
        <div className="tx-kpi p-4"><span className="tx-kpi-label">PROVIDER</span><b className="tx-kpi-value text-purple-300">{provider}</b></div>
        <div className="tx-kpi p-4"><span className="tx-kpi-label">PRICE FEED</span><b className={"tx-kpi-value " + (hasLivePrices ? "text-emerald-300" : "text-amber-300")}>{dataState}</b></div>
        <div className="tx-kpi p-4"><span className="tx-kpi-label">LAST SUCCESSFUL REFRESH</span><b className="tx-kpi-value text-blue-300">{updatedAt ? new Date(updatedAt).toLocaleTimeString() : "—"}</b></div>
      </div>

      {data && data.contracts_top.some(x => x.fundingRate == null || x.openInterest == null || Number(x.lastPrice) <= 0) && (
        <div className="glass-card p-3 flex gap-2 items-start text-amber-200 text-xs">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          Some provider fields are unavailable. Missing funding, open interest or prices are shown as N/A rather than being represented as zero or live data.
        </div>
      )}

      <div className="glass-card overflow-hidden">
        <div className="p-4 border-b border-blue-900/30 tx-section-title"><Activity size={16} /> Perpetual Contracts</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] text-xs">
            <thead><tr className="text-slate-600 uppercase">
              <th className="text-left p-4">Contract</th><th className="text-right p-4">Price</th><th className="text-right p-4">24h</th><th className="text-right p-4">Funding</th><th className="text-right p-4">Open Interest</th><th className="text-right p-4">Volume</th>
            </tr></thead>
            <tbody>
              {(data?.contracts_top ?? []).map(x => (
                <tr key={x.symbol} className="border-t border-blue-900/15">
                  <td className="p-4 text-white font-semibold">{x.symbol}</td>
                  <td className="p-4 text-right">{Number(x.lastPrice) > 0 ? "$ " + money(x.lastPrice) : "N/A"}</td>
                  <td className={"p-4 text-right " + (Number(x.priceChangePercent) >= 0 ? "text-emerald-400" : "text-red-400")}>{x.priceChangePercent == null ? "N/A" : Number(x.priceChangePercent).toFixed(2) + "%"}</td>
                  <td className="p-4 text-right text-cyan-300">{x.fundingRate == null ? "N/A" : (Number(x.fundingRate) * 100).toFixed(4) + "%"}</td>
                  <td className="p-4 text-right text-purple-300">{x.openInterest == null || Number(x.openInterest) <= 0 ? "N/A" : "$ " + money(x.openInterest)}</td>
                  <td className="p-4 text-right text-slate-400">{x.volume24h == null ? "N/A" : "$ " + money(x.volume24h)}</td>
                </tr>
              ))}
              {!loading && data?.contracts_top?.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-slate-500">The provider returned no perpetual contracts.</td></tr>}
              {!data && loading && <tr><td colSpan={6} className="p-8 text-center text-slate-500">Connecting to the derivatives provider…</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
