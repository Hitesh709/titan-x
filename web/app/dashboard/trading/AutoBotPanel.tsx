"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Bot, Pause, Play, ShieldCheck, Activity, Zap, Clock3 } from "lucide-react"
import api from "@/lib/api"
import { SymbolAutocomplete } from "@/components/dashboard/SymbolAutocomplete"

const MAX_RUNTIME_SECONDS = 15 * 60

interface TechnicalResponse {
  intraday?: { score?: number; direction?: string; label?: string }
  delivery?: { score?: number; direction?: string; label?: string }
}

interface PaperPosition {
  symbol: string
  quantity: number
  average_price?: number
  market_value?: number
  unrealized_pnl?: number
}

interface AutoBotPanelProps {
  initialSymbol?: string
  onSymbolChange?: (symbol: string) => void
}

function normalizeSignal(value: unknown): "BUY" | "SELL" | "WAIT" {
  const text = String(value ?? "").toUpperCase()
  if (text.includes("SELL") || text.includes("BEAR")) return "SELL"
  if (text.includes("BUY") || text.includes("BULL")) return "BUY"
  return "WAIT"
}

export default function AutoBotPanel({ initialSymbol = "RELIANCE", onSymbolChange }: AutoBotPanelProps) {
  const [symbol, setSymbol] = useState(initialSymbol || "RELIANCE")
  const [threshold, setThreshold] = useState(85)
  const [quantity, setQuantity] = useState(1)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lastScore, setLastScore] = useState<number | null>(null)
  const [lastDirection, setLastDirection] = useState<"BUY" | "SELL" | "WAIT">("WAIT")
  const [executed, setExecuted] = useState(0)
  const [message, setMessage] = useState("Bot stopped")
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const deadlineRef = useRef(0)
  const runningRef = useRef(false)

  useEffect(() => setSymbol(initialSymbol || "RELIANCE"), [initialSymbol])

  const stopTimers = useCallback(() => {
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
    stopTimerRef.current = null
  }, [])

  useEffect(() => () => stopTimers(), [stopTimers])

  const ensureAccount = useCallback(async () => {
    try {
      await api.get("/paper-trading/account")
    } catch {
      await api.post("/paper-trading/account?initial_capital=100000", {})
    }
  }, [])

  const getSellableQuantity = useCallback(async (sym: string) => {
    const positions = await api.get<PaperPosition[]>("/paper-trading/portfolio")
    const position = (positions ?? []).find((p) => String(p.symbol).toUpperCase() === sym)
    return Math.max(0, Math.floor(Number(position?.quantity ?? 0)))
  }, [])

  const executeOnce = useCallback(async () => {
    const sym = symbol.trim().toUpperCase()
    if (!sym || busy) return
    setBusy(true)
    try {
      const technical = await api.get<TechnicalResponse>(`/technical-strength/${encodeURIComponent(sym)}?resolution=5min`)
      const intradayScore = Number(technical?.intraday?.score ?? 0)
      const deliveryScore = Number(technical?.delivery?.score ?? 0)
      const score = Math.max(intradayScore, deliveryScore)
      const signal = normalizeSignal(technical?.intraday?.direction || technical?.delivery?.direction)
      setLastScore(Number.isFinite(score) ? score : 0)
      setLastDirection(signal)

      if (!Number.isFinite(score) || score < threshold || signal === "WAIT") {
        setMessage(`No trade · ${signal} · ${Number.isFinite(score) ? score.toFixed(0) : "—"}/100`)
        return
      }

      await ensureAccount()
      let tradeQuantity = quantity
      if (signal === "SELL") {
        const sellable = await getSellableQuantity(sym)
        if (sellable <= 0) {
          setMessage(`SELL signal · no ${sym} holding to exit`)
          return
        }
        tradeQuantity = Math.min(quantity, sellable)
      }

      const params = new URLSearchParams({
        symbol: sym,
        side: signal === "BUY" ? "buy" : "sell",
        order_type: "market",
        quantity: String(Math.max(1, tradeQuantity)),
        time_in_force: "day",
      })
      const order = await api.post<{ status?: string; rejection_reason?: string }>(`/paper-trading/orders?${params.toString()}`, {})
      if (order?.status === "rejected") {
        setMessage(order.rejection_reason || "Order rejected")
        return
      }
      setExecuted((v) => v + 1)
      setMessage(`${signal} · paper trade placed`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Auto trade failed")
    } finally {
      setBusy(false)
    }
  }, [busy, ensureAccount, getSellableQuantity, quantity, symbol, threshold])

  const stop = useCallback((reason = "Bot stopped") => {
    stopTimers()
    deadlineRef.current = 0
    runningRef.current = false
    setRemainingSeconds(0)
    setRunning(false)
    setMessage(reason)
  }, [stopTimers])

  const start = () => {
    if (runningRef.current) return
    const sym = symbol.trim().toUpperCase()
    if (!sym) {
      setMessage("Select a stock symbol first")
      return
    }
    stopTimers()
    const deadline = Date.now() + MAX_RUNTIME_SECONDS * 1000
    deadlineRef.current = deadline
    runningRef.current = true
    setRemainingSeconds(MAX_RUNTIME_SECONDS)
    setExecuted(0)
    setRunning(true)
    setMessage("Auto trade command accepted · executing once")
    void executeOnce().finally(() => {
      if (runningRef.current) stop("Auto trade completed")
    })
    stopTimerRef.current = setTimeout(() => stop("15-minute maximum reached · bot stopped"), MAX_RUNTIME_SECONDS * 1000)
  }

  useEffect(() => {
    if (!running) return
    const countdown = window.setInterval(() => {
      const left = Math.max(0, Math.ceil((deadlineRef.current - Date.now()) / 1000))
      setRemainingSeconds(left)
      if (left <= 0) stop("15-minute maximum reached · bot stopped")
    }, 1000)
    return () => clearInterval(countdown)
  }, [running, stop])

  const updateSymbol = (value: string) => {
    const next = value.toUpperCase()
    setSymbol(next)
    onSymbolChange?.(next)
  }
  const mins = Math.floor(remainingSeconds / 60)
  const secs = remainingSeconds % 60

  return (
    <section className="glass-card p-5 border border-titan-500/20 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-titan-500/5 via-transparent to-fuchsia-500/5 pointer-events-none" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Bot size={17} className="text-titan-400" /> Auto Bot Trading <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">Paper</span></h3>
            <p className="text-xs text-gray-500 mt-1">One automatic BUY/SELL decision per user command using the current Titan-X technical signal.</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500"><ShieldCheck size={14} className="text-emerald-400" /> 15-minute safety window</div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-[10px] text-gray-500 mb-1">Search stock</label>
            <SymbolAutocomplete value={symbol} onChange={updateSymbol} placeholder="Search symbol" className="w-full" />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Min technical</label>
            <input type="number" min={70} max={100} value={threshold} onChange={(e) => setThreshold(Math.min(100, Math.max(70, Number(e.target.value) || 85)))} className="input-field w-full text-sm" disabled={running} />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Quantity</label>
            <input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))} className="input-field w-full text-sm" disabled={running} />
          </div>
          <div>
            {running ? <button onClick={() => stop()} className="w-full px-4 py-2 rounded-lg text-sm font-semibold border border-red-500/30 bg-red-500/10 text-red-400 inline-flex items-center justify-center gap-2"><Pause size={14} /> Stop</button> : <button onClick={start} disabled={busy} className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-titan-500 text-white inline-flex items-center justify-center gap-2 disabled:opacity-50"><Play size={14} /> Auto Trade Now</button>}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Technical</div><div className="text-lg font-bold text-white">{lastScore == null ? "—" : `${lastScore.toFixed(0)}/100`}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Signal</div><div className="text-lg font-bold text-titan-300">{lastDirection}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Executed</div><div className="text-lg font-bold text-white">{executed}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Window</div><div className="text-lg font-bold text-white flex items-center gap-1"><Clock3 size={14} />{running ? `${mins}:${String(secs).padStart(2, "0")}` : "15:00 max"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Status</div><div className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mt-1"><Activity size={12} className={running ? "text-emerald-400" : "text-gray-500"} />{message}</div></div>
        </div>

        <div className="mt-4 flex items-start gap-2 text-[10px] leading-4 text-gray-500"><Zap size={12} className="mt-0.5 shrink-0 text-titan-400" /><span>Paper trading only. The command performs one live-signal evaluation and one paper order when the signal passes the configured technical threshold. It does not promise a return.</span></div>
      </div>
    </section>
  )
}
