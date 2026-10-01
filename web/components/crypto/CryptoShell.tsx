"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { Activity, BarChart3, Bell, Bitcoin, Bot, Briefcase, ChevronLeft, ChevronRight, FlaskConical, Layers, LineChart, Menu, Newspaper, Search, Settings, ShieldCheck, Star, Target, TrendingUp, X } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import CryptoLiveTicker, { useCryptoLivePrices } from "./CryptoLiveTicker"

const nav = [
  { icon: Layers, label: "Overview", href: "/crypto" },
  { icon: TrendingUp, label: "Markets", href: "/crypto/markets" },
  { icon: Briefcase, label: "Portfolio", href: "/crypto/portfolio" },
  { icon: LineChart, label: "Analysis", href: "/crypto/analysis" },
  { icon: Target, label: "Research", href: "/crypto/research" },
  { icon: Activity, label: "Recommendations", href: "/crypto/recommendations" },
  { icon: BarChart3, label: "Trading", href: "/crypto/trading" },
  { icon: Bot, label: "Auto Bot", href: "/crypto/bot" },
  { icon: FlaskConical, label: "Backtesting", href: "/crypto/backtesting" },
  { icon: ShieldCheck, label: "Risk", href: "/crypto/risk" },
  { icon: Star, label: "Watchlists", href: "/crypto/watchlists" },
  { icon: Bell, label: "Alerts", href: "/crypto/alerts" },
  { icon: Newspaper, label: "News & Insights", href: "/crypto/news" },
  { icon: Settings, label: "Settings", href: "/crypto/settings" },
]

const symbols = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"]

export default function CryptoShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, loading, logout } = useAuth()
  const { prices } = useCryptoLivePrices()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    if (!loading && !user) router.replace("/login")
  }, [loading, user, router])

  const matches = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q) return symbols
    return symbols.filter(s => s.includes(q))
  }, [query])

  const openSymbol = (symbol: string) => {
    setQuery("")
    setSearchOpen(false)
    setMobileOpen(false)
    router.push("/crypto/markets?symbol=" + encodeURIComponent(symbol))
  }

  if (loading || !user) {
    return <div className="min-h-screen bg-[#020713] flex items-center justify-center"><div className="tx-brand-mark"><span className="text-white font-bold text-xs">TX</span></div></div>
  }

  return (
    <div className="min-h-screen flex tx-shell bg-[#020713] text-white">
      {mobileOpen && <div className="fixed inset-0 z-40 bg-black/70 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside className={`fixed lg:static inset-y-0 left-0 z-50 tx-sidebar backdrop-blur-xl flex flex-col transition-all duration-300 ${collapsed ? "w-[68px]" : "w-60"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="tx-brand flex items-center px-4">
          <Link href="/crypto" className="flex items-center gap-3 min-w-0" onClick={() => setMobileOpen(false)}>
            <div className="tx-brand-mark flex items-center justify-center shrink-0"><Bitcoin size={17} className="text-cyan-200" /></div>
            {!collapsed && <div className="min-w-0"><div className="font-bold text-white truncate">TITAN <span className="text-cyan-300">X</span></div><div className="text-[9px] uppercase tracking-[.2em] text-fuchsia-300">Crypto Engine</div></div>}
          </Link>
          <button className="ml-auto lg:hidden text-slate-500" onClick={() => setMobileOpen(false)} aria-label="Close crypto navigation"><X size={18}/></button>
        </div>
        {!collapsed && <div className="mx-3 mb-2 rounded-xl border border-cyan-500/10 bg-cyan-500/[.03] px-3 py-2"><div className="flex items-center justify-between"><span className="text-[9px] uppercase tracking-widest text-slate-600">Market</span><span className="text-[9px] text-emerald-300">24/7 LIVE</span></div><div className="text-xs text-cyan-200 mt-1">Digital Assets</div></div>}
        <nav aria-label="Crypto navigation" className="tx-nav-list flex-1 overflow-y-auto">
          {nav.map(item => {
            const active = pathname === item.href || (item.href !== "/crypto" && pathname.startsWith(item.href + "/"))
            return <Link key={item.href} href={item.href} title={collapsed ? item.label : undefined} aria-current={active ? "page" : undefined} onClick={() => setMobileOpen(false)} className={active ? "sidebar-link-active tx-nav-tab group flex items-center gap-3 px-3" : "sidebar-link tx-nav-tab group flex items-center gap-3 px-3"}>
              <item.icon size={18} className="shrink-0" />
              {!collapsed && <span className="text-sm truncate">{item.label}</span>}
            </Link>
          })}
        </nav>
        <div className="p-3 border-t border-blue-900/30">
          {!collapsed && <div className="px-3 py-2 mb-2"><div className="text-sm text-white font-medium truncate">{user.username || user.email}</div><div className="text-[10px] text-slate-500 truncate">Crypto workspace</div></div>}
          <button onClick={logout} className="sidebar-link w-full flex items-center gap-3 px-3" title={collapsed ? "Sign Out" : undefined}><span className="text-lg">↪</span>{!collapsed && <span className="text-sm">Sign Out</span>}</button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="tx-topbar flex items-center justify-between px-4 lg:px-6 backdrop-blur-xl sticky top-0 z-30">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setMobileOpen(true)} className="lg:hidden text-gray-400" aria-label="Open crypto navigation"><Menu size={20}/></button>
            <button onClick={() => setCollapsed(!collapsed)} className="hidden lg:flex text-gray-500 hover:text-white" aria-label={collapsed ? "Expand crypto sidebar" : "Collapse crypto sidebar"}>{collapsed ? <ChevronRight size={18}/> : <ChevronLeft size={18}/>}</button>
            <div className="relative min-w-0" style={{ width: "min(360px, 45vw)" }}>
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-cyan-500"/>
              <input value={query} onChange={e => { setQuery(e.target.value); setSearchOpen(true) }} onFocus={() => setSearchOpen(true)} placeholder="Search crypto pair…" aria-label="Search crypto pair" className="tx-search pl-9 pr-3 py-2 text-sm text-gray-300 placeholder-gray-600 focus:outline-none w-full"/>
              {searchOpen && <div className="absolute left-0 right-0 top-full mt-2 z-50 rounded-xl bg-slate-950/95 border border-cyan-800/30 shadow-2xl backdrop-blur-xl overflow-hidden">
                {matches.map(symbol => <button key={symbol} onClick={() => openSymbol(symbol)} className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-cyan-900/20"><span className="text-sm text-white">{symbol.replace("USDT","")}/USDT</span><span className="text-[10px] text-slate-500">{prices[symbol]?.price ? "$" + prices[symbol].price.toLocaleString(undefined,{maximumFractionDigits:6}) : "LIVE"}</span></button>)}
              </div>}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0 ml-3"><CryptoLiveTicker/><span className="tx-api text-[10px] hidden sm:block">● CRYPTO API</span><div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"/></div>
        </header>
        <main className="tx-content flex-1 p-4 lg:p-6 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
