"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Bot, Pause, Play, ShieldCheck, Activity, Clock3, TrendingUp } from "lucide-react"
import api from "@/lib/api"
import { SymbolAutocomplete } from "@/components/dashboard/SymbolAutocomplete"

const MAX_RUNTIME_SECONDS = 15 * 60
const CYCLE_SECONDS = 60

interface AutoBotPanelProps { initialSymbol?: string; onSymbolChange?: (symbol: string) => void }
interface CycleResult { cycle: number; action: "BUY" | "SELL" | "HOLD"; price?: number; price_source?: string; quantity?: number; reason?: string; strategy?: { confidence?: number; action?: string; metadata?: Record<string, unknown> }; order?: { status?: string; price?: number; rejection_reason?: string } }

export default function AutoBotPanel({ initialSymbol = "RELIANCE", onSymbolChange }: AutoBotPanelProps) {
  const [symbol, setSymbol] = useState(initialSymbol || "RELIANCE")
  const [amount, setAmount] = useState(10000)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [cycle, setCycle] = useState(0)
  const [executed, setExecuted] = useState(0)
  const [last, setLast] = useState<CycleResult | null>(null)
  const [message, setMessage] = useState("Bot stopped")
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cycleRef = useRef(0)
  const runningRef = useRef(false)

  useEffect(() => setSymbol(initialSymbol || "RELIANCE"), [initialSymbol])
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  const runCycle = useCallback(async (nextCycle: number) => {
    if (busy || !runningRef.current) return
    setBusy(true)
    try {
      const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase(), cycle: String(nextCycle), trade_amount: String(amount) })
      const result = await api.post<CycleResult>(`/auto-demo-bot/cycle?${params.toString()}`, {})
      setLast(result)
      setCycle(nextCycle)
      if (result.action === "BUY" || result.action === "SELL") setExecuted((v) => v + 1)
      const source = result.price_source === "LIVE_REFERENCE" ? "LIVE LTP" : result.price_source === "DEMO_MARKET" ? "DEMO PRICE" : "REFERENCE"
      const p = result.price ? `₹${result.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"
      setMessage(`${result.action} · ${p} · ${source}${result.quantity ? ` · ${result.quantity} qty` : ""}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Auto demo cycle failed")
    } finally { setBusy(false) }
  }, [amount, busy, symbol])

  const stop = useCallback((reason = "Bot stopped") => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    runningRef.current = false
    setRunning(false)
    setRemainingSeconds(0)
    setMessage(reason)
  }, [])

  const start = () => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) { setMessage("Select a stock symbol first"); return }
    if (!Number.isFinite(amount) || amount <= 0) { setMessage("Enter a valid demo trade amount"); return }
    if (runningRef.current) return
    cycleRef.current = 1
    runningRef.current = true
    setCycle(0)
    setExecuted(0)
    setLast(null)
    setRunning(true)
    setRemainingSeconds(MAX_RUNTIME_SECONDS)
    setMessage("Demo bot started · fetching market price and strategy")
    void runCycle(1)
    timerRef.current = setInterval(() => {
      if (!runningRef.current) return
      cycleRef.current += 1
      if (cycleRef.current > 15) { stop("15-minute demo completed"); return }
      void runCycle(cycleRef.current)
    }, CYCLE_SECONDS * 1000)
  }

  useEffect(() => {
    if (!running) return
    const countdown = window.setInterval(() => {
      setRemainingSeconds((current) => {
        const next = Math.max(0, current - 1)
        if (next === 0) stop("15-minute demo completed")
        return next
      })
    }, 1000)
    return () => clearInterval(countdown)
  }, [running, stop])

  const updateSymbol = (value: string) => { const next = value.toUpperCase(); setSymbol(next); onSymbolChange?.(next) }
  const mins = Math.floor(remainingSeconds / 60), secs = remainingSeconds % 60
  const confidence = Number(last?.strategy?.confidence ?? 0)

  return (
    <section className="glass-card p-5 border border-titan-500/20 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-titan-500/5 via-transparent to-fuchsia-500/5 pointer-events-none" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Bot size={17} className="text-titan-400" /> Auto Bot Trading <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Demo Money</span></h3>
            <p className="text-xs text-gray-500 mt-1">15-minute automatic BUY → SELL → BUY → SELL paper execution.</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500"><ShieldCheck size={14} className="text-emerald-400" /> No real broker orders</div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div className="col-span-2 md:col-span-1"><label className="block text-[10px] text-gray-500 mb-1">Stock</label><SymbolAutocomplete value={symbol} onChange={updateSymbol} placeholder="Search symbol" className="w-full" /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Demo trade amount (₹)</label><input type="number" min={1} step={1000} value={amount} onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))} className="input-field w-full text-sm" disabled={running} /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Cycle</label><div className="input-field w-full text-sm text-white">{cycle || 0}/15</div></div>
          <div>{running ? <button onClick={() => stop()} className="w-full px-4 py-2 rounded-lg text-sm font-semibold border border-red-500/30 bg-red-500/10 text-red-400 inline-flex items-center justify-center gap-2"><Pause size={14} /> Stop</button> : <button onClick={start} disabled={busy} className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-titan-500 text-white inline-flex items-center justify-center gap-2 disabled:opacity-50"><Play size={14} /> Start 15-Min Bot</button>}</div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Last price</div><div className="text-lg font-bold text-white">{last?.price ? `₹${last.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Action</div><div className="text-lg font-bold text-titan-300">{last?.action ?? "WAIT"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Trades</div><div className="text-lg font-bold text-white">{executed}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Strategy</div><div className="text-lg font-bold text-white flex items-center gap-1"><TrendingUp size={14} />{confidence ? `${Math.round(confidence * 100)}%` : "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Window</div><div className="text-lg font-bold text-white flex items-center gap-1"><Clock3 size={14} />{running ? `${mins}:${String(secs).padStart(2, "0")}` : "15:00"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Status</div><div className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mt-1"><Activity size={12} className={running ? "text-emerald-400" : "text-gray-500"} />{message}</div></div>
        </div>

        <div className="mt-4 text-[10px] leading-4 text-gray-500">Reference price is the configured market-data LTP when available. If demo/mock data is configured or no live quote is available, the engine uses a clearly labelled synthetic demo price. The existing advanced SMA + RSI + ATR strategy supplies confidence and risk metadata; execution remains paper-only.</div>
      </div>
    </section>
  )
}
