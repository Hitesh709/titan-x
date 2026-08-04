"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { RefreshCw } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { IndexPerformance, IndexSnapshot, SectorRanking } from "@/types"
import { formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"

const PERIODS = ["1W", "1M", "3M", "6M", "YTD", "1Y"] as const
type Period = (typeof PERIODS)[number]

export default function HistoricalPage() {
  const [indices, setIndices] = useState<IndexSnapshot[]>([])
  const [performance, setPerformance] = useState<Record<string, IndexPerformance>>({})
  const [sectors, setSectors] = useState<SectorRanking[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const idxRes = await api.get<{ items: IndexSnapshot[] }>("/indices")
      if (!mounted.current) return
      const list = idxRes.items ?? []
      setIndices(list)

      const perfMap: Record<string, IndexPerformance> = {}
      const perfResults = await Promise.allSettled(
        list.map((i) => api.get<IndexPerformance>(`/indices/${i.symbol}/performance`))
      )
      list.forEach((i, idx) => {
        if (perfResults[idx].status === "fulfilled") {
          perfMap[i.symbol] = perfResults[idx].value
        }
      })
      setPerformance(perfMap)

      const sectorRes = await api.get<SectorRanking[]>("/sectors/ranking")
      if (mounted.current) setSectors(sectorRes)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load historical performance")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-gray-500 text-sm">Index and sector performance across time horizons</p>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} onRetry={handleRefresh} />
      ) : (
        <>
          {/* Index performance table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">Index Performance</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Index</th>
                    {PERIODS.map((p) => (
                      <th key={p} className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">{p}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {indices.map((idx) => {
                    const perf = performance[idx.symbol]
                    return (
                      <tr key={idx.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                        <td className="py-3 px-4">
                          <span className="text-white font-medium">{idx.name}</span>
                          <span className="ml-2 text-xs text-gray-600">{idx.symbol}</span>
                        </td>
                        {PERIODS.map((p) => {
                          const v = perf?.periods?.[p]
                          return (
                            <td key={p} className={`py-3 px-4 text-right font-medium ${v === null || v === undefined ? "text-gray-600" : getChangeColor(v)}`}>
                              {v === null || v === undefined ? "—" : formatPercent(v)}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Sector performance table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">Sector Performance</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Rank</th>
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Sector</th>
                    {PERIODS.filter((p) => p !== "1W" && p !== "6M" && p !== "YTD").map((p) => (
                      <th key={p} className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">{p}</th>
                    ))}
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">YTD</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((s) => (
                    <tr key={s.sector} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                      <td className="py-3 px-4">
                        <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-white/5 text-xs font-semibold text-gray-300">
                          {s.rank ?? "—"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-white font-medium">{s.sector}</td>
                      {(["1M", "3M", "1Y"] as Period[]).map((p) => {
                        const v = s.periods?.[p]
                        return (
                          <td key={p} className={`py-3 px-4 text-right font-medium ${v === null || v === undefined ? "text-gray-600" : getChangeColor(v)}`}>
                            {v === null || v === undefined ? "—" : formatPercent(v)}
                          </td>
                        )
                      })}
                      <td className={`py-3 px-4 text-right font-medium ${s.ytd_return === null || s.ytd_return === undefined ? "text-gray-600" : getChangeColor(s.ytd_return)}`}>
                        {s.ytd_return === null || s.ytd_return === undefined ? "—" : formatPercent(s.ytd_return)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
