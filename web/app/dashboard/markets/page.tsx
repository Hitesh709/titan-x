"use client"

import { TrendingUp, TrendingDown, Search, Filter, Star } from "lucide-react"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"

const marketData = [
  { symbol: "NVDA", name: "NVIDIA Corp", price: 874.32, change: 4.56, volume: "45.2M", marketCap: "2.15T", sector: "Technology" },
  { symbol: "AAPL", name: "Apple Inc", price: 187.45, change: -1.23, volume: "62.1M", marketCap: "2.89T", sector: "Technology" },
  { symbol: "MSFT", name: "Microsoft Corp", price: 412.67, change: 2.34, volume: "28.7M", marketCap: "3.07T", sector: "Technology" },
  { symbol: "TSLA", name: "Tesla Inc", price: 245.89, change: -3.45, volume: "89.3M", marketCap: "782.4B", sector: "Automotive" },
  { symbol: "AMZN", name: "Amazon.com", price: 178.23, change: 1.56, volume: "35.6M", marketCap: "1.85T", sector: "Consumer Cyclical" },
  { symbol: "GOOGL", name: "Alphabet Inc", price: 156.78, change: 0.89, volume: "22.4M", marketCap: "1.97T", sector: "Technology" },
  { symbol: "META", name: "Meta Platforms", price: 498.12, change: 3.21, volume: "18.9M", marketCap: "1.27T", sector: "Technology" },
  { symbol: "JPM", name: "JPMorgan Chase", price: 198.45, change: -0.67, volume: "8.4M", marketCap: "572.1B", sector: "Financial" },
  { symbol: "V", name: "Visa Inc", price: 275.34, change: 1.12, volume: "12.3M", marketCap: "565.8B", sector: "Financial" },
  { symbol: "JNJ", name: "Johnson & Johnson", price: 156.23, change: -0.45, volume: "6.7M", marketCap: "376.2B", sector: "Healthcare" },
  { symbol: "WMT", name: "Walmart Inc", price: 172.89, change: 0.78, volume: "9.8M", marketCap: "465.3B", sector: "Consumer Defensive" },
  { symbol: "PG", name: "Procter & Gamble", price: 167.45, change: -0.23, volume:  "5.6M", marketCap: "394.1B", sector: "Consumer Defensive" },
]

const sectors = ["All", "Technology", "Financial", "Healthcare", "Automotive", "Consumer Cyclical", "Consumer Defensive"]

export default function MarketsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Markets</h1>
          <p className="text-gray-500 text-sm mt-1">Real-time market data across all asset classes</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input type="text" placeholder="Search symbols..." className="pl-9 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-titan-500 w-48" />
          </div>
          <button className="btn-secondary text-sm"><Filter size={14} /> Filters</button>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {sectors.map((s) => (
          <button key={s} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            s === "All" ? "bg-titan-600/20 text-titan-400 border border-titan-600/30" : "bg-white/5 text-gray-400 hover:text-gray-200 border border-white/10"
          }`}>{s}</button>
        ))}
      </div>

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30">
                <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Symbol</th>
                <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Name</th>
                <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Price</th>
                <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Change</th>
                <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Volume</th>
                <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Market Cap</th>
                <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Sector</th>
                <th className="text-center py-3 px-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Watch</th>
              </tr>
            </thead>
            <tbody>
              {marketData.map((stock) => (
                <tr key={stock.symbol} className="border-b border-titan-800/20 hover:bg-white/5 transition-colors">
                  <td className="py-3 px-4">
                    <span className="text-white font-medium">{stock.symbol}</span>
                  </td>
                  <td className="py-3 px-4 text-gray-400">{stock.name}</td>
                  <td className="py-3 px-4 text-right text-white font-medium">${stock.price.toFixed(2)}</td>
                  <td className={`py-3 px-4 text-right font-medium ${getChangeColor(stock.change)}`}>
                    <div className="flex items-center justify-end gap-1">
                      {stock.change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {formatPercent(stock.change)}
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right text-gray-400">{stock.volume}</td>
                  <td className="py-3 px-4 text-right text-gray-400">{stock.marketCap}</td>
                  <td className="py-3 px-4">
                    <span className="badge-blue text-[10px]">{stock.sector}</span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <button className="text-gray-600 hover:text-yellow-500 transition-colors">
                      <Star size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
