"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { BarChart3, CandlestickChart, History, LayoutGrid, PieChart } from "lucide-react"

const tabs = [
  { href: "/dashboard/markets", label: "Indices", icon: LayoutGrid },
  { href: "/dashboard/markets/charts", label: "Charts", icon: CandlestickChart },
  { href: "/dashboard/markets/sectors", label: "Sectors", icon: PieChart },
  { href: "/dashboard/markets/breadth", label: "Breadth", icon: BarChart3 },
  { href: "/dashboard/markets/historical", label: "Historical", icon: History },
]

export default function MarketsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Markets</h1>
        <p className="text-gray-500 text-sm mt-1">Indian indices, sector performance, breadth and historical data</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {tabs.map((tab) => {
          const isActive = pathname === tab.href
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                isActive
                  ? "bg-titan-600/20 text-titan-400 border-titan-600/30"
                  : "bg-white/5 text-gray-400 hover:text-gray-200 border-white/10"
              }`}
            >
              <tab.icon size={14} />
              {tab.label}
            </Link>
          )
        })}
      </div>

      {children}
    </div>
  )
}
