"use client"

import { Bell, Plus, BellOff, BellRing, Trash2 } from "lucide-react"
import { getChangeColor } from "@/lib/utils"

const alerts = [
  { symbol: "NVDA", type: "Price Above", condition: "Price > $900.00", triggered: false, created: "2024-06-10" },
  { symbol: "TSLA", type: "Price Below", condition: "Price < $230.00", triggered: false, created: "2024-06-09" },
  { symbol: "MSFT", type: "Percent Change", condition: "Daily change > 5%", triggered: false, created: "2024-06-08" },
  { symbol: "AAPL", type: "Volume", condition: "Volume > 80M", triggered: true, created: "2024-06-07" },
  { symbol: "AMZN", type: "RSI", condition: "RSI > 75", triggered: true, created: "2024-06-06" },
  { symbol: "GOOGL", type: "Earnings", condition: "Earnings release date", triggered: false, created: "2024-06-05" },
  { symbol: "META", type: "Technical", condition: "SMA50 crosses SMA200", triggered: false, created: "2024-06-04" },
  { symbol: "NVDA", type: "Price Target", condition: "Price hits analyst target $950", triggered: false, created: "2024-06-03" },
]

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
          <p className="text-gray-500 text-sm mt-1">Configure and manage your market alerts</p>
        </div>
        <button className="btn-primary text-sm"><Plus size={14} /> New Alert</button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Active Alerts", value: "12" },
          { label: "Triggered Today", value: "3" },
          { label: "Delivery Channels", value: "Email, SMS, Web" },
        ].map((s) => (
          <div key={s.label} className="glass-card p-4">
            <div className="text-sm text-gray-400">{s.label}</div>
            <div className="text-lg font-bold text-white mt-1">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30 text-left">
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Symbol</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Type</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Condition</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Status</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Created</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <tr key={i} className="border-b border-titan-800/20 hover:bg-white/5">
                  <td className="py-3 px-4">
                    <span className="text-white font-medium">{a.symbol}</span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="badge-blue text-[10px]">{a.type}</span>
                  </td>
                  <td className="py-3 px-4 text-gray-400">{a.condition}</td>
                  <td className="py-3 px-4">
                    {a.triggered ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-400"><BellRing size={12} /> Triggered</span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-gray-400"><Bell size={12} /> Active</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-gray-500">{a.created}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-1">
                      <button className="btn-ghost text-xs px-2 py-1 text-gray-500 hover:text-yellow-400">
                        <BellOff size={12} />
                      </button>
                      <button className="btn-ghost text-xs px-2 py-1 text-gray-500 hover:text-red-400">
                        <Trash2 size={12} />
                      </button>
                    </div>
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
