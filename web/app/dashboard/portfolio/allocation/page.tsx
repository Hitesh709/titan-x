"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Legend } from "recharts"
import { useRouter } from "next/navigation"
import api from "@/lib/api"
import type { PaperPosition } from "@/types"
import { formatCurrency } from "@/lib/utils"
import { WidgetLoading, WidgetError } from "@/components/dashboard/widget"

const COLORS = ["#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa", "#fb923c", "#a3e635"]

export default function PortfolioAllocationPage() {
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)
  const router = useRouter()

  const load = useCallback(async () => {
    try {
      const res = await api.get<PaperPosition[]>("/paper-trading/portfolio")
      if (!mounted.current) return
      setPositions(res)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load allocation")
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    load()
    return () => {
      mounted.current = false
    }
  }, [load])

  const total = positions.reduce((s, p) => s + p.market_value, 0)
  const chartData = positions
    .map((p) => ({ name: p.symbol, value: Number(p.market_value.toFixed(2)) }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="space-y-6">
      {loading ? (
        <WidgetLoading lines={6} />
      ) : error ? (
        <WidgetError message={error} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Allocation pie */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Portfolio Allocation</h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e) => e.name}>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                    labelStyle={{ color: "#9ca3af" }}
                    formatter={(value: number | string, name: string) => [
                      formatCurrency(Number(value)),
                      name,
                    ]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Allocation table */}
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-4 border-b border-titan-800/30">
              <h3 className="text-sm font-semibold text-white">Allocation Breakdown</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-titan-800/30">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Value</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {positions
                    .slice()
                    .sort((a, b) => b.market_value - a.market_value)
                    .map((p, i) => {
                      const weight = total ? (p.market_value / total) * 100 : 0
                      return (
                        <tr key={p.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                              <span className="text-white font-medium">{p.symbol}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4 text-right text-gray-300">{formatCurrency(p.market_value)}</td>
                          <td className="py-3 px-4 text-right">
                            <span className="text-white font-medium">{weight.toFixed(2)}%</span>
                            <div className="mt-1 h-1 rounded-full bg-white/10 overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${weight}%`, background: COLORS[i % COLORS.length] }}
                              />
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
