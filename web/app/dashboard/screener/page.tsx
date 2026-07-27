"use client"

import { Target, Filter, Search, Save, TrendingUp, TrendingDown } from "lucide-react"
import { getChangeColor } from "@/lib/utils"

const screeners = [
  { name: "High Momentum", criteria: "RSI > 70, Volume > 2M, Price > $20", results: 34, lastRun: "2h ago" },
  { name: "Undervalued Growth", criteria: "P/E < 20, EPS Growth > 15%, PEG < 1.5", results: 22, lastRun: "4h ago" },
  { name: "Breakout Candidates", criteria: "Price > SMA20, Volume Spike > 50%, RSI 50-65", results: 18, lastRun: "1h ago" },
]

const screenerResults = [
  { symbol: "NVDA", price: 874.32, change: 4.56, volume: "45.2M", rsi: 72, volumeRatio: 2.1, marketCap: "2.15T" },
  { symbol: "AMD", price: 156.78, change: 3.21, volume: "28.9M", rsi: 68, volumeRatio: 1.8, marketCap: "253.4B" },
  { symbol: "SMCI", price: 725.45, change: 5.67, volume: "12.3M", rsi: 75, volumeRatio: 2.5, marketCap: "42.1B" },
  { symbol: "ARM", price: 134.23, change: 2.89, volume: "8.7M", rsi: 65, volumeRatio: 1.4, marketCap: "138.2B" },
  { symbol: "MRVL", price: 68.45, change: 1.34, volume: "6.2M", rsi: 62, volumeRatio: 1.2, marketCap: "59.3B" },
  { symbol: "MU", price: 128.90, change: -0.45, volume: "15.6M", rsi: 55, volumeRatio: 0.9, marketCap: "142.8B" },
]

export default function ScreenerPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Stock Screener</h1>
          <p className="text-gray-500 text-sm mt-1">Screen thousands of stocks using custom criteria</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary text-sm"><Save size={14} /> Save Screen</button>
          <button className="btn-primary text-sm"><Search size={14} /> Run Screen</button>
        </div>
      </div>

      {/* Saved Screeners */}
      <div className="grid md:grid-cols-3 gap-4">
        {screeners.map((s) => (
          <div key={s.name} className="glass-card p-4 hover:border-titan-600/40 cursor-pointer transition-all">
            <div className="flex items-start justify-between mb-2">
              <h3 className="text-sm font-medium text-white">{s.name}</h3>
              <span className="text-xs text-gray-500">{s.results} results</span>
            </div>
            <p className="text-xs text-gray-500 line-clamp-2">{s.criteria}</p>
            <div className="text-[10px] text-gray-600 mt-2">Last run: {s.lastRun}</div>
          </div>
        ))}
      </div>

      {/* Filter Builder (simplified) */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Filter size={16} className="text-titan-400" /> Filter Criteria
        </h3>
        <div className="flex flex-wrap gap-3">
          {[
            { label: "Market Cap", value: "> $10B" },
            { label: "RSI (14)", value: "> 60" },
            { label: "Volume", value: "> 2M" },
            { label: "Price", value: "> $20" },
            { label: "Sector", value: "Technology" },
          ].map((f) => (
            <div key={f.label} className="flex items-center gap-2 px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-xs">
              <span className="text-gray-400">{f.label}:</span>
              <span className="text-white">{f.value}</span>
              <button className="text-gray-600 hover:text-red-400 ml-1">&times;</button>
            </div>
          ))}
          <button className="flex items-center gap-1 px-3 py-1.5 border border-dashed border-white/10 rounded-lg text-xs text-gray-500 hover:text-gray-300">
            + Add Filter
          </button>
        </div>
      </div>

      {/* Results */}
      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-titan-800/30 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Results</h3>
          <span className="text-xs text-gray-500">{screenerResults.length} matches</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30">
                <th className="text-left py-3 px-4 text-gray-500 text-xs uppercase">Symbol</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">Price</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">Change</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">Volume</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">RSI (14)</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">Vol Ratio</th>
                <th className="text-right py-3 px-4 text-gray-500 text-xs uppercase">Market Cap</th>
              </tr>
            </thead>
            <tbody>
              {screenerResults.map((s) => (
                <tr key={s.symbol} className="border-b border-titan-800/20 hover:bg-white/5">
                  <td className="py-3 px-4">
                    <span className="text-white font-medium">{s.symbol}</span>
                  </td>
                  <td className="py-3 px-4 text-right text-white">${s.price.toFixed(2)}</td>
                  <td className={`py-3 px-4 text-right font-medium ${getChangeColor(s.change)}`}>
                    <div className="flex items-center justify-end gap-1">
                      {s.change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {s.change >= 0 ? "+" : ""}{s.change.toFixed(2)}%
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right text-gray-400">{s.volume}</td>
                  <td className={`py-3 px-4 text-right font-medium ${s.rsi > 70 ? "text-red-400" : s.rsi < 30 ? "text-emerald-400" : "text-white"}`}>{s.rsi}</td>
                  <td className={`py-3 px-4 text-right font-medium ${s.volumeRatio > 1.5 ? "text-emerald-400" : "text-gray-400"}`}>{s.volumeRatio.toFixed(1)}x</td>
                  <td className="py-3 px-4 text-right text-gray-400">{s.marketCap}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
