"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowRight, Clock, CheckCircle, Loader2, Zap, Trash2, Landmark } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PaperAccountSummary, PaperPosition } from "@/types"
import { formatCurrency, formatPercent, getChangeColor } from "@/lib/utils"
import { WidgetLoading, WidgetError, WidgetEmpty, RefreshButton } from "@/components/dashboard/widget"
import { SymbolAutocomplete } from "@/components/dashboard/SymbolAutocomplete"

interface OrderRow {
  id: number
  symbol: string
  side: string
  order_type: string
  quantity: number
  filled_quantity: number
  price: number | null
  stop_price: number | null
  status: string
  time_in_force: string
  rejection_reason: string | null
  filled_at: string | null
  created_at: string | null
}

interface PlacedOrder {
  id: number
  symbol: string
  side: string
  order_type: string
  quantity: number
  filled_quantity: number
  status: string
  rejection_reason: string | null
}

const OPEN_STATUSES = ["pending", "open", "partially_filled"]

function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

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

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [accRes, posRes, ordRes] = await Promise.allSettled([
        api.get<PaperAccountSummary>("/paper-trading/account"),
        api.get<PaperPosition[]>("/paper-trading/portfolio"),
        api.get<{ items: OrderRow[] }>("/paper-trading/orders?limit=50&skip=0"),
      ])
      if (!mounted.current) return
      if (accRes.status === "fulfilled") setAccount(accRes.value)
      if (accRes.status === "rejected") setError(accRes.reason instanceof Error ? accRes.reason.message : "Failed to load account")
      if (posRes.status === "fulfilled") setPositions(posRes.value)
      if (ordRes.status === "fulfilled") setOrders(ordRes.value.items ?? [])
      else setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load trading data")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  const ensureAccount = async () => {
    try {
      await api.get("/paper-trading/account")
    } catch {
      await api.post("/paper-trading/account?initial_capital=100000", {})
    }
  }

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setFormSuccess(null)

    const sym = symbol.trim().toUpperCase()
    const qty = Number(quantity)
    if (!sym) return setFormError("Enter a symbol (e.g. RELIANCE)")
    if (!qty || qty <= 0) return setFormError("Enter a valid quantity")
    if (orderType === "limit" && (!Number(price) || Number(price) <= 0)) return setFormError("Enter a limit price")

    setSubmitting(true)
    try {
      await ensureAccount()
      const orderParams = new URLSearchParams({
        symbol: sym,
        side,
        order_type: orderType,
        quantity: String(qty),
        time_in_force: "day",
      })
      if (orderType === "limit" && price) {
        orderParams.set("price", String(Number(price)))
      }
      const placed = await api.post<PlacedOrder>(`/paper-trading/orders?${orderParams.toString()}`, {})
      if (placed.status === "rejected") {
        setFormError(placed.rejection_reason || "Order rejected")
      } else {
        setFormSuccess(`${placed.side.toUpperCase()} ${placed.filled_quantity ?? placed.quantity} ${placed.symbol} @ ${placed.status}`)
        setSymbol("")
        setQuantity("")
        setPrice("")
      }
      await load(true)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to place order")
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = async (id: number) => {
    try {
      await api.delete(`/paper-trading/orders/${id}`)
      await load(true)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to cancel order")
    }
  }

  const openOrders = orders.filter((o) => OPEN_STATUSES.includes(o.status))
  const orderHistory = orders.filter((o) => !OPEN_STATUSES.includes(o.status)).slice(0, 20)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Trading</h1>
          <p className="text-gray-500 text-sm mt-1">
            Place paper trades and track your positions, orders, and P&amp;L
          </p>
        </div>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {error && (
        <WidgetError message={error} onRetry={() => load(false)} />
      )}

      {loading ? (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="glass-card p-5 md:col-span-2">
            <WidgetLoading lines={3} />
          </div>
          <div className="glass-card p-5">
            <WidgetLoading lines={4} />
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 mb-1">Portfolio Value</div>
              <div className="text-xl font-bold text-white">
                {formatCurrency(account?.portfolio_value ?? 0)}
              </div>
              <div className="text-xs text-gray-500 mt-1">{account?.positions_count ?? 0} positions</div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 mb-1">Cash</div>
              <div className="text-xl font-bold text-white">
                {formatCurrency(account?.cash_balance ?? 0)}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                of {formatCurrency(account?.initial_capital ?? 0)}
              </div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 mb-1">Total P&amp;L</div>
              <div className={`text-xl font-bold ${getChangeColor(account?.total_pnl ?? 0)}`}>
                {formatCurrency(account?.total_pnl ?? 0)}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Unrealized {formatCurrency(account?.total_unrealized_pnl ?? 0)}
              </div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 mb-1">Total Return</div>
              <div className={`text-xl font-bold ${getChangeColor(account?.total_pnl ?? 0)}`}>
                {formatPercent(account?.total_pnl_pct ?? 0)}
              </div>
              <div className="text-xs text-gray-500 mt-1">Realized {formatCurrency(account?.total_realized_pnl ?? 0)}</div>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Quick Trade */}
            <form onSubmit={handlePlaceOrder} className="glass-card p-5">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Zap size={16} className="text-titan-400" /> Quick Trade
              </h3>
              <div className="flex flex-wrap gap-4 items-end">
                <div className="min-w-[160px]">
                  <label className="block text-xs text-gray-500 mb-1">Symbol</label>
                  <SymbolAutocomplete
                    value={symbol}
                    onChange={setSymbol}
                    placeholder="RELIANCE"
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Side</label>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => setSide("buy")}
                      className={`px-3 py-1.5 rounded text-xs font-medium border ${
                        side === "buy"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          : "bg-white/5 text-gray-400 border-white/10 hover:bg-emerald-500/10 hover:text-emerald-400"
                      }`}
                    >
                      Buy
                    </button>
                    <button
                      type="button"
                      onClick={() => setSide("sell")}
                      className={`px-3 py-1.5 rounded text-xs font-medium border ${
                        side === "sell"
                          ? "bg-red-500/10 text-red-400 border-red-500/30"
                          : "bg-white/5 text-gray-400 border-white/10 hover:bg-red-500/10 hover:text-red-400"
                      }`}
                    >
                      Sell
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Order Type</label>
                  <select
                    value={orderType}
                    onChange={(e) => setOrderType(e.target.value as "market" | "limit")}
                    className="input-field text-sm py-2 px-3 w-28"
                  >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Quantity</label>
                  <input
                    type="number"
                    min={1}
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    className="input-field w-20 text-sm"
                    placeholder="100"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Price</label>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    className="input-field w-24 text-sm"
                    placeholder={orderType === "limit" ? "875.00" : "Auto"}
                    disabled={orderType !== "limit"}
                  />
                </div>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary text-sm px-6 inline-flex items-center gap-2 disabled:opacity-50"
                >
                  {submitting ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                  Place Order
                </button>
              </div>
              {formError && <p className="mt-3 text-xs text-red-400">{formError}</p>}
              {formSuccess && <p className="mt-3 text-xs text-emerald-400">{formSuccess}</p>}
            </form>

            {/* Current Holdings */}
            <div className="glass-card p-5">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Landmark size={16} className="text-titan-400" /> Current Holdings
              </h3>
              {positions.length === 0 ? (
                <WidgetEmpty message="No positions yet. Place a trade to get started." />
              ) : (
                <div className="space-y-2">
                  {positions.map((p) => (
                    <div key={p.symbol} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                      <div>
                        <div className="text-sm font-medium text-white">{p.symbol}</div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {p.quantity} shares @ {formatCurrency(p.average_price)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={getChangeColor(p.unrealized_pnl)}>
                          {formatCurrency(p.unrealized_pnl)}
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">{p.market_value.toFixed(0)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Open Orders */}
            <div className="glass-card p-5">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Clock size={16} className="text-titan-400" /> Open Orders
              </h3>
              {openOrders.length === 0 ? (
                <WidgetEmpty message="No open orders." />
              ) : (
                <div className="space-y-3">
                  {openOrders.map((o) => (
                    <div key={o.id} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">{o.symbol}</span>
                          <span className="badge-blue text-[10px]">
                            {o.order_type} {o.side}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {o.quantity} shares @ {o.price ? `₹${o.price.toFixed(2)}` : "Market"}
                        </div>
                      </div>
                      <div className="text-right flex items-center gap-2">
                        <span className="text-xs font-medium text-yellow-400 uppercase">{o.status}</span>
                        <button
                          onClick={() => handleCancel(o.id)}
                          className="text-gray-500 hover:text-red-400"
                          title="Cancel"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Order History */}
            <div className="glass-card p-5">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle size={16} className="text-titan-400" /> Order History
              </h3>
              {orderHistory.length === 0 ? (
                <WidgetEmpty message="No orders yet." />
              ) : (
                <div className="space-y-3">
                  {orderHistory.map((o) => (
                    <div key={o.id} className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">{o.symbol}</span>
                          <span className="badge-blue text-[10px]">
                            {o.order_type} {o.side}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {o.filled_quantity ?? o.quantity} shares @{" "}
                          {o.price ? `₹${o.price.toFixed(2)}` : "Market"} · {formatWhen(o.filled_at ?? o.created_at)}
                        </div>
                      </div>
                      <span className={`text-xs font-medium ${
                        o.status === "filled"
                          ? "text-emerald-400"
                          : o.status === "rejected"
                            ? "text-red-400"
                            : "text-gray-400"
                      } uppercase`}>
                        {o.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}