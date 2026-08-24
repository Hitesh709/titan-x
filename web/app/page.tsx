"use client"

import Link from "next/link"
import { useAuth } from "@/contexts/AuthContext"
import {
  TrendingUp, Shield, Brain, BarChart3, Globe, Zap,
  LineChart, Wallet, Bell, Puzzle, Database, ArrowRight,
  Menu, X, ChevronRight, Star, Users, Building2, Sparkles,
  Cpu, Gauge, Lock, Layers,
} from "lucide-react"
import { useState } from "react"

const features = [
  { icon: Brain, title: "AI-Powered Intelligence", desc: "Multi-model AI ensemble with real-time learning, pattern recognition, and predictive analytics tuned for institutional-grade accuracy." },
  { icon: BarChart3, title: "Advanced Analytics", desc: "Technical indicators, fundamental analysis, correlation matrices, and risk metrics delivered through interactive dashboards." },
  { icon: Globe, title: "Global Market Coverage", desc: "Real-time data across equities, FX, commodities, and fixed income from 60+ exchanges worldwide with sub-millisecond latency." },
  { icon: Shield, title: "Enterprise Security", desc: "Bank-grade encryption, role-based access control, audit trails, and compliance-ready infrastructure with SOC 2 alignment." },
  { icon: Wallet, title: "Portfolio Optimization", desc: "Modern portfolio theory, risk parity, black-litterman, and custom constraint optimization engines for any investment mandate." },
  { icon: Zap, title: "Ultra-Low Latency", desc: "Edge-optimized infrastructure delivering market data and order execution with microsecond-level processing pipelines." },
  { icon: Bell, title: "Smart Alerts", desc: "Configurable multi-channel alerts for price movements, technical breakouts, news sentiment shifts, and portfolio drift thresholds." },
  { icon: Puzzle, title: "Modular Architecture", desc: "Plugin-based service architecture with REST + WebSocket APIs, allowing seamless integration with existing trading infrastructure." },
  { icon: Database, title: "Time-Series Engine", desc: "Petabyte-scale time-series database optimized for financial data with automatic partitioning, compression, and tiered storage." },
  { icon: Cpu, title: "Automated Trading", desc: "Backtest, validate, and deploy algorithmic strategies across multiple brokers with real-time risk monitoring and circuit breakers." },
  { icon: Layers, title: "Multi-Asset Support", desc: "Unified interface for equities, options, futures, forex, crypto, and fixed income with normalized data models and pricing." },
  { icon: Gauge, title: "Performance Analytics", desc: "Attribution analysis, alpha/beta decomposition, Sharpe ratios, drawdown analysis, and peer comparison benchmarking." },
]

const stats = [
  { value: "$2.4B+", label: "Assets Under Analysis" },
  { value: "99.97%", label: "Platform Uptime" },
  { value: "150μs", label: "Avg. Data Latency" },
  { value: "60+", label: "Exchanges Connected" },
  { value: "12K+", label: "Institutional Users" },
  { value: "500+", label: "AI Models Deployed" },
]

const testimonials = [
  { name: "Marcus Chen", role: "CIO, Horizon Capital", content: "TITAN X transformed our research workflow. The AI ensemble catches patterns our analysts would miss, and the risk engine saved us 8 figures in drawdown protection last quarter alone." },
  { name: "Sarah Mitchell", role: "Head of Trading, Meridian Funds", content: "The latency is exceptional — we're seeing market data before our legacy Bloomberg terminals. The backtesting framework is the most rigorous I've encountered outside of HFT shops." },
  { name: "David Okonkwo", role: "Managing Partner, Aether Investments", content: "We evaluated 15 platforms before choosing TITAN X. The modularity, API-first design, and institutional-grade security made it a clear winner. Six months in, it's indispensable." },
]

export default function LandingPage() {
  const { isAuthenticated } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <div className="min-h-screen bg-titan-950">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-titan-950/80 backdrop-blur-xl border-b border-titan-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-titan-500 to-titan-700 flex items-center justify-center">
                <span className="text-white font-bold text-sm">TX</span>
              </div>
              <span className="text-xl font-bold text-white tracking-tight">TITAN <span className="text-titan-400">X</span></span>
            </Link>
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">Features</a>
              <a href="#stats" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">Performance</a>
              <a href="#testimonials" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">Testimonials</a>
              {isAuthenticated ? (
                <Link href="/dashboard" className="btn-primary text-sm">Dashboard</Link>
              ) : (
                <div className="flex items-center gap-3">
                  <Link href="/login" className="btn-ghost text-sm">Sign In</Link>
                  <Link href="/register" className="btn-primary text-sm">Get Started</Link>
                </div>
              )}
            </div>
            <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="md:hidden text-gray-400 hover:text-white">
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-titan-800/50 bg-titan-950/95 backdrop-blur-xl">
            <div className="px-4 py-4 space-y-3">
              <a href="#features" className="block text-sm text-gray-400 hover:text-white py-2">Features</a>
              <a href="#stats" className="block text-sm text-gray-400 hover:text-white py-2">Performance</a>
              <a href="#testimonials" className="block text-sm text-gray-400 hover:text-white py-2">Testimonials</a>
              {isAuthenticated ? (
                <Link href="/dashboard" className="btn-primary text-sm w-full">Dashboard</Link>
              ) : (
                <div className="flex flex-col gap-3 pt-2">
                  <Link href="/login" className="btn-secondary text-sm w-full">Sign In</Link>
                  <Link href="/register" className="btn-primary text-sm w-full">Get Started</Link>
                </div>
              )}
            </div>
          </div>
        )}
      </nav>

      {/* Hero */}
      <section className="relative pt-28 pb-20 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-titan-900/50 via-transparent to-transparent" />
        <div className="absolute top-1/4 left-1/3 w-[700px] h-[700px] bg-titan-600/10 rounded-full blur-3xl animate-pulse-glow" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
          <div className="grid lg:grid-cols-[1.02fr_.98fr] gap-10 lg:gap-14 items-center">
            <div className="text-left">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-titan-600/10 border border-titan-600/20 text-titan-400 text-sm mb-6">
                <Sparkles size={14} />
                <span>AI-powered market intelligence</span>
              </div>
              <h1 className="text-5xl md:text-6xl xl:text-7xl font-bold tracking-tight mb-6">
                Enterprise Intelligence
                <br />
                <span className="bg-gradient-to-r from-titan-400 via-blue-400 to-titan-300 text-transparent bg-clip-text">for Financial Markets</span>
              </h1>
              <p className="text-lg md:text-xl text-gray-400 max-w-2xl mb-10 leading-relaxed">
                TITAN X is the next-generation AI-powered analytics and trading platform for investors and trading desks.
                Harness real-time market intelligence, AI signals, breakout detection, and advanced execution workflows.
              </p>
              <div className="flex flex-col sm:flex-row items-start gap-4">
                <Link href="/register" className="btn-primary text-lg px-8 py-3">
                  Start Free Trial <ArrowRight size={18} />
                </Link>
                <Link href="#features" className="btn-secondary text-lg px-8 py-3">
                  Explore Platform
                </Link>
              </div>
              <div className="mt-8 flex flex-wrap items-center gap-5 text-sm text-gray-500">
                <span className="flex items-center gap-1.5"><Lock size={14} />Secure Infrastructure</span>
                <span className="flex items-center gap-1.5"><Shield size={14} />Risk Controls</span>
                <span className="flex items-center gap-1.5"><Zap size={14} />Real-Time Signals</span>
              </div>
            </div>

            <div className="relative">
              <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-titan-500/15 via-blue-500/10 to-transparent blur-2xl" />
              <div className="relative overflow-hidden rounded-[1.6rem] border border-titan-700/50 bg-black/30 shadow-2xl shadow-black/40">
                <img
                  src="/titanx-3d-bull.svg"
                  alt="TITAN X 3D bull AI market intelligence"
                  className="w-full h-auto block"
                />
                <div className="absolute top-5 right-5 rounded-2xl border border-emerald-400/30 bg-slate-950/80 backdrop-blur-xl px-5 py-4 min-w-[180px] shadow-xl">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500">AI Market Score</div>
                  <div className="flex items-end gap-2 mt-1">
                    <span className="text-4xl font-black text-white leading-none">92</span>
                    <span className="text-emerald-400 text-xs font-bold mb-1">/ 100</span>
                  </div>
                  <div className="mt-2 text-sm font-semibold text-emerald-300">Very Bullish ↗</div>
                </div>
                <div className="absolute bottom-5 left-5 right-5 grid grid-cols-3 gap-2">
                  {[
                    ["NIFTY 50", "+1.15%"],
                    ["SENSEX", "+1.10%"],
                    ["BANK NIFTY", "+1.35%"],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-cyan-400/20 bg-slate-950/75 backdrop-blur-xl px-3 py-2">
                      <div className="text-[10px] text-gray-500">{label}</div>
                      <div className="text-xs font-bold text-emerald-300 mt-0.5">▲ {value}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between px-2 text-xs text-gray-500">
                <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />AI market engine active</span>
                <span>Live dashboard visual</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section id="stats" className="py-20 border-t border-titan-800/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-3xl font-bold text-white mb-1">{stat.value}</div>
                <div className="text-sm text-gray-500">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Everything an Investment Desk Needs</h2>
            <p className="text-gray-400 max-w-2xl mx-auto text-lg">
              From real-time market data to AI-powered signal generation and automated execution — one unified platform.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature) => (
              <div key={feature.title} className="glass-card p-6 group hover:border-titan-600/40 transition-all duration-300">
                <div className="w-12 h-12 rounded-lg bg-titan-600/10 border border-titan-600/20 flex items-center justify-center mb-4 group-hover:bg-titan-600/20 transition-colors">
                  <feature.icon className="w-6 h-6 text-titan-400" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture Preview */}
      <section className="py-24 border-t border-titan-800/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <div className="badge-blue mb-4 inline-block">Platform Architecture</div>
              <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">Designed for Scale, Built for Speed</h2>
              <p className="text-gray-400 leading-relaxed mb-8">
                TITAN X runs on a modern, cloud-native architecture with microservices, event-driven data pipelines,
                and a multi-model AI inference layer. Every component is horizontally scalable and designed for
                high-frequency financial workloads.
              </p>
              <div className="space-y-4">
                {[
                  { label: "Data Ingestion", desc: "60+ exchange connections with real-time normalization" },
                  { label: "AI Inference", desc: "500+ models across ensemble, ranking, and prediction engines" },
                  { label: "Execution", desc: "Smart order routing with real-time risk checks" },
                ].map((item) => (
                  <div key={item.label} className="flex items-start gap-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-titan-400 mt-2 shrink-0" />
                    <div>
                      <div className="text-white font-medium">{item.label}</div>
                      <div className="text-sm text-gray-500">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="glass-card p-8 relative">
              <div className="aspect-video rounded-lg bg-gradient-to-br from-titan-800/50 to-titan-900/50 border border-titan-700/30 flex items-center justify-center">
                <div className="text-center">
                  <Cpu className="w-16 h-16 text-titan-400/40 mx-auto mb-4" />
                  <div className="text-gray-500 text-sm">Architecture Diagram</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section id="testimonials" className="py-24 border-t border-titan-800/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Trusted by Industry Leaders</h2>
            <p className="text-gray-400 max-w-xl mx-auto">Leading hedge funds, asset managers, and trading desks rely on TITAN X.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {testimonials.map((t) => (
              <div key={t.name} className="glass-card p-6">
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, i) => <Star key={i} size={14} className="fill-yellow-500 text-yellow-500" />)}
                </div>
                <p className="text-gray-300 text-sm leading-relaxed mb-6">"{t.content}"</p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-titan-600/30 flex items-center justify-center text-white font-medium text-sm">
                    {t.name.split(" ").map(n => n[0]).join("")}
                  </div>
                  <div>
                    <div className="text-white text-sm font-medium">{t.name}</div>
                    <div className="text-gray-500 text-xs">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 border-t border-titan-800/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="glass-card p-12 md:p-16 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-titan-600/10 via-titan-500/5 to-transparent" />
            <div className="relative">
              <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Ready to Transform Your Trading?</h2>
              <p className="text-gray-400 max-w-lg mx-auto mb-8">
                Join 500+ institutional desks already using TITAN X to gain a competitive edge.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link href="/register" className="btn-primary text-lg px-8 py-3">
                  Start Free Trial <ArrowRight size={18} />
                </Link>
                <Link href="/login" className="btn-secondary text-lg px-8 py-3">
                  Sign In
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-titan-800/30 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-titan-500 to-titan-700 flex items-center justify-center">
                  <span className="text-white font-bold text-xs">TX</span>
                </div>
                <span className="text-lg font-bold text-white">TITAN X</span>
              </div>
              <p className="text-sm text-gray-500 leading-relaxed">Enterprise intelligence platform for financial markets.</p>
            </div>
            {[
              { title: "Platform", links: ["Features", "Pricing", "API", "Integrations", "Changelog"] },
              { title: "Company", links: ["About", "Careers", "Blog", "Press", "Partners"] },
              { title: "Legal", links: ["Privacy", "Terms", "Security", "Compliance", "SLA"] },
            ].map((col) => (
              <div key={col.title}>
                <h4 className="text-white font-medium mb-4">{col.title}</h4>
                <ul className="space-y-2">
                  {col.links.map((link) => (
                    <li key={link}>
                      <a href="#" className="text-sm text-gray-500 hover:text-gray-300 transition-colors">{link}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="border-t border-titan-800/30 pt-8 text-center text-sm text-gray-600">
            &copy; {new Date().getFullYear()} TITAN X. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  )
}
