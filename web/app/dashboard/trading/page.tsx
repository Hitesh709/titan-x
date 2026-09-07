"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Clock, CheckCircle } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PaperAccountSummary, PaperPosition } from "@/types"
import { WidgetError, RefreshButton } from "@/components/dashboard/widget"
import {
  AccountSummary,
  QuickTradeForm,
  HoldingsList,
  OrdersTable,
  type OrderRow,
  type PlacedOrder,
} from "./components"
import AutoBotPanel from "./AutoBotPanel"

const OPEN_STATUSES = ["pending", "open", "partially_filled"]
type LiveQuote = { symbol: string; last_price: number | null; source?: string; live?: boolean }

export default function TradingPage() {
  const [account, setAccount] = useState<PaperAccountSummary | null>(null)
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)
  const [symbol, setSymbol] = useState("")
  const [side, setSide] = useState<"buy" | "sell">("buy")
  const [orderType, setOrderType] = useState<"market" | "limit">("market")
  const [quantity, setQuantity] = useState("")
  const [price, setPrice] = useState("")
  const mounted = useRef(true)
  const positionsRef = useRef<PaperPosition[]>([])

  useEffect(() => { positionsRef.current = positions }, [positions])

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [accRes, posRes, ordRes] = await Promise.allSettled([
        api.get<PaperAccountSummary>("/paper-trading/account"),
        api.get<PaperPosition[]>("/paper-trading/portfolio"),
        api.get<{ items: OrderRow[] }>("/paper-trading/orders?limit=50&skip=0"),
      ])
      if (!mounted.current) return
      const failures: string[] = []
      if (accRes.status === "fulfilled") setAccount(accRes.value)
      else failures.push(accRes.reason instanceof Error ? accRes.reason.message : "Failed to load account")
      if (posRes.status === "fulfilled") setPositions(posRes.value)
      else failures.push(posRes.reason instanceof Error ? posRes.reason.message : "Failed to load portfolio")
      if (ordRes.status === "fulfilled") setOrders(ordRes.value.items ?? [])
      else failures.push(ordRes.reason instanceof Error ? ordRes.reason.message : "Failed to load orders")
      setError(failures.length ? failures.join(" · ") : null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load trading data")
    } finally {
      if (mounted.current) { setLoading(false); setRefreshing(false) }
    }
  }, [])

  const refreshLivePrices = useCallback(async () => {
    const symbols = positionsRef.current.map((p) => p.symbol.trim().toUpperCase()).filter(Boolean)
    if (!symbols.length) return
    try {
      const params = new URLSearchParams({ symbols: [...new Set(symbols)].join(",") })
      const response = await api.get<{ quotes: LiveQuote[] }>(`/live-market/quotes?${params.toString()}`)
      const bySymbol = new Map(
        (response.quotes ?? [])
          .filter((q) => q.last_price != null && Number(q.last_price) > 0)
          .map((q) => [q.symbol.replace(/\.NS$|\.BO$/i, "").toUpperCase(), Number(q.last_price)]),
      )
      if (!bySymbol.size) return
      setPositions((current) => current.map((p) => {
        const live = bySymbol.get(p.symbol.replace(/\.NS$|\.BO$/i, "").toUpperCase())
        return live ? {
          ...p,
          current_price: live,
          market_value: live * p.quantity,
          unrealized_pnl: (live - p.average_price) * p.quantity,
          unrealized_pnl_pct: p.average_price ? Number(((live - p.average_price) / p.average_price * 100).toFixed(2)) : 0,
        } : p
      }))
    } catch {
      // Keep the last known portfolio mark if live quote service is temporarily unavailable.
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    const params = new URLSearchParams(window.location.search)
    const requestedSymbol = params.get("symbol")?.trim().toUpperCase()
    const requestedSide = params.get("side")?.toLowerCase()
    if (requestedSymbol) setSymbol(requestedSymbol)
    if (requestedSide === "buy" || requestedSide === "sell") setSide(requestedSide)
    return () => { mounted.current = false }
  }, [])

  useLiveRefresh(() => { void load(true).then(() => refreshLivePrices()) }, [load, refreshLivePrices])

  const refreshPrices = async () => {
    await refreshLivePrices()
    try { await api.post("/paper-trading/portfolio/refresh", {}) } catch { /* keep live UI marks */ }
  }

  const handleRefresh = () => { setRefreshing(true); load(true).then(() => refreshLivePrices()) }

  const ensureAccount = async () => {
    try { await api.get<PaperAccountSummary>("/paper-trading/account"); return }
    catch (error) {
      const message = error instanceof Error ? error.message : ""
      if (!/no paper account/i.test(message)) throw error
    }
    await api.post("/paper-trading/account?initial_capital=100000", {})
  }

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault(); setFormError(null); setFormSuccess(null)
    const sym = symbol.trim().toUpperCase(); const qty = Number(quantity)
    if (!sym) return setFormError("Enter a symbol (e.g. RELIANCE)")
    if (!qty || qty <= 0) return setFormError("Enter a valid quantity")
    if (orderType === "limit" && (!Number(price) || Number(price) <= 0)) return setFormError("Enter a limit price")
    setSubmitting(true)
    try {
      await ensureAccount()
      const orderParams = new URLSearchParams({ symbol: sym, side, order_type: orderType, quantity: String(qty), time_in_force: "day" })
      if (orderType === "limit" && price) orderParams.set("price", String(Number(price)))
      const placed = await api.post<PlacedOrder>(`/paper-trading/orders?${orderParams.toString()}`, {})
      if (placed.status === "rejected") setFormError(placed.rejection_reason || "Order rejected")
      else { setFormSuccess(`${placed.side.toUpperCase()} ${placed.filled_quantity ?? placed.quantity} ${placed.symbol} @ ${placed.status}`); setQuantity(""); setPrice("") }
      await load(true); await refreshLivePrices()
    } catch (err) { setFormError(err instanceof Error ? err.message : "Failed to place order") }
    finally { setSubmitting(false) }
  }

  const handleCancel = async (id: number) => {
    try { await api.delete(`/paper-trading/orders/${id}`); await load(true); await refreshLivePrices() }
    catch (err) { setFormError(err instanceof Error ? err.message : "Failed to cancel order") }
  }

  const handleSquareOff = async (positionSymbol: string) => {
    const position = positions.find((p) => p.symbol.toUpperCase() === positionSymbol.toUpperCase())
    if (!position) return
    if (!window.confirm(`Square off the entire ${position.quantity} share ${position.symbol} position at market price?`)) return
    setFormError(null); setFormSuccess(null)
    try {
      const result = await api.post<{ id: number; symbol: string; quantity: number; filled_quantity: number; status: string; price: number | null; rejection_reason: string | null; message: string }>(`/paper-trading/portfolio/${encodeURIComponent(position.symbol)}/square-off`, {})
      if (result.status === "rejected") throw new Error(result.rejection_reason || "Square-off order was rejected")
      setFormSuccess(result.status === "filled" ? `${result.symbol} position squared off: ${result.filled_quantity} shares sold${result.price ? ` @ ₹${result.price.toFixed(2)}` : ""}.` : `${result.symbol} square-off order submitted (${result.status}).`)
      await load(true); await refreshLivePrices()
    } catch (err) { setFormError(err instanceof Error ? err.message : "Failed to square off position") }
  }

  const openOrders = orders.filter((o) => OPEN_STATUSES.includes(o.status))
  const orderHistory = orders.filter((o) => !OPEN_STATUSES.includes(o.status)).slice(0, 20)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><div><div className="flex items-center gap-2"><h1 className="text-2xl font-bold text-white">Trading</h1><span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30" title="Simulated trading with virtual cash — no real broker, no real money">Demo · Paper</span></div><p className="text-gray-500 text-sm mt-1">Place paper trades and track your positions, orders, and P&amp;L</p></div><RefreshButton onClick={handleRefresh} spinning={refreshing} /></div>
      {error && <WidgetError message={error} onRetry={() => load(false)} />}
      {loading ? <div className="grid md:grid-cols-3 gap-4"><div className="glass-card p-5 md:col-span-2"><div className="h-24 animate-pulse bg-white/5 rounded-lg" /></div><div className="glass-card p-5"><div className="h-24 animate-pulse bg-white/5 rounded-lg" /></div></div> : <><AccountSummary account={account} /><AutoBotPanel initialSymbol={symbol || "RELIANCE"} onSymbolChange={setSymbol} /><div className="grid lg:grid-cols-2 gap-6"><QuickTradeForm symbol={symbol} side={side} orderType={orderType} quantity={quantity} price={price} onSymbolChange={setSymbol} onSideChange={setSide} onOrderTypeChange={setOrderType} onQuantityChange={setQuantity} onPriceChange={setPrice} onSubmit={handlePlaceOrder} submitting={submitting} formError={formError} formSuccess={formSuccess} /><div className="glass-card p-5"><h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">Current Holdings</h3><HoldingsList positions={positions} onSquareOff={handleSquareOff} /></div></div><div className="grid lg:grid-cols-2 gap-6"><OrdersTable title="Open Orders" icon={<Clock size={16} className="text-titan-400" />} orders={openOrders} onCancel={handleCancel} emptyMessage="No open orders." /><OrdersTable title="Order History" icon={<CheckCircle size={16} className="text-titan-400" />} orders={orderHistory} emptyMessage="No orders yet." /></div></>}
    </div>
  )
}
