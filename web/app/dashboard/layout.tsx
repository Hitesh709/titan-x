"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/contexts/AuthContext"
import { startLiveTicker } from "@/lib/live"
import api from "@/lib/api"
import type { PaginatedResponse } from "@/types"
import { LayoutDashboard, BarChart3, Briefcase, TrendingUp, Newspaper, Bell, Star, Settings, LogOut, ChevronLeft, ChevronRight, Search, Target, Brain, Activity, Menu, TestTube, Loader2, Crown } from "lucide-react"

interface CompanySearchResult { symbol: string; company_name: string; sector: string | null; exchange: string }
const sidebarItems = [
  { icon: LayoutDashboard, label: "Overview", href: "/dashboard" }, { icon: TrendingUp, label: "Markets", href: "/dashboard/markets" },
  { icon: Briefcase, label: "Portfolio", href: "/dashboard/portfolio" }, { icon: BarChart3, label: "Analysis", href: "/dashboard/analysis" },
  { icon: Target, label: "Research", href: "/dashboard/research" }, { icon: Brain, label: "Recommendations", href: "/dashboard/recommendations" },
  { icon: Crown, label: "Premium", href: "/dashboard/subscription" }, { icon: Newspaper, label: "News & Insights", href: "/dashboard/news" },
  { icon: Activity, label: "Trading", href: "/dashboard/trading" }, { icon: TestTube, label: "Backtesting", href: "/dashboard/backtest" },
  { icon: Target, label: "Screener", href: "/dashboard/screener" }, { icon: Star, label: "Watchlists", href: "/dashboard/watchlists" },
  { icon: Bell, label: "Alerts", href: "/dashboard/alerts" }, { icon: Settings, label: "Settings", href: "/dashboard/settings" },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false), [mobileOpen, setMobileOpen] = useState(false), [sendingVerification, setSendingVerification] = useState(false)
  const [search, setSearch] = useState(""), [searchResults, setSearchResults] = useState<CompanySearchResult[]>([]), [searchOpen, setSearchOpen] = useState(false), [searching, setSearching] = useState(false)
  const searchBoxRef = useRef<HTMLDivElement>(null), searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pathname = usePathname(), router = useRouter(), { user, logout, loading, sendVerification } = useAuth()
  useEffect(() => { if (!loading && !user) router.replace("/login") }, [loading, user, router])
  useEffect(() => startLiveTicker(), [])
  useEffect(() => () => { if (searchTimer.current) clearTimeout(searchTimer.current) }, [])
  useEffect(() => { if (!searchOpen) return; const fn = (e: MouseEvent) => { if (searchBoxRef.current && !searchBoxRef.current.contains(e.target as Node)) setSearchOpen(false) }; document.addEventListener("mousedown", fn); return () => document.removeEventListener("mousedown", fn) }, [searchOpen])
  const runSearch = useCallback(async (q: string) => { const term = q.trim(); if (!term) { setSearchResults([]); setSearching(false); return }; setSearching(true); try { const res = await api.get<PaginatedResponse<CompanySearchResult>>(`/companies?search=${encodeURIComponent(term)}&exchange=NSE&limit=8&order_by=symbol`); setSearchResults(res.items ?? []) } catch { setSearchResults([]) } finally { setSearching(false) } }, [])
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => { const value = e.target.value; setSearch(value); setSearchOpen(value.trim().length > 0); if (searchTimer.current) clearTimeout(searchTimer.current); searchTimer.current = setTimeout(() => void runSearch(value), 250) }
  const goToSymbol = (symbol: string) => { setSearch(""); setSearchResults([]); setSearchOpen(false); setMobileOpen(false); router.push(`/dashboard/stocks/${symbol.toUpperCase()}`) }
  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") { if (searchResults.length > 0) goToSymbol(searchResults[0].symbol); else if (search.trim()) goToSymbol(search.trim()) } }
  const handleVerifyClick = async () => { if (!user || sendingVerification) return; setSendingVerification(true); try { const res = await sendVerification(user.email); if (res.verification_url) window.location.href = res.verification_url } catch {} finally { setSendingVerification(false) } }
  if (loading || !user) return <div className="min-h-screen bg-titan-950 flex items-center justify-center"><div className="w-9 h-9 rounded-xl tx-brand-mark flex items-center justify-center"><span className="text-white font-bold text-xs">TX</span></div></div>
  return (
    <div className="min-h-screen flex tx-shell">
      {mobileOpen && <div className="fixed inset-0 z-40 bg-black/65 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside aria-label="Dashboard navigation" className={`fixed lg:static inset-y-0 left-0 z-50 tx-sidebar backdrop-blur-xl flex flex-col transition-all duration-300 ${collapsed ? "w-[68px]" : "w-60"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="tx-brand flex items-center px-4"><Link href="/dashboard" className="flex items-center gap-3 min-w-0"><div className="tx-brand-mark flex items-center justify-center shrink-0"><span className="text-white font-bold text-xs">TX</span></div>{!collapsed && <span className="tx-brand-word font-bold text-white truncate">TITAN <span className="text-cyan-300">X</span></span>}</Link></div>
        <nav aria-label="Dashboard sections" className="flex-1 overflow-y-auto">{sidebarItems.map((item) => { const isActive = pathname === item.href, premium = item.label === "Premium"; return <Link key={item.href} href={item.href} className={isActive ? "sidebar-link-active group flex items-center gap-3 px-3" : "sidebar-link group flex items-center gap-3 px-3"} title={collapsed ? item.label : undefined} aria-current={isActive ? "page" : undefined} onClick={() => setMobileOpen(false)}><item.icon size={19} className="shrink-0" />{!collapsed && <span className="text-sm truncate">{item.label}</span>}{!collapsed && premium && <span className="ml-auto text-[9px] uppercase tracking-wider text-purple-300">AI</span>}</Link> })}</nav>
        <div className="p-3 border-t border-blue-900/30">{!collapsed && user && <div className="px-3 py-2 mb-2"><div className="text-sm text-white font-medium truncate">{user.username || user.email}</div><div className="text-[10px] text-slate-500 truncate">{user.email}</div></div>}<button onClick={logout} className="sidebar-link w-full flex items-center gap-3 px-3" title={collapsed ? "Sign Out" : undefined} aria-label="Sign out"><LogOut size={19} className="shrink-0" />{!collapsed && <span className="text-sm">Sign Out</span>}</button></div>
      </aside>
      <div className="flex-1 flex flex-col min-w-0">
        <header className="tx-topbar flex items-center justify-between px-4 lg:px-6 backdrop-blur-xl sticky top-0 z-30">
          <div className="flex items-center gap-3 min-w-0"><button onClick={() => setMobileOpen(true)} className="lg:hidden text-gray-400 hover:text-white" aria-label="Open navigation menu"><Menu size={20} /></button><button onClick={() => setCollapsed(!collapsed)} className="hidden lg:flex text-gray-500 hover:text-white" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}</button><div className="relative flex-1 min-w-0 sm:flex-none sm:ml-2" ref={searchBoxRef}><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-cyan-500" /><input type="text" value={search} onChange={handleSearchChange} onKeyDown={handleSearchKeyDown} onFocus={() => setSearchOpen(search.trim().length > 0)} placeholder="Search NSE scripts (e.g. RELIANCE)…" aria-label="Search NSE scripts" className="tx-search pl-9 pr-9 py-2 text-sm text-gray-300 placeholder-gray-600 focus:outline-none w-full sm:w-80" />{searching && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-cyan-400"><Loader2 size={14} className="animate-spin" /></span>}{searchOpen && <div role="listbox" aria-label="Search results" className="absolute left-0 right-0 top-full mt-2 z-50 rounded-xl bg-slate-950/95 border border-blue-800/40 shadow-2xl backdrop-blur-xl overflow-hidden max-h-80 overflow-y-auto">{searching ? <div className="px-4 py-3 text-xs text-gray-500">Searching…</div> : searchResults.length === 0 ? <div className="px-4 py-3 text-xs text-gray-500">No NSE scripts match “{search}”.</div> : searchResults.map(r => <button key={r.symbol} role="option" onClick={() => goToSymbol(r.symbol)} className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left hover:bg-blue-900/25"><div className="min-w-0"><div className="text-sm text-white font-medium">{r.symbol}</div><div className="text-[11px] text-gray-500 truncate">{r.company_name}</div></div><span className="text-[10px] uppercase text-cyan-400">{r.sector ?? "—"}</span></button>)}</div>}</div></div>
          <div className="flex items-center gap-3 shrink-0 ml-3"><span className="tx-api text-[10px] hidden sm:block">● API CONNECTED</span><div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_10px_rgba(0,240,160,.9)]" /></div>
        </header>
        <main className="tx-content flex-1 p-4 lg:p-6 overflow-auto">{user && !user.is_verified && <div className="mb-4 flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-yellow-500/10 border border-yellow-500/20 text-yellow-300 text-sm"><span>Your email is not verified yet. Some features may be limited until you confirm your address.</span><button onClick={handleVerifyClick} disabled={sendingVerification} className="text-yellow-200 font-medium hover:text-white shrink-0">{sendingVerification ? "Sending..." : "Verify now"}</button></div>}{children}</main>
      </div>
    </div>
  )
}
