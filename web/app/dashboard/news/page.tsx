"use client"

import { Newspaper, ExternalLink, TrendingUp, TrendingDown, Minus } from "lucide-react"

const newsItems = [
  { title: "NVIDIA Reports Record Data Center Revenue, Shares Surge 5%", source: "Financial Times", sentiment: "positive" as const, time: "2h ago", summary: "NVIDIA's Q1 earnings exceeded expectations with data center revenue reaching $22.6B, driven by unprecedented demand for AI computing infrastructure.", symbols: ["NVDA", "AMD", "INTC"] },
  { title: "Federal Reserve Holds Rates Steady, Signals Potential Cut in September", source: "Reuters", sentiment: "positive" as const, time: "3h ago", summary: "The Federal Reserve maintained interest rates at 5.25-5.50% while indicating progress on inflation may allow for rate reductions later this year.", symbols: ["SPY", "QQQ", "TLT"] },
  { title: "Tesla Faces New Regulatory Scrutiny Over Autopilot Claims", source: "Bloomberg", sentiment: "negative" as const, time: "4h ago", summary: "The NHTSA has opened a new investigation into Tesla's Full Self-Driving claims following a series of incidents involving the autonomous driving system.", symbols: ["TSLA"] },
  { title: "Microsoft Announces $60B Share Buyback Program, Dividend Increase", source: "CNBC", sentiment: "positive" as const, time: "5h ago", summary: "Microsoft's board authorized a $60 billion share repurchase program and raised the quarterly dividend by 10%, signaling strong confidence in future growth.", symbols: ["MSFT"] },
  { title: "Oil Prices Slide as OPEC+ Considers Production Increase", source: "Wall Street Journal", sentiment: "negative" as const, time: "6h ago", summary: "Crude oil prices fell 3% amid reports that OPEC+ members are discussing a potential production increase at next month's meeting.", symbols: ["XOM", "CVX", "USO"] },
  { title: "Amazon Invests $4B in AI Startup Anthropic", source: "TechCrunch", sentiment: "positive" as const, time: "7h ago", summary: "Amazon has committed an additional $4 billion investment in AI startup Anthropic, deepening their strategic partnership in the rapidly evolving AI landscape.", symbols: ["AMZN"] },
  { title: "JPMorgan Issues Recession Warning as Consumer Debt Hits Record", source: "Bloomberg", sentiment: "negative" as const, time: "8h ago", summary: "JPMorgan's chief economist warned of increased recession risk as US consumer debt surpassed $17 trillion for the first time.", symbols: ["JPM", "BAC", "C"] },
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
                      <span key={sym} className={`badge text-[10px] ${
                        item.sentiment === "positive" ? "badge-green" :
                        item.sentiment === "negative" ? "badge-red" : "badge-blue"
                      }`}>{sym}</span>
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
