"use client"

import { memo, type FormEvent, type ReactNode } from "react"
import { Trash2, Landmark, Clock, CheckCircle, Zap, ArrowRight, Loader2 } from "lucide-react"
import type { PaperAccountSummary, PaperPosition } from "@/types"
import { formatCurrency, getChangeColor } from "@/lib/utils"
import { WidgetEmpty } from "@/components/dashboard/widget"
import { SymbolAutocomplete } from "@/components/dashboard/SymbolAutocomplete"

export interface OrderRow {
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

export interface PlacedOrder {
  id: number
  symbol: string
  side: string
  order_type: string
  quantity: number
  filled_quantity: number
  status: string
  rejection_reason: string | null
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function AccountSummary({ account }: { account: PaperAccountSummary | null }) {
  return (
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
          {formatCurrency(account?.total_pnl ?? 0)}
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Realized {formatCurrency(account?.total_realized_pnl ?? 0)}
        </div>
      </div>
    </div>
  )
}

interface QuickTradeFormProps {
  symbol: string
  side: "buy" | "sell"
  orderType: "market" | "limit"
  quantity: string
  price: string
  onSymbolChange: (v: string) => void
  onSideChange: (v: "buy" | "sell") => void
  onOrderTypeChange: (v: "market" | "limit") => void
  onQuantityChange: (v: string) => void
  onPriceChange: (v: string) => void
  onSubmit: (e: FormEvent) => void
  submitting: boolean
  formError: string | null
  formSuccess: string | null
}

export function QuickTradeForm(props: QuickTradeFormProps) {
  const {
    symbol, side, orderType, quantity, price,
    onSymbolChange, onSideChange, onOrderTypeChange, onQuantityChange, onPriceChange,
    onSubmit, submitting, formError, formSuccess,
  } = props
  return (
    <form onSubmit={onSubmit} className="glass-card p-5">
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        <Zap size={16} className="text-titan-400" /> Quick Trade
      </h3>
      <div className="flex flex-wrap gap-4 items-end">
        <div className="min-w-[160px]">
          <label className="block text-xs text-gray-500 mb-1">Symbol</label>
          <SymbolAutocomplete value={symbol} onChange={onSymbolChange} placeholder="RELIANCE" className="w-full" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Side</label>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => onSideChange("buy")}
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
              onClick={() => onSideChange("sell")}
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
            onChange={(e) => onOrderTypeChange(e.target.value as "market" | "limit")}
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
            onChange={(e) => onQuantityChange(e.target.value)}
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
            onChange={(e) => onPriceChange(e.target.value)}
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
  )
}

const HoldingRow = memo(function HoldingRow({ p }: { p: PaperPosition }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
      <div>
        <div className="text-sm font-medium text-white">{p.symbol}</div>
        <div className="text-xs text-gray-500 mt-0.5">
          {p.quantity} shares @ {formatCurrency(p.average_price)}
        </div>
      </div>
      <div className="text-right">
        <div className={getChangeColor(p.unrealized_pnl)}>{formatCurrency(p.unrealized_pnl)}</div>
        <div className="text-xs text-gray-500 mt-0.5">{p.market_value.toFixed(0)}</div>
      </div>
    </div>
  )
})

export function HoldingsList({ positions }: { positions: PaperPosition[] }) {
  if (positions.length === 0) {
    return <WidgetEmpty message="No positions yet. Place a trade to get started." />
  }
  return (
    <div className="space-y-2">
      {positions.map((p) => (
        <HoldingRow key={p.symbol} p={p} />
      ))}
    </div>
  )
}

const OrderRowItem = memo(function OrderRowItem({
  o,
  onCancel,
}: {
  o: OrderRow
  onCancel?: (id: number) => void
}) {
  const isOpen = onCancel !== undefined
  return (
    <div className="flex items-center justify-between py-2 border-b border-titan-800/20 last:border-0">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white">{o.symbol}</span>
          <span className="badge-blue text-[10px]">
            {o.order_type} {o.side}
          </span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5">
          {o.filled_quantity ?? o.quantity} shares @ {o.price ? `₹${o.price.toFixed(2)}` : "Market"}
          {isOpen ? "" : ` · ${formatWhen(o.filled_at ?? o.created_at)}`}
        </div>
      </div>
      <div className="text-right flex items-center gap-2">
        <span
          className={`text-xs font-medium ${
            o.status === "filled"
              ? "text-emerald-400"
              : o.status === "rejected"
                ? "text-red-400"
                : o.status === "open" || o.status === "pending" || o.status === "partially_filled"
                  ? "text-yellow-400"
                  : "text-gray-400"
          } uppercase`}
        >
          {o.status}
        </span>
        {onCancel && (
          <button onClick={() => onCancel(o.id)} className="text-gray-500 hover:text-red-400" title="Cancel">
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
})

export function OrdersTable({
  title,
  icon,
  orders,
  onCancel,
  emptyMessage,
}: {
  title: string
  icon: ReactNode
  orders: OrderRow[]
  onCancel?: (id: number) => void
  emptyMessage: string
}) {
  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        {icon} {title}
      </h3>
      {orders.length === 0 ? (
        <WidgetEmpty message={emptyMessage} />
      ) : (
        <div className="space-y-3">
          {orders.map((o) => (
            <OrderRowItem key={o.id} o={o} onCancel={onCancel} />
          ))}
        </div>
      )}
    </div>
  )
}
