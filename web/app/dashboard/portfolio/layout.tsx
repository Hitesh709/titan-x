"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Briefcase, Wallet, PieChart, Building2, TrendingUp, Trophy, ArrowLeftRight, BrainCircuit } from "lucide-react"

const tabs = [
  { href: "/dashboard/portfolio", label: "Holdings", icon: Briefcase },
  { href: "/dashboard/portfolio/pnl", label: "PnL", icon: Wallet },
  { href: "/dashboard/portfolio/allocation", label: "Allocation", icon: PieChart },
  { href: "/dashboard/portfolio/sectors", label: "Sectors", icon: Building2 },
  { href: "/dashboard/portfolio/profit", label: "Profit", icon: TrendingUp },
  { href: "/dashboard/portfolio/performance", label: "Performance", icon: Trophy },
  { href: "/dashboard/portfolio/transactions", label: "Transactions", icon: ArrowLeftRight },
  { href: "/dashboard/portfolio/analytics", label: "Analytics", icon: BrainCircuit },
]

export default function PortfolioLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio</h1>
        <p className="text-gray-500 text-sm mt-1">Holdings, PnL, allocation, sector exposure and trading analytics</p>
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
