"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/contexts/AuthContext"
import { startLiveTicker } from "@/lib/live"
import api from "@/lib/api"
import type { PaginatedResponse } from "@/types"
import {
  LayoutDashboard, BarChart3, Briefcase, TrendingUp, Newspaper,
  Bell, Star, Settings, LogOut, ChevronLeft, ChevronRight,
  Search, Wallet, LineChart, Target, Brain, PieChart,
  Activity, Shield, Menu, X, BookOpen, TestTube, Loader2,
} from "lucide-react"

interface CompanySearchResult {
  symbol: string
  company_name: string
  sector: string | null
  exchange: string
}

const sidebarItems = [
  { icon: LayoutDashboard, label: "Overview", href: "/dashboard" },
  { icon: TrendingUp, label: "Markets", href: "/dashboard/markets" },
  { icon: Briefcase, label: "Portfolio", href: "/dashboard/portfolio" },
  { icon: BarChart3, label: "Analysis", href: "/dashboard/analysis" },
  { icon: BookOpen, label: "Research", href: "/dashboard/research" },
  { icon: Brain, label: "Recommendations", href: "/dashboard/recommendations" },
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
  const [sendingVerification, setSendingVerification] = useState(false)
  const [search, setSearch] = useState("")
  const [searchResults, setSearchResults] = useState<CompanySearchResult[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const searchBoxRef = useRef<HTMLDivElement>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout, loading, sendVerification } = useAuth()

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login")
    }
  }, [loading, user, router])

  useEffect(() => startLiveTicker(), [])

  // Close the search dropdown when clicking outside.
  useEffect(() => {
    if (!searchOpen) return
    const onDocMouseDown = (e: MouseEvent) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target as Node)) {
        setSearchOpen(false)
      }
    }
    document.addEventListener("mousedown", onDocMouseDown)
    return () => document.removeEventListener("mousedown", onDocMouseDown)
  }, [searchOpen])

  const runSearch = useCallback(async (q: string) => {
    const term = q.trim()
    if (!term) {
      setSearchResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    try {
      const res = await api.get<PaginatedResponse<CompanySearchResult>>(
        `/companies?search=${encodeURIComponent(term)}&exchange=NSE&limit=8&order_by=symbol`
      )
      setSearchResults(res.items ?? [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [])

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setSearch(value)
    setSearchOpen(value.trim().length > 0)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => runSearch(value), 250)
  }

  const goToSymbol = (symbol: string) => {
    setSearch("")
    setSearchResults([])
    setSearchOpen(false)
    setMobileOpen(false)
    router.push(`/dashboard/stocks/${symbol.toUpperCase()}`)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return
    if (searchResults.length > 0) {
      goToSymbol(searchResults[0].symbol)
    } else if (search.trim()) {
      goToSymbol(search.trim())
    }
  }

  const handleVerifyClick = async () => {
    if (!user || sendingVerification) return
    setSendingVerification(true)
    try {
      const res = await sendVerification(user.email)
      if (res.verification_url) window.location.href = res.verification_url
    } catch {
      // ignore
    } finally {
      setSendingVerification(false)
    }
  }

  if (loading || !user) {
    return (
      <div className="min-h-screen bg-titan-950 flex items-center justify-center">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-titan-500 to-titan-700 flex items-center justify-center">
          <span className="text-white font-bold text-xs">TX</span>
        </div>
      </div>
    )
  }

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
              <div className="text-sm text-white font-medium truncate">{user.full_name || user.email}</div>
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
            <div className="relative hidden sm:block" ref={searchBoxRef}>
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                value={search}
                onChange={handleSearchChange}
                onKeyDown={handleSearchKeyDown}
                onFocus={() => setSearchOpen(search.trim().length > 0)}
                placeholder="Search NSE scripts (e.g. RELIANCE)…"
                className="pl-9 pr-9 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-titan-500 w-64"
              />
              {searching || (search && searchResults.length > 0) ? (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">
                  {searching ? <Loader2 size={14} className="animate-spin" /> : <span className="text-[10px]">{searchResults.length}</span>}
                </span>
              ) : null}
              {searchOpen && (
                <div className="absolute left-0 right-0 top-full mt-2 z-50 rounded-lg bg-titan-900/95 border border-titan-800/40 shadow-2xl backdrop-blur-xl overflow-hidden max-h-80 overflow-y-auto">
                  {searching ? (
                    <div className="px-4 py-3 text-xs text-gray-500 flex items-center gap-2">
                      <Loader2 size={13} className="animate-spin" /> Searching…
                    </div>
                  ) : searchResults.length === 0 ? (
                    <div className="px-4 py-3 text-xs text-gray-500">No NSE scripts match &ldquo;{search}&rdquo;.</div>
                  ) : (
                    searchResults.map((r) => (
                      <button
                        key={r.symbol}
                        onClick={() => goToSymbol(r.symbol)}
                        className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left hover:bg-titan-800/60 transition-colors"
                      >
                        <div className="min-w-0">
                          <div className="text-sm text-white font-medium">{r.symbol}</div>
                          <div className="text-[11px] text-gray-500 truncate">{r.company_name}</div>
                        </div>
                        <span className="text-[10px] uppercase text-titan-400 shrink-0">{r.sector ?? "—"}</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-600 hidden sm:block">API: Connected</span>
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto">
          {user && !user.is_verified && (
            <div className="mb-4 flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-300 text-sm">
              <span>
                Your email is not verified yet. Some features may be limited until you confirm your address.
              </span>
              <button
                onClick={handleVerifyClick}
                disabled={sendingVerification}
                className="text-yellow-200 font-medium hover:text-white shrink-0 disabled:opacity-50"
              >
                {sendingVerification ? "Sending..." : "Verify now"}
              </button>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  )
}
