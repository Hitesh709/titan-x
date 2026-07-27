"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/contexts/AuthContext"
import {
  LayoutDashboard, BarChart3, Briefcase, TrendingUp, Newspaper,
  Bell, Star, Settings, LogOut, ChevronLeft, ChevronRight,
  Search, Wallet, LineChart, Target, Brain, PieChart,
  Activity, Shield, Menu, X, BookOpen, TestTube,
} from "lucide-react"

const sidebarItems = [
  { icon: LayoutDashboard, label: "Overview", href: "/dashboard" },
  { icon: TrendingUp, label: "Markets", href: "/dashboard/markets" },
  { icon: Briefcase, label: "Portfolio", href: "/dashboard/portfolio" },
  { icon: BarChart3, label: "Analysis", href: "/dashboard/analysis" },
  { icon: BookOpen, label: "Research", href: "/dashboard/research" },
  { icon: Newspaper, label: "News & Insights", href: "/dashboard/news" },
  { icon: Activity, label: "Trading", href: "/dashboard/trading" },
  { icon: TestTube, label: "Backtesting", href: "/dashboard/backtest" },
  { icon: Target, label: "Screener", href: "/dashboard/screener" },
  { icon: Star, label: "Watchlists", href: "/dashboard/watchlists" },
  { icon: Bell, label: "Alerts", href: "/dashboard/alerts" },
  { icon: Settings, label: "Settings", href: "/dashboard/settings" },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-titan-950 flex">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 bg-titan-900/50 backdrop-blur-xl border-r border-titan-800/30 flex flex-col transition-all duration-300 ${
          collapsed ? "w-[68px]" : "w-60"
        } ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-titan-800/30">
          <Link href="/dashboard" className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-titan-500 to-titan-700 flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-xs">TX</span>
            </div>
            {!collapsed && (
              <span className="font-bold text-white truncate">
                TITAN <span className="text-titan-400">X</span>
              </span>
            )}
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          {sidebarItems.map((item) => {
            const isActive = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={isActive ? "sidebar-link-active group" : "sidebar-link group"}
                title={collapsed ? item.label : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <item.icon size={20} className="shrink-0" />
                {!collapsed && <span className="text-sm truncate">{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Bottom */}
        <div className="p-3 border-t border-titan-800/30">
          {!collapsed && user && (
            <div className="px-3 py-2 mb-2">
              <div className="text-sm text-white font-medium truncate">{user.full_name}</div>
              <div className="text-xs text-gray-500 truncate">{user.email}</div>
            </div>
          )}
          <button
            onClick={logout}
            className="sidebar-link w-full"
            title={collapsed ? "Sign Out" : undefined}
          >
            <LogOut size={20} className="shrink-0" />
            {!collapsed && <span className="text-sm">Sign Out</span>}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 border-b border-titan-800/30 flex items-center justify-between px-4 lg:px-6 bg-titan-950/80 backdrop-blur-xl sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="lg:hidden text-gray-400 hover:text-white">
              <Menu size={20} />
            </button>
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="hidden lg:flex text-gray-500 hover:text-white transition-colors"
            >
              {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </button>
            <div className="relative hidden sm:block">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="Search symbols, news, tools..."
                className="pl-9 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-titan-500 w-64"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-600 hidden sm:block">API: Connected</span>
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
