"use client"

import { BarChart3, TrendingUp, TrendingDown, LineChart, Activity } from "lucide-react"
import { getChangeColor } from "@/lib/utils"

const indicators = [
  { name: "RSI (14)", value: "62.4", signal: "Neutral", status: "neutral" as const },
  { name: "MACD", value: "Bullish", signal: "Buy", status: "positive" as const },
  { name: "SMA (50)", value: "₹1,278.00", signal: "Above", status: "positive" as const },
  { name: "SMA (200)", value: "₹1,210.00", signal: "Above", status: "positive" as const },
  { name: "Bollinger Bands", value: "Upper ₹1,310", signal: "Near Upper", status: "warning" as const },
  { name: "Volume", value: "10.2M", signal: "Above Avg", status: "positive" as const },
]

const recommendations = [
  { symbol: "RELIANCE", action: "Buy", confidence: 92, target: 1550, current: 1300.00, timeframe: "3M" },
  { symbol: "TCS", action: "Buy", confidence: 85, target: 2700, current: 2460.00, timeframe: "6M" },
  { symbol: "HDFCBANK", action: "Hold", confidence: 60, target: 1900, current: 1750.00, timeframe: "1M" },
  { symbol: "TATAMOTORS", action: "Sell", confidence: 78, target: 990, current: 1050.00, timeframe: "2M" },
  { symbol: "INFY", action: "Buy", confidence: 88, target: 1680, current: 1520.00, timeframe: "6M" },
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
                  <div className="text-xs text-gray-500 mt-0.5">Target: ₹{rec.target} | {rec.timeframe}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-white">₹{rec.current.toFixed(2)}</div>
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
            { pattern: "Bull Flag", symbol: "RELIANCE", timeframe: "1H", strength: "Strong", direction: "bullish" as const },
            { pattern: "Double Bottom", symbol: "TCS", timeframe: "4H", strength: "Moderate", direction: "bullish" as const },
            { pattern: "Head & Shoulders", symbol: "TATAMOTORS", timeframe: "1D", strength: "Weak", direction: "bearish" as const },
            { pattern: "Ascending Triangle", symbol: "HDFCBANK", timeframe: "1D", strength: "Strong", direction: "bullish" as const },
            { pattern: "Engulfing", symbol: "INFY", timeframe: "1H", strength: "Moderate", direction: "bearish" as const },
            { pattern: "Golden Cross", symbol: "SBIN", timeframe: "1D", strength: "Strong", direction: "bullish" as const },
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
          <BarChart3 size={16} className="text-titan-400" /> Fundamental Metrics — RELIANCE
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "P/E Ratio", value: "22.8" },
            { label: "EPS (TTM)", value: "₹57.10" },
            { label: "Revenue (TTM)", value: "₹7.1L Cr" },
            { label: "Profit Margin", value: "11.2%" },
            { label: "Debt/Equity", value: "0.42" },
            { label: "ROE", value: "14.3%" },
            { label: "Div Yield", value: "0.38%" },
            { label: "Beta", value: "1.05" },
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
