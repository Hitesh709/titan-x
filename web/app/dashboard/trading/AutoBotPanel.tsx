"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Bot, Pause, Play, ShieldCheck, Activity, Zap } from "lucide-react"
import api from "@/lib/api"

const INTERVALS = [60, 300] as const

interface TechnicalResponse {
  intraday?: { score?: number; direction?: string; label?: string }
  delivery?: { score?: number; direction?: string; label?: string }
}

interface AutoBotPanelProps {
  initialSymbol?: string
  onSymbolChange?: (symbol: string) => void
}

export default function AutoBotPanel({ initialSymbol = "RELIANCE", onSymbolChange }: AutoBotPanelProps) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [intervalSeconds, setIntervalSeconds] = useState<number>(60)
  const [maxTrades, setMaxTrades] = useState(1)
  const [threshold, setThreshold] = useState(85)
  const [quantity, setQuantity] = useState(1)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lastScore, setLastScore] = useState<number | null>(null)
  const [lastDirection, setLastDirection] = useState("WAIT")
  const [executed, setExecuted] = useState(0)
  const [message, setMessage] = useState("Bot stopped")
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setSymbol(initialSymbol || "RELIANCE")
  }, [initialSymbol])

  const stopTimer = useCallback(() => {
    if (timer.current) clearInterval(timer.current)
    timer.current = null
  }, [])

  useEffect(() => () => stopTimer(), [stopTimer])

  const runCycle = useCallback(async () => {
    const sym = symbol.trim().toUpperCase()
    if (!sym || busy) return
    setBusy(true)
    try {
      const technical = await api.get<TechnicalResponse>(`/technical-strength/${encodeURIComponent(sym)}?resolution=5min`)
      const score = Math.max(
        Number(technical?.intraday?.score ?? 0),
        Number(technical?.delivery?.score ?? 0),
      )
      const direction = String(technical?.intraday?.direction ?? technical?.delivery?.direction ?? "WAIT").toUpperCase()
      setLastScore(Number.isFinite(score) ? score : 0)
      setLastDirection(direction)

      const isBuy = direction.includes("BUY") || direction.includes("BULL")
      const isSell = direction.includes("SELL") || direction.includes("BEAR")
      if (score < threshold || (!isBuy && !isSell)) {
        setMessage(`No trade · ${direction} · ${score.toFixed(0)}/100`)
        return
      }

      await api.get("/paper-trading/account")
      let placed = 0
      for (let i = 0; i < Math.min(maxTrades, 100); i += 1) {
        const params = new URLSearchParams({
          symbol: sym,
          side: isBuy ? "buy" : "sell",
          order_type: "market",
          quantity: String(quantity),
          time_in_force: "day",
        })
        const order = await api.post<{ status?: string; rejection_reason?: string }>(`/paper-trading/orders?${params.toString()}`, {})
        if (order?.status === "rejected") break
        placed += 1
      }
      setExecuted((v) => v + placed)
      setMessage(placed ? `${isBuy ? "BUY" : "SELL"} · ${placed} paper trade${placed > 1 ? "s" : ""} placed` : "Order rejected")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Bot cycle failed")
    } finally {
      setBusy(false)
    }
  }, [busy, maxTrades, quantity, symbol, threshold])

  const start = () => {
    if (running) return
    setRunning(true)
    setMessage("Bot running · scanning market")
    void runCycle()
    timer.current = setInterval(() => void runCycle(), intervalSeconds * 1000)
  }

  const stop = () => {
    stopTimer()
    setRunning(false)
    setMessage("Bot stopped")
  }

  const updateSymbol = (value: string) => {
    const next = value.toUpperCase()
    setSymbol(next)
    onSymbolChange?.(next)
  }

  return (
    <section className="glass-card p-5 border border-titan-500/20 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-titan-500/5 via-transparent to-fuchsia-500/5 pointer-events-none" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Bot size={17} className="text-titan-400" /> Auto Bot Trading
              <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">Paper</span>
            </h3>
            <p className="text-xs text-gray-500 mt-1">High-confidence technical execution using Titan-X signals.</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            <ShieldCheck size={14} className="text-emerald-400" /> Risk-controlled simulation
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Symbol</label>
            <input value={symbol} onChange={(e) => updateSymbol(e.target.value)} className="input-field w-full text-sm" placeholder="RELIANCE" disabled={running} />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Cycle</label>
            <select value={intervalSeconds} onChange={(e) => setIntervalSeconds(Number(e.target.value))} className="input-field w-full text-sm" disabled={running}>
              <option value={60}>Every 1 min</option>
              <option value={300}>Every 5 min</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Max trades/cycle</label>
            <input type="number" min={1} max={100} value={maxTrades} onChange={(e) => setMaxTrades(Math.min(100, Math.max(1, Number(e.target.value) || 1)))} className="input-field w-full text-sm" disabled={running} />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Min technical score</label>
            <input type="number" min={70} max={100} value={threshold} onChange={(e) => setThreshold(Math.min(100, Math.max(70, Number(e.target.value) || 85)))} className="input-field w-full text-sm" disabled={running} />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Qty/trade</label>
            <input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))} className="input-field w-full text-sm" disabled={running} />
          </div>
          <div>
            {running ? (
              <button onClick={stop} className="w-full px-4 py-2 rounded-lg text-sm font-semibold border border-red-500/30 bg-red-500/10 text-red-400 inline-flex items-center justify-center gap-2"><Pause size={14} /> Stop Bot</button>
            ) : (
              <button onClick={start} className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-titan-500 text-white inline-flex items-center justify-center gap-2"><Play size={14} /> Start Bot</button>
            )}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Technical</div><div className="text-lg font-bold text-white">{lastScore == null ? "—" : `${lastScore.toFixed(0)}/100`}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Signal</div><div className="text-lg font-bold text-titan-300">{lastDirection}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Executed this session</div><div className="text-lg font-bold text-white">{executed}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Status</div><div className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mt-1"><Activity size={12} className={running ? "text-emerald-400" : "text-gray-500"} />{message}</div></div>
        </div>

        <div className="mt-4 flex items-start gap-2 text-[10px] leading-4 text-gray-500">
          <Zap size={12} className="mt-0.5 shrink-0 text-titan-400" />
          <span>This bot currently executes <strong className="text-gray-400">paper trades only</strong>. A 99% profit rate cannot be guaranteed; the score threshold is a signal-strength filter, not a profit promise.</span>
        </div>
      </div>
    </section>
  )
}
