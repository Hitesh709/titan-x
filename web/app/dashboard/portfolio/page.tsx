"use client"

import { useState } from "react"
import { TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Plus, PieChart } from "lucide-react"
import { formatCurrency, formatPercent, getChangeColor, formatCompactNumber } from "@/lib/utils"

const holdings = [
  { symbol: "NVDA", name: "NVIDIA Corp", shares: 1250, avgPrice: 642.15, currentPrice: 874.32, sector: "Technology", weight: 18.5 },
  { symbol: "MSFT", name: "Microsoft Corp", shares: 2100, avgPrice: 345.80, currentPrice: 412.67, sector: "Technology", weight: 14.2 },
  { symbol: "AAPL", name: "Apple Inc", shares: 3200, avgPrice: 172.30, currentPrice: 187.45, sector: "Technology", weight: 9.8 },
  { symbol: "AMZN", name: "Amazon.com", shares: 1500, avgPrice: 152.45, currentPrice: 178.23, sector: "Consumer Cyclical", weight: 4.4 },
  { symbol: "GOOGL", name: "Alphabet Inc", shares: 1800, avgPrice: 138.90, currentPrice: 156.78, sector: "Technology", weight: 4.6 },
  { symbol: "TSLA", name: "Tesla Inc", shares: 800, avgPrice: 268.50, currentPrice: 245.89, sector: "Automotive", weight: -3.2 },
  { symbol: "JPM", name: "JPMorgan Chase", shares: 2800, avgPrice: 182.30, currentPrice: 198.45, sector: "Financial", weight: 9.1 },
  { symbol: "V", name: "Visa Inc", shares: 1500, avgPrice: 245.60, currentPrice: 275.34, sector: "Financial", weight: 6.8 },
]

const riskMetrics = [
  { label: "Beta (1Y)", value: "1.12", status: "neutral" as const },
  { label: "Sharpe Ratio", value: "1.84", status: "positive" as const },
  { label: "Volatility (30d)", value: "18.4%", status: "warning" as const },
  { label: "VaR (95%)", value: "-2.3%", status: "neutral" as const },
  { label: "Max Drawdown", value: "-8.7%", status: "warning" as const },
  { label: "Alpha", value: "3.42%", status: "positive" as const },
]

export default function PortfolioPage() {
  const [positionSize, setPositionSize] = useState<"all" | "long" | "short">("all")

  const totalValue = holdings.reduce((sum, h) => sum + (h.shares * h.currentPrice), 0)
  const totalCost = holdings.reduce((sum, h) => sum + (h.shares * h.avgPrice), 0)
  const totalGain = totalValue - totalCost
  const totalGainPercent = (totalGain / totalCost) * 100

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio</h1>
        <p className="text-gray-500 text-sm mt-1">Manage and monitor your investment portfolio</p>
      </div>

      {/* Summary */}
      <div className="grid md:grid-cols-3 gap-4">
        <div className="glass-card p-5">
          <p className="text-sm text-gray-400 mb-1">Total Value</p>
          <h2 className="text-2xl font-bold text-white">{formatCurrency(totalValue)}</h2>
          <div className={`flex items-center gap-1 text-sm mt-1 ${getChangeColor(totalGain)}`}>
            {totalGain >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
            {formatCurrency(totalGain)} ({formatPercent(totalGainPercent)})
          </div>
        </div>
        <div className="glass-card p-5">
          <p className="text-sm text-gray-400 mb-1">Cost Basis</p>
          <h2 className="text-2xl font-bold text-white">{formatCurrency(totalCost)}</h2>
          <p className="text-sm text-gray-500 mt-1">{holdings.length} positions across 4 sectors</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-sm text-gray-400 mb-1">Cash Balance</p>
          <h2 className="text-2xl font-bold text-white">{formatCurrency(124567.89)}</h2>
          <p className="text-sm text-gray-500 mt-1">Available for trading</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Holdings */}
        <div className="lg:col-span-2 glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Positions</h3>
            <div className="flex gap-1">
              {(["all", "long", "short"] as const).map((size) => (
                <button key={size} onClick={() => setPositionSize(size)} className={`px-3 py-1 rounded text-xs font-medium capitalize ${
                  positionSize === size ? "bg-titan-600/20 text-titan-400 border border-titan-600/30" : "text-gray-500 hover:text-gray-300"
                }`}>{size}</button>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            {holdings.map((h) => {
              const gainLoss = (h.currentPrice - h.avgPrice) * h.shares
              const gainLossPercent = ((h.currentPrice - h.avgPrice) / h.avgPrice) * 100
              return (
                <div key={h.symbol} className="flex items-center justify-between py-2.5 border-b border-titan-800/20 last:border-0">
                  <div className="flex items-center gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">{h.symbol}</div>
                      <div className="text-xs text-gray-500">{h.shares} shares</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className="text-sm text-white">${h.currentPrice.toFixed(2)}</div>
                      <div className="text-xs text-gray-500">Avg: ${h.avgPrice.toFixed(2)}</div>
                    </div>
                    <div className="text-right w-28">
                      <div className="text-sm text-white">{formatCurrency(h.shares * h.currentPrice)}</div>
                      <div className={`text-xs font-medium ${getChangeColor(gainLoss)}`}>
                        {gainLoss >= 0 ? "+" : ""}{formatCurrency(gainLoss)} ({formatPercent(gainLossPercent)})
                      </div>
                    </div>
                    <div className="text-right w-16">
                      <span className="text-xs text-gray-400">{h.weight.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Side panel */}
        <div className="space-y-4">
          {/* Risk Metrics */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Risk Metrics</h3>
            <div className="space-y-3">
              {riskMetrics.map((metric) => (
                <div key={metric.label} className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">{metric.label}</span>
                  <span className={`text-sm font-medium ${
                    metric.status === "positive" ? "text-emerald-400" :
                    metric.status === "warning" ? "text-yellow-400" : "text-white"
                  }`}>{metric.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Sector Allocation */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Sector Allocation</h3>
            <div className="space-y-3">
              {["Technology", "Financial", "Consumer Cyclical", "Automotive"].map((sector) => {
                const sectorHoldings = holdings.filter(h => h.sector === sector)
                const sectorValue = sectorHoldings.reduce((sum, h) => sum + (h.shares * h.currentPrice), 0)
                const sectorWeight = (sectorValue / totalValue) * 100
                return (
                  <div key={sector}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-gray-400">{sector}</span>
                      <span className="text-white">{sectorWeight.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                      <div className="h-full rounded-full bg-titan-500" style={{ width: `${sectorWeight}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
