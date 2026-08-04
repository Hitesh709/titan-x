"use client"

import { Star, Plus, MoreHorizontal, ExternalLink, TrendingUp, TrendingDown } from "lucide-react"
import Link from "next/link"
import { getChangeColor } from "@/lib/utils"

const watchlists = [
  {
    name: "Nifty IT",
    symbols: [
      { symbol: "TCS", price: 2460.00, change: 1.20 },
      { symbol: "INFY", price: 1520.00, change: 2.10 },
      { symbol: "WIPRO", price: 520.00, change: 0.80 },
      { symbol: "HCLTECH", price: 1750.00, change: 1.45 },
    ],
  },
  {
    name: "Banks & Financials",
    symbols: [
      { symbol: "HDFCBANK", price: 1750.00, change: 0.95 },
      { symbol: "ICICIBANK", price: 1250.00, change: -0.65 },
      { symbol: "SBIN", price: 790.00, change: 1.10 },
      { symbol: "AXISBANK", price: 1130.00, change: 0.45 },
    ],
  },
  {
    name: "Energy & Metals",
    symbols: [
      { symbol: "RELIANCE", price: 1300.00, change: -0.90 },
      { symbol: "ONGC", price: 260.00, change: 1.30 },
      { symbol: "TATAMOTORS", price: 1050.00, change: 2.20 },
      { symbol: "JSWSTEEL", price: 950.00, change: 0.70 },
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
                    <Link href={`/dashboard/stocks/${s.symbol}`} className="text-sm font-medium text-white hover:text-titan-400 transition-colors">{s.symbol}</Link>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-white">₹{s.price.toFixed(2)}</span>
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
