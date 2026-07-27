"use client"

import { BookOpen, Building2, Globe, FileText, TrendingUp, ExternalLink } from "lucide-react"

const companies = [
  { symbol: "NVDA", name: "NVIDIA Corporation", sector: "Semiconductors", price: 874.32, rating: "Strong Buy", target: 950, employees: "29,600", founded: "1993" },
  { symbol: "MSFT", name: "Microsoft Corporation", sector: "Software", price: 412.67, rating: "Buy", target: 450, employees: "228,000", founded: "1975" },
  { symbol: "AAPL", name: "Apple Inc", sector: "Consumer Electronics", price: 187.45, rating: "Hold", target: 200, employees: "164,000", founded: "1976" },
  { symbol: "TSLA", name: "Tesla Inc", sector: "Automotive", price: 245.89, rating: "Hold", target: 260, employees: "140,000", founded: "2003" },
  { symbol: "AMZN", name: "Amazon.com Inc", sector: "E-Commerce", price: 178.23, rating: "Strong Buy", target: 210, employees: "1,525,000", founded: "1994" },
]

const peerComparison = [
  { metric: "Market Cap", nvda: "2.15T", peers: "1.85T" },
  { metric: "Revenue", nvda: "$60.9B", peers: "$45.2B" },
  { metric: "Gross Margin", nvda: "72.8%", peers: "65.4%" },
  { metric: "P/E Ratio", nvda: "34.2x", peers: "28.6x" },
  { metric: "Revenue Growth", nvda: "126%", peers: "42%" },
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
                    <span className="badge-blue">{c.symbol}</span>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">{c.sector} · Founded {c.founded} · {c.employees} employees</p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-white">${c.price.toFixed(2)}</div>
                <div className="flex items-center gap-2 justify-end text-xs mt-1">
                  <span className={`badge ${
                    c.rating === "Strong Buy" ? "badge-green" :
                    c.rating === "Buy" ? "badge-blue" :
                    "badge-yellow"
                  }`}>{c.rating}</span>
                  <span className="text-gray-500">Target: ${c.target}</span>
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
