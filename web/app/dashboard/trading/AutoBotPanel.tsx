"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Activity, Bot, Pause, Play, ShieldCheck, Target, TrendingUp } from "lucide-react"
import api from "@/lib/api"

interface AutoBotPanelProps { initialSymbol?: string; onSymbolChange?: (symbol: string) => void }
interface TradeResult { symbol: string; action: string; quantity: number; price: number; allocated_amount?: number; stop_loss_price?: number; score?: number; technical_score?: number; predicted_return_pct?: number; price_source?: string }
interface BotResult { action: "TRADE" | "WAIT"; reason?: string; strategy_window: string; continuous: boolean; universe_candidates?: number; eligible_candidates?: number; selected_candidates?: number; profile_ratio?: number; max_trades_per_burst?: number; stop_loss_max_pct?: number; protected_positions?: TradeResult[]; trades?: TradeResult[] }

const POLL_MS = 15000

export default function AutoBotPanel({ initialSymbol = "RELIANCE" }: AutoBotPanelProps) {
  const [amount, setAmount] = useState(10000)
  const [profileRatio, setProfileRatio] = useState(1)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [executed, setExecuted] = useState(0)
  const [last, setLast] = useState<BotResult | null>(null)
  const [message, setMessage] = useState("Bot stopped")
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const runningRef = useRef(false)
  const busyRef = useRef(false)

  const runBot = useCallback(async () => {
    if (busyRef.current || !runningRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      const params = new URLSearchParams({ trade_amount: String(amount), profile_ratio: String(profileRatio) })
      const result = await api.post<BotResult>(`/auto-demo-bot/run?${params.toString()}`, {})
      setLast(result)
      const trades = result.trades ?? []
      if (trades.length) setExecuted((value) => value + trades.length)
      setMessage(
        result.action === "TRADE"
          ? `${trades.length} trade${trades.length === 1 ? "" : "s"} · ${trades.slice(0, 4).map((t) => `${t.symbol} ${t.action}`).join(" · ")}`
          : result.reason ?? "No qualified trade",
      )
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Auto bot run failed")
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [amount, profileRatio])

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    runningRef.current = false
    setRunning(false)
    setMessage("Bot stopped")
  }, [])

  const start = () => {
    if (!Number.isFinite(amount) || amount <= 0) { setMessage("Enter a valid trading amount"); return }
    if (runningRef.current) return
    runningRef.current = true
    setRunning(true)
    setExecuted(0)
    setLast(null)
    setMessage("Bot started · scanning the market for the best qualified stocks")
    void runBot()
    timerRef.current = setInterval(() => { void runBot() }, POLL_MS)
  }

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  const trades = last?.trades ?? []
  const protectedPositions = last?.protected_positions ?? []

  return (
    <section className="glass-card p-5 border border-titan-500/20 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-titan-500/5 via-transparent to-fuchsia-500/5 pointer-events-none" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Bot size={17} className="text-titan-400" /> Auto Bot Trading <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Demo Money</span></h3>
            <p className="text-xs text-gray-500 mt-1">Continuous multi-stock algorithm · 3-hour strategy window · best-value ranking · paper execution.</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500"><ShieldCheck size={14} className="text-emerald-400" /> No real broker orders</div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div><label className="block text-[10px] text-gray-500 mb-1">Trading capital (₹)</label><input type="number" min={1} step={1000} value={amount} onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))} className="input-field w-full text-sm" disabled={running} /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Profile ratio</label><input type="number" min={0.2} max={20} step={0.1} value={profileRatio} onChange={(e) => setProfileRatio(Math.max(0.2, Math.min(20, Number(e.target.value) || 1)))} className="input-field w-full text-sm" disabled={running} /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Strategy window</label><div className="input-field w-full text-sm text-white flex items-center gap-2"><Target size={14} /> 3 hours</div></div>
          <div>{running ? <button onClick={stop} className="w-full px-4 py-2 rounded-lg text-sm font-semibold border border-red-500/30 bg-red-500/10 text-red-400 inline-flex items-center justify-center gap-2"><Pause size={14} /> Stop</button> : <button onClick={start} disabled={busy} className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-titan-500 text-white inline-flex items-center justify-center gap-2 disabled:opacity-50"><Play size={14} /> Start Auto Bot</button>}</div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Candidates</div><div className="text-lg font-bold text-white">{last?.universe_candidates ?? "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Qualified</div><div className="text-lg font-bold text-white">{last?.eligible_candidates ?? "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Trades this run</div><div className="text-lg font-bold text-titan-300">{trades.length}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Total executions</div><div className="text-lg font-bold text-white flex items-center gap-1"><TrendingUp size={14} />{executed}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Stop loss</div><div className="text-lg font-bold text-amber-300">Max 40%</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Status</div><div className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mt-1"><Activity size={12} className={running ? "text-emerald-400" : "text-gray-500"} />{busy ? "Analysing…" : message}</div></div>
        </div>

        {trades.length > 0 && <div className="mt-4 rounded-lg border border-white/5 bg-white/[0.02] p-3"><div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Selected trades</div><div className="grid md:grid-cols-2 gap-2">{trades.slice(0, 12).map((trade) => <div key={`${trade.symbol}-${trade.action}`} className="flex items-center justify-between rounded-md bg-white/[0.03] px-3 py-2 text-xs"><span className="font-semibold text-white">{trade.symbol}</span><span className="text-emerald-400">{trade.action} {trade.quantity}</span><span className="text-gray-400">₹{trade.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span><span className="text-amber-300">SL ₹{trade.stop_loss_price?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>)}</div></div>}
        {protectedPositions.length > 0 && <div className="mt-3 text-[10px] text-amber-300">{protectedPositions.length} position(s) exited by the 40% maximum-loss protection.</div>}

        <div className="mt-4 text-[10px] leading-4 text-gray-500">The bot does not trade a manually selected stock. It continuously ranks qualified market candidates, checks the 3-hour intraday context, allocates capital by score/profile ratio, and trades only when the algorithm finds a qualified opportunity. The 40% maximum loss protection is enforced before/while managing open bot positions.</div>
      </div>
    </section>
  )
}
