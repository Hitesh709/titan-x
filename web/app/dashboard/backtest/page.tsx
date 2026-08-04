"use client"

import { TestTube, TrendingUp, TrendingDown, Calendar, Play, Settings2 } from "lucide-react"
import { formatCurrency, getChangeColor } from "@/lib/utils"

const strategies = [
  { name: "Momentum Breakout", returns: 34.2, sharpe: 1.86, maxDD: -8.4, trades: 142, winRate: 64.2, timeframe: "1Y" },
  { name: "Mean Reversion", returns: 18.7, sharpe: 1.32, maxDD: -5.2, trades: 98, winRate: 58.6, timeframe: "1Y" },
  { name: "EMA Crossover", returns: 22.4, sharpe: 1.54, maxDD: -7.1, trades: 56, winRate: 60.8, timeframe: "1Y" },
  { name: "RSI Divergence", returns: 15.8, sharpe: 1.12, maxDD: -4.8, trades: 73, winRate: 56.4, timeframe: "1Y" },
  { name: "ML Ensemble", returns: 42.6, sharpe: 2.12, maxDD: -6.3, trades: 215, winRate: 68.9, timeframe: "1Y" },
]

const backtestHistory = [
  { name: "Momentum Breakout v3", symbol: "RELIANCE", period: "2024-07 to 2025-07", return: 45.8, benchmark: 28.4, alpha: 17.4 },
  { name: "Mean Reversion v2", symbol: "TCS", period: "2024-07 to 2025-07", return: 12.3, benchmark: 8.2, alpha: 4.1 },
  { name: "ML Ensemble v5", symbol: "NIFTY", period: "2024-01 to 2025-07", return: 38.2, benchmark: 24.6, alpha: 13.6 },
]

export default function BacktestPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtesting</h1>
          <p className="text-gray-500 text-sm mt-1">Strategy development, backtesting, and performance analysis</p>
        </div>
        <button className="btn-primary text-sm"><Play size={14} /> New Backtest</button>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {[
          { label: "Total Strategies", value: "12", change: "+2 this month" },
          { label: "Avg. Annual Return", value: "26.7%", change: "+4.2% vs benchmark" },
          { label: "Avg. Win Rate", value: "61.7%", change: "+3.1% improvement" },
        ].map((s) => (
          <div key={s.label} className="glass-card p-4">
            <div className="text-sm text-gray-400">{s.label}</div>
            <div className="text-2xl font-bold text-white mt-1">{s.value}</div>
            <div className="text-xs text-emerald-400 mt-1">{s.change}</div>
          </div>
        ))}
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4">Strategy Performance</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30 text-left">
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Strategy</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Returns</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Sharpe</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Max DD</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Trades</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Win Rate</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Period</th>
                <th className="py-3 px-4 text-gray-500 font-medium text-xs uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.name} className="border-b border-titan-800/20 hover:bg-white/5">
                  <td className="py-3 px-4 text-white font-medium">{s.name}</td>
                  <td className={`py-3 px-4 font-medium ${getChangeColor(s.returns)}`}>+{s.returns}%</td>
                  <td className="py-3 px-4 text-white">{s.sharpe.toFixed(2)}</td>
                  <td className="py-3 px-4 text-red-400">{s.maxDD.toFixed(1)}%</td>
                  <td className="py-3 px-4 text-gray-400">{s.trades}</td>
                  <td className="py-3 px-4 text-white">{s.winRate}%</td>
                  <td className="py-3 px-4 text-gray-400">{s.timeframe}</td>
                  <td className="py-3 px-4">
                    <button className="btn-ghost text-xs px-2 py-1">Run</button>
                    <button className="btn-ghost text-xs px-2 py-1">Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4">Recent Backtests</h3>
        <div className="space-y-3">
          {backtestHistory.map((b) => (
            <div key={b.name} className="flex items-center justify-between py-3 border-b border-titan-800/20 last:border-0">
              <div>
                <div className="text-sm font-medium text-white">{b.name}</div>
                <div className="text-xs text-gray-500">{b.symbol} · {b.period}</div>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <div className="text-xs text-gray-500">Return</div>
                  <div className={`text-sm font-medium ${getChangeColor(b.return)}`}>+{b.return}%</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-500">Benchmark</div>
                  <div className={`text-sm font-medium ${getChangeColor(b.benchmark)}`}>+{b.benchmark}%</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-500">Alpha</div>
                  <div className={`text-sm font-medium ${getChangeColor(b.alpha)}`}>+{b.alpha}%</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
