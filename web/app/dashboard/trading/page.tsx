"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Clock, CheckCircle } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import type { PaperAccountSummary, PaperPosition } from "@/types"
import { WidgetLoading, WidgetError, RefreshButton } from "@/components/dashboard/widget"
import {
  AccountSummary,
  QuickTradeForm,
  HoldingsList,
  OrdersTable,
  type OrderRow,
  type PlacedOrder,
} from "./components"

const OPEN_STATUSES = ["pending", "open", "partially_filled"]

export default function TradingPage() {
  const searchParams = useSearchParams()
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
      if (accRes.status === "rejected")
        setError(accRes.reason instanceof Error ? accRes.reason.message : "Failed to load account")
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
    const requestedSymbol = searchParams.get("symbol")?.trim().toUpperCase()
    const requestedSide = searchParams.get("side")?.toLowerCase()
    if (requestedSymbol) setSymbol(requestedSymbol)
    if (requestedSide === "buy" || requestedSide === "sell") setSide(requestedSide)
    return () => {
      mounted.current = false
    }
  }, [searchParams])

  useLiveRefresh(() => void load(true), [load])

  const refreshPrices = async () => {
    try {
      await api.post("/paper-trading/portfolio/refresh", {})
    } catch {
      // non-fatal: positions simply keep their last mark
    }
  }

  const handleRefresh = () => {
    setRefreshing(true)
    refreshPrices().finally(() => load(true))
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
        setFormSuccess(
          `${placed.side.toUpperCase()} ${placed.filled_quantity ?? placed.quantity} ${placed.symbol} @ ${placed.status}`,
        )
        setQuantity("")
        setPrice("")
      }
      await refreshPrices()
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
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-white">Trading</h1>
            <span
              className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30"
              title="Simulated trading with virtual cash — no real broker, no real money"
            >
              Demo · Paper
            </span>
          </div>
          <p className="text-gray-500 text-sm mt-1">
            Place paper trades and track your positions, orders, and P&amp;L
          </p>
        </div>
        <RefreshButton onClick={handleRefresh} spinning={refreshing} />
      </div>

      {error && <WidgetError message={error} onRetry={() => load(false)} />}

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
          <AccountSummary account={account} />

          <div className="grid lg:grid-cols-2 gap-6">
            <QuickTradeForm
              symbol={symbol}
              side={side}
              orderType={orderType}
              quantity={quantity}
              price={price}
              onSymbolChange={setSymbol}
              onSideChange={setSide}
              onOrderTypeChange={setOrderType}
              onQuantityChange={setQuantity}
              onPriceChange={setPrice}
              onSubmit={handlePlaceOrder}
              submitting={submitting}
              formError={formError}
              formSuccess={formSuccess}
            />
            <div className="glass-card p-5">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                Current Holdings
              </h3>
              <HoldingsList positions={positions} />
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            <OrdersTable
              title="Open Orders"
              icon={<Clock size={16} className="text-titan-400" />}
              orders={openOrders}
              onCancel={handleCancel}
              emptyMessage="No open orders."
            />
            <OrdersTable
              title="Order History"
              icon={<CheckCircle size={16} className="text-titan-400" />}
              orders={orderHistory}
              emptyMessage="No orders yet."
            />
          </div>
        </>
      )}
    </div>
  )
}
