"use client"

import { Star, Plus, MoreHorizontal, ExternalLink, TrendingUp, TrendingDown } from "lucide-react"
import { getChangeColor } from "@/lib/utils"

const watchlists = [
  {
    name: "AI & Semiconductors",
    symbols: [
      { symbol: "NVDA", price: 874.32, change: 4.56 },
      { symbol: "AMD", price: 156.78, change: 3.21 },
      { symbol: "SMCI", price: 725.45, change: 5.67 },
      { symbol: "INTC", price: 34.23, change: -0.89 },
    ],
  },
  {
    name: "Portfolio Core",
    symbols: [
      { symbol: "MSFT", price: 412.67, change: 2.34 },
      { symbol: "AAPL", price: 187.45, change: -1.23 },
      { symbol: "AMZN", price: 178.23, change: 1.56 },
    ],
  },
  {
    name: "Earnings Watch",
    symbols: [
      { symbol: "TSLA", price: 245.89, change: -3.45 },
      { symbol: "META", price: 498.12, change: 3.21 },
      { symbol: "GOOGL", price: 156.78, change: 0.89 },
      { symbol: "NFLX", price: 634.50, change: 2.78 },
    ],
  },
]

export default function WatchlistsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlists</h1>
          <p className="text-gray-500 text-sm mt-1">Monitor your favorite symbols and custom watchlists</p>
        </div>
        <button className="btn-primary text-sm"><Plus size={14} /> New Watchlist</button>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {watchlists.map((list) => (
          <div key={list.name} className="glass-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Star size={14} className="fill-yellow-500 text-yellow-500" /> {list.name}
              </h3>
              <div className="flex items-center gap-1">
                <button className="btn-ghost text-xs px-2 py-1"><MoreHorizontal size={14} /></button>
              </div>
            </div>
            <div className="space-y-2">
              {list.symbols.map((s) => (
                <div key={s.symbol} className="flex items-center justify-between py-2 px-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{s.symbol}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-white">${s.price.toFixed(2)}</span>
                    <span className={`flex items-center gap-1 text-xs font-medium ${getChangeColor(s.change)}`}>
                      {s.change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {s.change >= 0 ? "+" : ""}{s.change.toFixed(2)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
