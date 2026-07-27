"use client"

import { BarChart3, TrendingUp, TrendingDown, LineChart, Activity } from "lucide-react"
import { getChangeColor } from "@/lib/utils"

const indicators = [
  { name: "RSI (14)", value: "62.4", signal: "Neutral", status: "neutral" as const },
  { name: "MACD", value: "Bullish", signal: "Buy", status: "positive" as const },
  { name: "SMA (50)", value: "$843.21", signal: "Above", status: "positive" as const },
  { name: "SMA (200)", value: "$721.45", signal: "Above", status: "positive" as const },
  { name: "Bollinger Bands", value: "Upper $892", signal: "Near Upper", status: "warning" as const },
  { name: "Volume", value: "45.2M", signal: "Above Avg", status: "positive" as const },
]

const recommendations = [
  { symbol: "NVDA", action: "Buy", confidence: 92, target: 950, current: 874.32, timeframe: "3M" },
  { symbol: "MSFT", action: "Buy", confidence: 85, target: 450, current: 412.67, timeframe: "6M" },
  { symbol: "TSLA", action: "Hold", confidence: 60, target: 260, current: 245.89, timeframe: "1M" },
  { symbol: "AAPL", action: "Sell", confidence: 78, target: 175, current: 187.45, timeframe: "2M" },
  { symbol: "AMZN", action: "Buy", confidence: 88, target: 200, current: 178.23, timeframe: "6M" },
]

export default function AnalysisPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Technical & Fundamental Analysis</h1>
        <p className="text-gray-500 text-sm mt-1">AI-powered analysis, indicators, and recommendations</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Technical Indicators */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Activity size={16} className="text-titan-400" /> Technical Indicators
          </h3>
          <div className="space-y-4">
            {indicators.map((ind) => (
              <div key={ind.name} className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-gray-400">{ind.name}</div>
                  <div className="text-sm font-medium text-white">{ind.value}</div>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                  ind.status === "positive" ? "badge-green" :
                  ind.status === "warning" ? "badge-yellow" : "badge-blue"
                }`}>{ind.signal}</span>
              </div>
            ))}
          </div>
        </div>

        {/* AI Recommendations */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <BarChart3 size={16} className="text-titan-400" /> AI Recommendations
          </h3>
          <div className="space-y-3">
            {recommendations.map((rec) => (
              <div key={rec.symbol} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{rec.symbol}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      rec.action === "Buy" ? "badge-green" :
                      rec.action === "Sell" ? "badge-red" : "badge-yellow"
                    }`}>{rec.action}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">Target: ${rec.target} | {rec.timeframe}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-white">${rec.current.toFixed(2)}</div>
                  <div className="flex items-center gap-1 text-xs text-titan-400">
                    <TrendingUp size={12} />
                    {rec.confidence}% confidence
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pattern Recognition */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <LineChart size={16} className="text-titan-400" /> Pattern Recognition
        </h3>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            { pattern: "Bull Flag", symbol: "NVDA", timeframe: "1H", strength: "Strong", direction: "bullish" as const },
            { pattern: "Double Bottom", symbol: "MSFT", timeframe: "4H", strength: "Moderate", direction: "bullish" as const },
            { pattern: "Head & Shoulders", symbol: "TSLA", timeframe: "1D", strength: "Weak", direction: "bearish" as const },
            { pattern: "Ascending Triangle", symbol: "AMZN", timeframe: "1D", strength: "Strong", direction: "bullish" as const },
            { pattern: "Engulfing", symbol: "AAPL", timeframe: "1H", strength: "Moderate", direction: "bearish" as const },
            { pattern: "Golden Cross", symbol: "GOOGL", timeframe: "1D", strength: "Strong", direction: "bullish" as const },
          ].map((p) => (
            <div key={p.pattern + p.symbol} className="bg-white/5 rounded-lg p-3 border border-white/10">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">{p.pattern}</span>
                <span className={`flex items-center gap-1 text-xs font-medium ${
                  p.direction === "bullish" ? "text-emerald-400" : "text-red-400"
                }`}>
                  {p.direction === "bullish" ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  {p.direction}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-white">{p.symbol}</span>
                <span className="text-xs text-gray-500">{p.timeframe} · {p.strength}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Fundamental Analysis quick view */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <BarChart3 size={16} className="text-titan-400" /> Fundamental Metrics — NVDA
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "P/E Ratio", value: "34.2" },
            { label: "EPS (TTM)", value: "$25.56" },
            { label: "Revenue (TTM)", value: "$60.9B" },
            { label: "Profit Margin", value: "48.3%" },
            { label: "Debt/Equity", value: "0.45" },
            { label: "ROE", value: "42.1%" },
            { label: "Div Yield", value: "0.04%" },
            { label: "Beta", value: "1.68" },
          ].map((m) => (
            <div key={m.label} className="text-center p-3 bg-white/5 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">{m.label}</div>
              <div className="text-sm font-semibold text-white">{m.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
