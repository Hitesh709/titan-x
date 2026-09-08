"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Activity, Bot, Pause, Play, ShieldCheck, Target, TrendingUp, Wallet } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import { formatCurrency, getChangeColor } from "@/lib/utils"

interface AutoBotPanelProps { initialSymbol?: string; onSymbolChange?: (symbol: string) => void }
interface TradeResult { symbol: string; action: string; quantity: number; price: number; allocated_amount?: number; stop_loss_price?: number; take_profit_price?: number; score?: number; technical_score?: number; predicted_return_pct?: number; price_source?: string }
interface BotResult { action: "TRADE" | "WAIT"; reason?: string; strategy_window: string; continuous: boolean; universe_candidates?: number; eligible_candidates?: number; selected_candidates?: number; profile_ratio?: number; max_trades_per_burst?: number; stop_loss_pct?: number; take_profit_pct?: number; stop_loss_max_pct?: number; protected_positions?: TradeResult[]; trades?: TradeResult[] }
interface OverviewPosition { symbol: string; quantity: number; average_price: number; current_price: number | null; price_source?: "live" | "eod"; market_value: number; unrealized_pnl: number; unrealized_pnl_pct: number }
interface OverviewSummary { initial_capital: number; cash_balance: number; portfolio_value: number; total_invested: number; total_realized_pnl: number; total_unrealized_pnl: number; total_pnl: number; total_pnl_pct: number; positions_count: number }
interface BotOverview { account: { account_id: number; is_active: boolean } | null; positions: OverviewPosition[]; summary: OverviewSummary }
interface StopResult { sold: number; failed: unknown[]; realized_pnl: number; remaining: number; message: string }

const POLL_MS = 15000

export default function AutoBotPanel({ initialSymbol = "RELIANCE" }: AutoBotPanelProps) {
  const [amount, setAmount] = useState(10000)
  const [profileRatio, setProfileRatio] = useState(1)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [executed, setExecuted] = useState(0)
  const [last, setLast] = useState<BotResult | null>(null)
  const [overview, setOverview] = useState<BotOverview | null>(null)
  const [message, setMessage] = useState("Bot stopped")
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const runningRef = useRef(false)
  const busyRef = useRef(false)

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await api.get<BotOverview>("/auto-demo-bot/overview"))
    } catch {
      /* overview is best-effort; core trading keeps working */
    }
  }, [])
  useLiveRefresh(loadOverview, [loadOverview])

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

  const halt = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    runningRef.current = false
    setRunning(false)
  }, [])

  const squareOff = useCallback(async () => {
    if (stopping) return
    if (!window.confirm("Stop the auto bot and square off ALL current holdings at the live market price?")) return
    setStopping(true)
    try {
      const result = await api.post<StopResult>("/auto-demo-bot/stop", {})
      halt()
      setMessage(result.message)
      await loadOverview()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Stop request failed")
    } finally {
      setStopping(false)
    }
  }, [stopping, halt, loadOverview])

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
  const summary = overview?.summary
  const holdings = overview?.positions ?? []

  return (
    <section className="glass-card p-5 border border-titan-500/20 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-titan-500/5 via-transparent to-fuchsia-500/5 pointer-events-none" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Bot size={17} className="text-titan-400" /> Auto Bot Trading <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Demo Money</span></h3>
            <p className="text-xs text-gray-500 mt-1">Continuous multi-stock algorithm · 3-hour window · 3% stop-loss / 6% take-profit · live price management.</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500"><ShieldCheck size={14} className="text-emerald-400" /> No real broker orders</div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div><label className="block text-[10px] text-gray-500 mb-1">Trading capital (₹)</label><input type="number" min={1} step={1000} value={amount} onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))} className="input-field w-full text-sm" disabled={running} /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Profile ratio</label><input type="number" min={0.2} max={20} step={0.1} value={profileRatio} onChange={(e) => setProfileRatio(Math.max(0.2, Math.min(20, Number(e.target.value) || 1)))} className="input-field w-full text-sm" disabled={running} /></div>
          <div><label className="block text-[10px] text-gray-500 mb-1">Strategy window</label><div className="input-field w-full text-sm text-white flex items-center gap-2"><Target size={14} /> 3 hours</div></div>
          <div>{running ? <button onClick={squareOff} disabled={stopping} className="w-full px-4 py-2 rounded-lg text-sm font-semibold border border-red-500/30 bg-red-500/10 text-red-400 inline-flex items-center justify-center gap-2 disabled:opacity-50"><Pause size={14} /> {stopping ? "Squaring off…" : "Stop & Square Off"}</button> : <button onClick={start} disabled={busy} className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-titan-500 text-white inline-flex items-center justify-center gap-2 disabled:opacity-50"><Play size={14} /> Start Auto Bot</button>}</div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Candidates</div><div className="text-lg font-bold text-white">{last?.universe_candidates ?? "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Qualified</div><div className="text-lg font-bold text-white">{last?.eligible_candidates ?? "—"}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Trades this run</div><div className="text-lg font-bold text-titan-300">{trades.length}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Total executions</div><div className="text-lg font-bold text-white flex items-center gap-1"><TrendingUp size={14} />{executed}</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Risk per trade</div><div className="text-lg font-bold text-amber-300">SL {last?.stop_loss_pct ?? 3}% · TP {last?.take_profit_pct ?? 6}%</div></div>
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3"><div className="text-[10px] text-gray-500">Status</div><div className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mt-1"><Activity size={12} className={running ? "text-emerald-400" : "text-gray-500"} />{busy ? "Analysing…" : message}</div></div>
        </div>

        {summary && (
          <div className="mt-4 rounded-lg border border-white/5 bg-white/[0.02] p-3">
            <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider text-gray-500 mb-2">
              <Wallet size={12} className="text-titan-400" /> Live account <span className="normal-case text-emerald-400">· refreshing every 5s</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><div className="text-[10px] text-gray-500">Portfolio value</div><div className="text-sm font-bold text-white">{formatCurrency(summary.portfolio_value)}</div><div className="text-[10px] text-gray-500 mt-0.5">{summary.positions_count} holdings · {formatCurrency(summary.total_invested)} invested</div></div>
              <div><div className="text-[10px] text-gray-500">Cash</div><div className="text-sm font-bold text-white">{formatCurrency(summary.cash_balance)}</div><div className="text-[10px] text-gray-500 mt-0.5">of {formatCurrency(summary.initial_capital)}</div></div>
              <div><div className="text-[10px] text-gray-500">Live Total P&amp;L</div><div className={`text-sm font-bold ${getChangeColor(summary.total_pnl)}`}>{formatCurrency(summary.total_pnl)} <span className="text-[10px]">({summary.total_pnl_pct >= 0 ? "+" : ""}{summary.total_pnl_pct.toFixed(2)}%)</span></div><div className="text-[10px] text-gray-500 mt-0.5">Unrealized {formatCurrency(summary.total_unrealized_pnl)}</div></div>
              <div><div className="text-[10px] text-gray-500">Realized P&amp;L</div><div className={`text-sm font-bold ${getChangeColor(summary.total_realized_pnl)}`}>{formatCurrency(summary.total_realized_pnl)}</div><div className="text-[10px] text-gray-500 mt-0.5">Cash + closed profits</div></div>
            </div>
            {holdings.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Live holdings</div>
                {holdings.slice(0, 8).map((h) => (
                  <div key={h.symbol} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-white/[0.03] px-3 py-1.5 text-xs">
                    <span className="font-semibold text-white">{h.symbol}</span>
                    <span className="text-gray-400">{h.quantity} @ {formatCurrency(h.average_price)}</span>
                    <span className="text-gray-400">{formatCurrency(h.market_value)}</span>
                    <div className="text-right">
                      <span className={`font-semibold ${getChangeColor(h.unrealized_pnl)}`}>{formatCurrency(h.unrealized_pnl)}</span>
                      <span className="ml-1.5 text-gray-500">({h.unrealized_pnl_pct >= 0 ? "+" : ""}{h.unrealized_pnl_pct.toFixed(2)}%)</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {trades.length > 0 && <div className="mt-4 rounded-lg border border-white/5 bg-white/[0.02] p-3"><div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Selected trades</div><div className="grid md:grid-cols-2 gap-2">{trades.slice(0, 12).map((trade) => <div key={`${trade.symbol}-${trade.action}`} className="flex items-center justify-between rounded-md bg-white/[0.03] px-3 py-2 text-xs"><span className="font-semibold text-white">{trade.symbol}</span><span className="text-emerald-400">{trade.action} {trade.quantity}</span><span className="text-gray-400">₹{trade.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span><span className="text-amber-300">SL ₹{(trade.stop_loss_price ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>)}</div></div>}
        {protectedPositions.length > 0 && <div className="mt-3 text-[10px] text-amber-300">{protectedPositions.length} position(s) exited by the 40% maximum-loss protection.</div>}

        <div className="mt-4 text-[10px] leading-4 text-gray-500">The bot continuously ranks qualified candidates, checks the 3-hour intraday context, allocates capital by score/profile ratio, and places a 3% stop-loss with a 6% take-profit on every entry. Positions are marked to live price every run so stops and targets trigger in real time. Stopping the bot squares off every holding at the live market price.</div>
      </div>
    </section>
  )
}