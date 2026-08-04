"use client"

import { BookOpen, Building2, Globe, FileText, TrendingUp, ExternalLink } from "lucide-react"
import Link from "next/link"

const companies = [
  { symbol: "RELIANCE", name: "Reliance Industries Ltd", sector: "Energy · Oil & Gas", price: 1300.00, rating: "Strong Buy", target: 1550, employees: "330,000", founded: "1966" },
  { symbol: "TCS", name: "Tata Consultancy Services Ltd", sector: "Technology · IT Services", price: 2460.00, rating: "Buy", target: 2700, employees: "600,000", founded: "1968" },
  { symbol: "HDFCBANK", name: "HDFC Bank Ltd", sector: "Financials · Banks", price: 1750.00, rating: "Hold", target: 1900, employees: "200,000", founded: "1994" },
  { symbol: "INFY", name: "Infosys Ltd", sector: "Technology · IT Services", price: 1520.00, rating: "Hold", target: 1650, employees: "340,000", founded: "1981" },
  { symbol: "BHARTIARTL", name: "Bharti Airtel Ltd", sector: "Communication Services · Telecom", price: 1450.00, rating: "Strong Buy", target: 1700, employees: "85,000", founded: "1995" },
]

const peerComparison = [
  { metric: "Market Cap", nvda: "₹8.8L Cr", peers: "₹7.4L Cr" },
  { metric: "Revenue", nvda: "₹7.1L Cr", peers: "₹5.2L Cr" },
  { metric: "Gross Margin", nvda: "45.4%", peers: "41.2%" },
  { metric: "P/E Ratio", nvda: "22.8x", peers: "19.6x" },
  { metric: "Revenue Growth", nvda: "9.2%", peers: "6.4%" },
]

export default function ResearchPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Company Research</h1>
        <p className="text-gray-500 text-sm mt-1">In-depth company analysis, filings, and peer comparisons</p>
      </div>

      <div className="space-y-4">
        {companies.map((c) => (
          <div key={c.symbol} className="glass-card p-5">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-titan-600/20 to-titan-800/20 border border-titan-700/30 flex items-center justify-center">
                  <Building2 size={24} className="text-titan-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
<h3 className="text-lg font-semibold text-white">{c.name}</h3>
<Link href={`/dashboard/stocks/${c.symbol}`} className="badge-blue hover:bg-titan-600/30 transition-colors">{c.symbol}</Link>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">{c.sector} · Founded {c.founded} · {c.employees} employees</p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-white">₹{c.price.toFixed(2)}</div>
                <div className="flex items-center gap-2 justify-end text-xs mt-1">
                  <span className={`badge ${
                    c.rating === "Strong Buy" ? "badge-green" :
                    c.rating === "Buy" ? "badge-blue" :
                    "badge-yellow"
                  }`}>{c.rating}</span>
                  <span className="text-gray-500">Target: ₹{c.target}</span>
                </div>
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <div>
                <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <TrendingUp size={14} className="text-titan-400" /> Peer Comparison
                </h4>
                <div className="space-y-2">
                  {peerComparison.map((p) => (
                    <div key={p.metric} className="flex items-center justify-between text-sm py-1.5 border-b border-titan-800/20">
                      <span className="text-gray-400">{p.metric}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-white font-medium">{p.nvda}</span>
                        <span className="text-gray-500 w-20 text-right">Peer: {p.peers}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <FileText size={14} className="text-titan-400" /> Recent Filings
                </h4>
                <div className="space-y-2">
                  {[
                    { type: "10-Q", date: "2024-05-22", title: "Quarterly Report Q1 2024" },
                    { type: "8-K", date: "2024-05-15", title: "Material Event — New Data Center Contract" },
                    { type: "10-K", date: "2024-02-21", title: "Annual Report FY 2023" },
                    { type: "DEF 14A", date: "2024-03-10", title: "Proxy Statement — Annual Meeting" },
                  ].map((f) => (
                    <div key={f.type + f.date} className="flex items-center justify-between text-sm py-1.5 border-b border-titan-800/20">
                      <div className="flex items-center gap-2">
                        <span className="badge-blue text-[10px]">{f.type}</span>
                        <span className="text-gray-400">{f.title}</span>
                      </div>
                      <span className="text-gray-500 text-xs">{f.date}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
