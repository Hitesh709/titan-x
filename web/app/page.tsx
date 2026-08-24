"use client"

import Link from "next/link"
import { useState } from "react"
import { useAuth } from "@/contexts/AuthContext"
import {
  ArrowRight, BarChart3, Brain, Building2, ChevronRight, Cpu, Database,
  Gauge, Globe, Lock, Menu, Shield, Sparkles, TrendingUp, Users,
  X, Zap, LineChart, Target, Activity, CircleDollarSign,
} from "lucide-react"
import MarketTicker from "@/components/landing/MarketTicker"
import MarketBattle from "@/components/landing/MarketBattle"

const features = [
  { icon: Brain, title: "AI Intelligence", desc: "Multi-model AI ensemble for pattern recognition, market regime detection, ranking, prediction and explainability." },
  { icon: BarChart3, title: "Advanced Analytics", desc: "Institutional-grade technical, fundamental, correlation, breadth and risk analytics in one interface." },
  { icon: Globe, title: "Global Markets", desc: "Unified market intelligence across equities, indices, commodities, FX and other major asset classes." },
  { icon: Cpu, title: "Automated Trading", desc: "Backtest, validate and execute strategies with smart routing, real-time controls and audit trails." },
  { icon: Shield, title: "Risk Engine", desc: "Continuous portfolio risk monitoring, drawdown controls, exposure analysis and circuit breakers." },
  { icon: Gauge, title: "HFT Infrastructure", desc: "Event-driven pipelines, WebSockets, Redis and time-series processing designed for speed and scale." },
]

const stats = [
  { value: "60+", label: "Markets & Exchanges", icon: Globe },
  { value: "50TB+", label: "Data Processed", icon: Database },
  { value: "1M+", label: "AI Predictions / Day", icon: Brain },
  { value: "<1ms", label: "Target Processing", icon: Zap },
  { value: "99.98%", label: "Platform Availability", icon: Activity },
  { value: "24/7", label: "Risk Monitoring", icon: Shield },
]

const movers = [
  ["RELIANCE", "+2.34%", "2,854.10"],
  ["TCS", "+1.87%", "4,218.75"],
  ["HDFCBANK", "+1.45%", "1,678.20"],
  ["INFY", "+1.23%", "1,432.60"],
  ["SBIN", "-0.76%", "812.40"],
]

export default function LandingPage() {
  const { isAuthenticated } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <main className="min-h-screen bg-titan-950 text-white overflow-x-hidden">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-titan-950/85 backdrop-blur-2xl border-b border-white/5">
        <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 shrink-0">
            <div className="titan-logo-mark">X</div>
            <div>
              <div className="text-xl font-black tracking-[0.08em]">TITAN <span className="text-titan-400">X</span></div>
              <div className="hidden sm:block text-[8px] text-gray-500 tracking-[0.24em]">AI · DATA · SPEED · PRECISION</div>
            </div>
          </Link>
          <div className="hidden lg:flex items-center gap-7 text-sm text-gray-400">
            <a href="#home" className="hover:text-white transition">Home</a>
            <a href="#markets" className="hover:text-white transition">Markets</a>
            <a href="#ai" className="hover:text-white transition">AI Intelligence</a>
            <a href="#trading" className="hover:text-white transition">Trading</a>
            <a href="#analytics" className="hover:text-white transition">Analytics</a>
            <a href="#risk" className="hover:text-white transition">Risk Engine</a>
            <Link href="/dashboard" className="hover:text-white transition">Platform</Link>
          </div>
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated ? (
              <Link href="/dashboard" className="btn-primary text-sm">Open Platform <ArrowRight size={15} /></Link>
            ) : (
              <><Link href="/login" className="btn-ghost text-sm">Login</Link><Link href="/register" className="btn-primary text-sm">Get Started <ArrowRight size={15} /></Link></>
            )}
          </div>
          <button onClick={() => setMobileMenuOpen((v) => !v)} className="md:hidden text-gray-300">
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-white/5 bg-titan-950/95 p-4 space-y-3">
            {[['#home','Home'],['#markets','Markets'],['#ai','AI Intelligence'],['#trading','Trading'],['#analytics','Analytics'],['#risk','Risk Engine']].map(([href,label]) => (
              <a key={href} href={href} onClick={() => setMobileMenuOpen(false)} className="block py-2 text-gray-300">{label}</a>
            ))}
            <Link href={isAuthenticated ? "/dashboard" : "/register"} className="btn-primary w-full">{isAuthenticated ? "Open Platform" : "Get Started"}</Link>
          </div>
        )}
      </nav>

      <div className="pt-16" id="home"><MarketTicker /></div>

      <section className="relative min-h-[720px] flex items-center overflow-hidden">
        <div className="absolute inset-0 hero-grid" />
        <div className="absolute -top-32 left-1/3 w-[700px] h-[700px] rounded-full bg-blue-600/10 blur-[130px]" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[500px] rounded-full bg-fuchsia-600/10 blur-[120px]" />
        <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 py-16 relative w-full">
          <div className="grid xl:grid-cols-[.82fr_1.18fr] gap-10 xl:gap-12 items-center">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/20 bg-blue-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-blue-300 mb-7"><Sparkles size={14} /> AI-powered financial intelligence</div>
              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-[-0.04em] leading-[.98]">The Future<br />Trades <span className="text-gradient">Smarter</span></h1>
              <p className="mt-7 text-lg sm:text-xl leading-relaxed text-gray-400 max-w-xl">Real-time market intelligence, AI-driven analytics and automated trading infrastructure for modern investors and trading desks.</p>
              <div className="mt-8 flex flex-wrap gap-3 text-xs text-gray-400"><span className="hero-chip"><Target size={13} /> Predict</span><span className="hero-chip"><Brain size={13} /> Analyze</span><span className="hero-chip"><Zap size={13} /> Automate</span><span className="hero-chip"><TrendingUp size={13} /> Execute</span></div>
              <div className="mt-9 flex flex-col sm:flex-row gap-3"><Link href="/register" className="btn-primary text-base px-7 py-3.5">Start Trading Now <ArrowRight size={17} /></Link><Link href="/dashboard" className="btn-secondary text-base px-7 py-3.5"><LineChart size={17} /> Explore Platform</Link></div>
              <div className="mt-7 flex flex-wrap gap-5 text-xs text-gray-500"><span className="inline-flex items-center gap-2"><Lock size={13} /> Secure infrastructure</span><span className="inline-flex items-center gap-2"><Shield size={13} /> Real-time risk controls</span><span className="inline-flex items-center gap-2"><Activity size={13} /> Live market engine</span></div>
            </div>
            <div className="xl:-mr-8"><MarketBattle /></div>
          </div>
        </div>
      </section>

      <section id="markets" className="border-y border-white/5 bg-black/15 py-5">
        <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap justify-center gap-5 sm:gap-10 text-xs text-gray-500"><span className="inline-flex items-center gap-2"><span className="status-dot" /> LIVE MARKET DATA</span><span>GLOBAL EQUITIES</span><span>INDEX INTELLIGENCE</span><span>AI SIGNALS</span><span>PORTFOLIO RISK</span><span>AUTOMATED EXECUTION</span></div>
      </section>

      <section id="ai" className="py-20 sm:py-24">
        <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="section-heading"><div className="section-kicker">ONE INTELLIGENCE LAYER</div><h2>Everything an Investment Desk Needs</h2><p>From live market data to AI signals, execution, analytics and risk — unified in one high-performance platform.</p></div>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">{features.map((feature) => <div key={feature.title} className="tech-card group"><div className="tech-icon"><feature.icon size={25} /></div><div className="flex-1"><h3>{feature.title}</h3><p>{feature.desc}</p></div><ChevronRight className="tech-arrow" size={18} /></div>)}</div>
        </div>
      </section>

      <section id="analytics" className="py-20 border-t border-white/5 bg-[#020612]">
        <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="section-heading"><div className="section-kicker">INSTITUTIONAL ANALYTICS</div><h2>A Living Market Command Center</h2><p>Dark glass, high-density data and real-time signals — built around the TITAN X trading engine.</p></div>
          <div className="grid xl:grid-cols-[1.05fr_1.2fr_.9fr] gap-5">
            <div className="dashboard-card min-h-[360px]"><div className="panel-title"><span>GLOBAL MARKETS</span><span className="live-label"><i /> LIVE</span></div><div className="world-map"><div className="map-orb map-orb-1" /><div className="map-orb map-orb-2" /><div className="map-orb map-orb-3" /><div className="map-line" /><div className="map-label">60+ EXCHANGES</div></div><div className="market-list">{[['NSE','India'],['BSE','India'],['NASDAQ','US'],['NYSE','US'],['LSE','UK'],['JPX','Japan']].map(([a,b]) => <div key={a}><span>{a} <small>{b}</small></span><b>OPEN</b></div>)}</div></div>
            <div className="dashboard-card min-h-[360px]"><div className="panel-title"><span>AI PREDICTION ENGINE</span><span className="live-label"><i /> LIVE</span></div><div className="prediction-top"><div><small>NIFTY 50 · 15 MIN</small><strong>AI SIGNAL</strong></div><div className="prediction-badge">BUY<br /><b>87% CONFIDENCE</b></div></div><div className="chart-area"><div className="chart-grid" /><svg viewBox="0 0 700 250" preserveAspectRatio="none" className="chart-svg"><polyline points="0,190 55,165 90,178 135,140 180,155 230,110 275,130 325,95 370,118 420,70 465,90 515,58 560,82 610,35 700,20" /></svg><div className="chart-target">PREDICTED MOVE<br /><b>+1.32%</b></div></div><div className="signal-row"><span>CONFIDENCE <b>87%</b></span><span>TARGET <b>25,150</b></span><span>STOP <b>24,250</b></span></div></div>
            <div className="dashboard-card min-h-[360px]"><div className="panel-title"><span>TOP AI MOVERS</span><span className="live-label"><i /> LIVE</span></div><div className="movers-list">{movers.map(([name,change,price]) => { const up = change.startsWith('+'); return <div key={name} className="mover-row"><div><b>{name}</b><small>{price}</small></div><span className={up ? 'is-up' : 'is-down'}>{change}</span></div> })}</div><div className="sentiment-mini"><div><span>AI MARKET SENTIMENT</span><strong>78</strong></div><div className="sentiment-bar"><i /></div><small>Momentum · News · Technical · Volume</small></div></div>
          </div>
        </div>
      </section>

      <section id="trading" className="py-20 sm:py-24"><div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8"><div className="grid lg:grid-cols-2 gap-10 items-center"><div><div className="section-kicker">AUTOMATION + EXECUTION</div><h2 className="text-4xl sm:text-5xl font-black tracking-tight mt-3">From Signal to Execution.</h2><p className="text-gray-400 text-lg leading-relaxed mt-5 max-w-xl">TITAN X connects prediction, validation, risk controls, portfolio intelligence and execution into one continuous decision workflow.</p><div className="mt-8 space-y-4">{[['01','Predict','AI ensemble detects regime, momentum and opportunity.'],['02','Validate','Technical, fundamental, news and risk layers cross-check the idea.'],['03','Execute','Smart routing and real-time controls manage the trade lifecycle.']].map(([n,t,d]) => <div key={n} className="flow-row"><span>{n}</span><div><b>{t}</b><p>{d}</p></div></div>)}</div></div><div className="execution-visual"><div className="execution-orbit orbit-a" /><div className="execution-orbit orbit-b" /><div className="execution-core"><Zap size={38} /><span>AI<br />EXECUTION</span></div><div className="execution-node node-a">SIGNAL</div><div className="execution-node node-b">RISK</div><div className="execution-node node-c">ORDER</div><div className="execution-node node-d">FILL</div></div></div></div></section>

      <section id="risk" className="py-20 border-t border-white/5 bg-[#020612]"><div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8"><div className="section-heading"><div className="section-kicker">PROTECT THE DOWNSIDE</div><h2>Risk Intelligence That Never Sleeps</h2><p>Continuous monitoring across positions, exposure, drawdown, volatility, concentration and market regime.</p></div><div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">{['Portfolio Exposure','Drawdown Control','Volatility Monitor','Real-Time Alerts'].map((item,i) => <div key={item} className="risk-card"><div className="risk-number">0{i+1}</div><Shield size={24} /><h3>{item}</h3><div className="risk-meter"><i style={{ width: `${72+i*6}%` }} /></div><small>AI monitoring active</small></div>)}</div></div></section>

      <section id="stats" className="py-16 border-y border-white/5"><div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-6">{stats.map((stat) => <div key={stat.label} className="stat-card"><stat.icon size={20} /><strong>{stat.value}</strong><span>{stat.label}</span></div>)}</div></section>

      <section className="py-24"><div className="max-w-[1100px] mx-auto px-4 sm:px-6 text-center"><div className="inline-flex items-center gap-2 text-xs uppercase tracking-[.2em] text-blue-300 mb-5"><CircleDollarSign size={14} /> TITAN X PLATFORM</div><h2 className="text-4xl sm:text-6xl font-black tracking-tight">The market moves fast.<br /><span className="text-gradient">Your intelligence should move faster.</span></h2><p className="text-gray-400 text-lg max-w-2xl mx-auto mt-6">Build your workflow around real-time data, AI intelligence and disciplined execution.</p><div className="mt-9 flex justify-center gap-3 flex-wrap"><Link href="/register" className="btn-primary text-base px-8 py-3.5">Start Trading Now <ArrowRight size={17} /></Link><Link href="/dashboard" className="btn-secondary text-base px-8 py-3.5">Open Platform</Link></div></div></section>

      <footer className="border-t border-white/5 py-8"><div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row gap-4 justify-between items-center text-xs text-gray-600"><div className="flex items-center gap-3"><div className="titan-logo-mark titan-logo-small">X</div><span>TITAN X · AI DATA SPEED PRECISION</span></div><div className="flex items-center gap-5"><span><Users size={13} className="inline mr-1" /> Institutional intelligence</span><span><Building2 size={13} className="inline mr-1" /> Built for scale</span></div></div></footer>
    </main>
  )
}
