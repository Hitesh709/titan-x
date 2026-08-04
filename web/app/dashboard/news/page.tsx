"use client"

import { Newspaper, ExternalLink, TrendingUp, TrendingDown, Minus } from "lucide-react"
import Link from "next/link"

const newsItems = [
  { title: "Reliance Jio Adds 8.2M Subscribers, RIL Shares Rise 3% on Telecom Growth", source: "Economic Times", sentiment: "positive" as const, time: "2h ago", summary: "Reliance's telecom arm reported strong subscriber additions in the June quarter, boosting the conglomerate's digital services revenue and lifting shares of the Nifty heavyweight.", symbols: ["RELIANCE"] },
  { title: "RBI Holds Repo Rate at 6.5%, Signals Easing in Coming Quarters", source: "Mint", sentiment: "positive" as const, time: "3h ago", summary: "India's central bank kept the policy rate unchanged for the eighth consecutive meeting while flagging softer inflation that could open the door to rate cuts later this year.", symbols: ["BANKNIFTY", "SBIN"] },
  { title: "Infosys Wins $1.5B AI Transformation Deal, Stock Jumps 4%", source: "Business Standard", sentiment: "positive" as const, time: "4h ago", summary: "The Bengaluru-based IT major clinched a large multi-year artificial intelligence and cloud contract from a global client, reaffirming the momentum in enterprise AI spending.", symbols: ["INFY", "TCS"] },
  { title: "Maruti Suzuki Reports Record Monthly Domestic Sales on SUV Demand", source: "Reuters", sentiment: "positive" as const, time: "5h ago", summary: "India's largest carmaker posted its best-ever monthly dispatches, driven by sustained demand for its compact SUV lineup and easing semiconductor supply constraints.", symbols: ["MARUTI", "TATAMOTORS"] },
  { title: "HDFC Bank Q1 Net Interest Income Grows 12%, Asset Quality Stable", source: "Moneycontrol", sentiment: "positive" as const, time: "6h ago", summary: "India's largest private lender reported healthy loan growth and contained slippages, keeping its core profitability metrics on track despite margin pressure.", symbols: ["HDFCBANK", "ICICIBANK"] },
  { title: "Crude Prices Slide as OPEC+ Considers Output Increase", source: "Business Today", sentiment: "negative" as const, time: "7h ago", summary: "Global oil benchmarks fell nearly 3% amid reports that OPEC+ members are discussing a production increase, weighing on energy stocks while easing import costs.", symbols: ["ONGC", "RELIANCE"] },
  { title: "Tata Motors EV Lineup Drives Double-Digit Growth in Quarterly Deliveries", source: "Economic Times", sentiment: "positive" as const, time: "8h ago", summary: "The automaker's electric vehicle portfolio expanded sharply during the quarter, supported by new launches and an expanding charging network across major cities.", symbols: ["TATAMOTORS", "M&M"] },
]

export default function NewsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">News & Market Intelligence</h1>
        <p className="text-gray-500 text-sm mt-1">Real-time news with AI-powered sentiment analysis</p>
      </div>

      <div className="space-y-4">
        {newsItems.map((item, i) => (
          <div key={i} className="glass-card p-5 hover:border-titan-600/40 transition-all duration-200">
            <div className="flex items-start gap-4">
              <div className="mt-0.5">
                {item.sentiment === "positive" ? (
                  <TrendingUp size={18} className="text-emerald-400" />
                ) : item.sentiment === "negative" ? (
                  <TrendingDown size={18} className="text-red-400" />
                ) : (
                  <Minus size={18} className="text-gray-500" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-white">{item.source}</span>
                  <span className={`w-2 h-2 rounded-full ${
                    item.sentiment === "positive" ? "bg-emerald-500" :
                    item.sentiment === "negative" ? "bg-red-500" : "bg-gray-500"
                  }`} />
                  <span className="text-xs text-gray-600">{item.time}</span>
                </div>
                <h3 className="text-base font-semibold text-white mb-1">{item.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{item.summary}</p>
                <div className="flex items-center gap-2 mt-3">
                  <div className="flex gap-1.5">
{item.symbols.map((sym) => (
  <Link key={sym} href={`/dashboard/stocks/${sym}`} className={`badge text-[10px] hover:opacity-80 ${
    item.sentiment === "positive" ? "badge-green" :
    item.sentiment === "negative" ? "badge-red" : "badge-blue"
  }`}>{sym}</Link>
))}
                  </div>
                  <button className="ml-auto text-gray-500 hover:text-titan-400 transition-colors">
                    <ExternalLink size={14} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
