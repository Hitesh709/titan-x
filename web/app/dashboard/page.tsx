"use client"

import {
  TrendingUp, DollarSign, Activity,
  BarChart3, ArrowUpRight, ArrowDownRight,
  LineChart,
} from "lucide-react"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import TopPickWidget from "@/components/TopPickWidget"

const marketIndices = [
  { symbol: "S&P 500", price: 5432.18, change: 1.24, volume: "2.1B" },
  { symbol: "NASDAQ", price: 17123.45, change: 1.87, volume: "3.4B" },
  { symbol: "DOW", price: 38987.23, change: -0.32, volume: "1.8B" },
  { symbol: "RUSSELL", price: 2034.56, change: 0.89, volume: "890M" },
]

const portfolioSummary = {
  totalValue: 2456789.42,
  dayChange: 23456.78,
  dayChangePercent: 0.96,
  totalGain: 456789.12,
  totalGainPercent: 22.84,
  allocation: [
    { label: "Equities", value: 55, color: "bg-titan-500" },
    { label: "Fixed Income", value: 20, color: "bg-emerald-500" },
    { label: "Commodities", value: 10, color: "bg-yellow-500" },
    { label: "Crypto", value: 10, color: "bg-purple-500" },
    { label: "Cash", value: 5, color: "bg-gray-500" },
  ],
}

const recentAlerts = [
  { symbol: "NVDA", type: "Price Target", message: "Hit resistance at $875", time: "2 min ago", severity: "info" },
  { symbol: "TSLA", type: "Volatility", message: "IV spike above 65%", time: "8 min ago", severity: "warning" },
  { symbol: "AAPL", type: "News", message: "Analyst downgrade detected", time: "15 min ago", severity: "negative" },
  { symbol: "MSFT", type: "Earnings", message: "Pre-earnings volume surge", time: "32 min ago", severity: "positive" },
]

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Real-time portfolio and market overview</p>
      </div>

      {/* Portfolio Value Card */}
      <div className="glass-card p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm text-gray-400">Total Portfolio Value</p>
            <h2 className="text-3xl font-bold text-white mt-1">{formatCurrency(portfolioSummary.totalValue)}</h2>
            <div className="flex items-center gap-3 mt-2">
              <span className={`flex items-center gap-1 text-sm font-medium ${getChangeColor(portfolioSummary.dayChange)}`}>
                {portfolioSummary.dayChange >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                {formatCurrency(portfolioSummary.dayChange)} ({formatPercent(portfolioSummary.dayChangePercent)})
              </span>
              <span className="text-gray-600">today</span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-400">Total Return</p>
            <p className={`text-lg font-semibold ${getChangeColor(portfolioSummary.totalGain)}`}>
              {formatPercent(portfolioSummary.totalGainPercent)}
            </p>
          </div>
        </div>

        {/* Allocation */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-400">Asset Allocation</span>
            <span className="text-gray-500">Weight</span>
          </div>
          <div className="flex h-2 rounded-full overflow-hidden bg-white/5">
            {portfolioSummary.allocation.map((item) => (
              <div key={item.label} className={item.color} style={{ width: `${item.value}%` }} title={`${item.label}: ${item.value}%`} />
            ))}
          </div>
          <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-1">
            {portfolioSummary.allocation.map((item) => (
              <span key={item.label} className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${item.color}`} />
                {item.label} {item.value}%
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: DollarSign, label: "Cash Balance", value: "$124,567.89", change: "+2.1%", positive: true },
          { icon: Activity, label: "Today's Volume", value: "1.2M", change: "+12.3%", positive: true },
          { icon: BarChart3, label: "Open Positions", value: "24", change: "3 pending", positive: null },
          { icon: TrendingUp, label: "Win Rate", value: "68.4%", change: "+5.2%", positive: true },
        ].map((stat) => (
          <div key={stat.label} className="glass-card p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-gray-500">{stat.label}</span>
              <stat.icon size={16} className="text-titan-400" />
            </div>
            <div className="text-xl font-bold text-white">{stat.value}</div>
            {stat.change && (
              <div className={`text-xs mt-1 ${stat.positive === true ? "text-emerald-400" : stat.positive === false ? "text-red-400" : "text-gray-500"}`}>
                {stat.change}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Market Indices + Top Movers */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Market Indices */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <LineChart size={16} className="text-titan-400" /> Market Indices
          </h3>
          <div className="space-y-3">
            {marketIndices.map((index) => (
              <div key={index.symbol} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                <div>
                  <div className="text-sm font-medium text-white">{index.symbol}</div>
                  <div className="text-xs text-gray-500">Vol: {index.volume}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium text-white">{index.price.toLocaleString()}</div>
                  <div className={`text-xs font-medium ${getChangeColor(index.change)}`}>
                    {index.change >= 0 ? "+" : ""}{index.change.toFixed(2)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Top Picks */}
        <TopPickWidget />
      </div>

      {/* Alerts */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Activity size={16} className="text-titan-400" /> Recent Activity
        </h3>
        <div className="space-y-3">
          {recentAlerts.map((alert, i) => (
            <div key={i} className="flex items-start gap-3 py-2 border-b border-titan-800/20 last:border-0">
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                alert.severity === "positive" ? "bg-emerald-500" :
                alert.severity === "negative" ? "bg-red-500" :
                alert.severity === "warning" ? "bg-yellow-500" : "bg-titan-500"
              }`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{alert.symbol}</span>
                  <span className="badge-blue text-[10px]">{alert.type}</span>
                </div>
                <p className="text-sm text-gray-400 mt-0.5">{alert.message}</p>
              </div>
              <span className="text-xs text-gray-600 shrink-0">{alert.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
