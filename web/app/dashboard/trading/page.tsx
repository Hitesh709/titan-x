"use client"

import { Activity, TrendingUp, ArrowRight, Zap, Clock, CheckCircle, XCircle } from "lucide-react"

const openOrders = [
  { symbol: "NVDA", type: "Limit Buy", shares: 500, limit: 860.00, status: "Working", submitted: "09:32:15" },
  { symbol: "TSLA", type: "Stop Sell", shares: 300, limit: 235.00, status: "Working", submitted: "10:15:42" },
  { symbol: "MSFT", type: "Limit Sell", shares: 200, limit: 420.00, status: "Partial", submitted: "09:45:00" },
]

const orderHistory = [
  { symbol: "AAPL", type: "Market Buy", shares: 1000, price: 187.23, filled: "09:30:01", status: "Filled" },
  { symbol: "AMZN", type: "Limit Buy", shares: 500, price: 178.00, filled: "10:22:33", status: "Filled" },
  { symbol: "GOOGL", type: "Limit Sell", shares: 300, price: 158.50, filled: "11:05:18", status: "Filled" },
  { symbol: "NVDA", type: "Market Sell", shares: 200, price: 875.12, filled: "13:42:55", status: "Filled" },
]

const brokers = [
  { name: "Interactive Brokers", status: "Connected", latency: "12ms" },
  { name: "Charles Schwab", status: "Connected", latency: "18ms" },
  { name: "Alpaca Trading", status: "Connected", latency: "8ms" },
]

export default function TradingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Trading</h1>
        <p className="text-gray-500 text-sm mt-1">Order management, execution, and broker connectivity</p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {brokers.map((b) => (
          <div key={b.name} className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">{b.name}</span>
              <span className="flex items-center gap-1 text-xs text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {b.status}
              </span>
            </div>
            <div className="text-xs text-gray-500">Latency: {b.latency}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Clock size={16} className="text-titan-400" /> Open Orders
          </h3>
          <div className="space-y-3">
            {openOrders.map((o) => (
              <div key={o.symbol + o.type} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{o.symbol}</span>
                    <span className="badge-blue text-[10px]">{o.type}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{o.shares} shares @ ${o.limit.toFixed(2)}</div>
                </div>
                <div className="text-right">
                  <span className={`text-xs font-medium ${
                    o.status === "Working" ? "text-yellow-400" : "text-titan-400"
                  }`}>{o.status}</span>
                  <div className="text-xs text-gray-500">{o.submitted}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <CheckCircle size={16} className="text-titan-400" /> Order History
          </h3>
          <div className="space-y-3">
            {orderHistory.map((o) => (
              <div key={o.symbol + o.type + o.filled} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{o.symbol}</span>
                    <span className="badge-blue text-[10px]">{o.type}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{o.shares} shares @ ${o.price.toFixed(2)}</div>
                </div>
                <div className="text-right">
                  <span className="text-xs text-emerald-400 font-medium">{o.status}</span>
                  <div className="text-xs text-gray-500">{o.filled}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick Trade */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Zap size={16} className="text-titan-400" /> Quick Trade
        </h3>
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Symbol</label>
            <input type="text" className="input-field w-24 text-sm" placeholder="NVDA" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Side</label>
            <div className="flex gap-1">
              <button className="px-3 py-1.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Buy</button>
              <button className="px-3 py-1.5 rounded text-xs font-medium bg-white/5 text-gray-400 border border-white/10 hover:bg-red-500/10 hover:text-red-400">Sell</button>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Order Type</label>
            <select className="input-field text-sm py-2 px-3 w-28">
              <option>Market</option>
              <option>Limit</option>
              <option>Stop</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Quantity</label>
            <input type="number" className="input-field w-20 text-sm" placeholder="100" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Price</label>
            <input type="text" className="input-field w-24 text-sm" placeholder="875.00" />
          </div>
          <button className="btn-primary text-sm px-6">
            Place Order <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
