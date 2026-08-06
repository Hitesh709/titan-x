"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Bell, Plus, BellOff, BellRing, Trash2, RefreshCw, X } from "lucide-react"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"

interface Watchlist {
  id: number
  name: string
  description: string | null
  is_default: boolean
  created_at: string | null
  items?: WatchlistItem[]
}

interface WatchlistItem {
  id: number
  watchlist_id: number
  symbol: string
  notes: string | null
  added_at: string | null
}

interface Alert {
  id: number
  watchlist_item_id: number
  alert_type: string
  operator: string
  threshold_value: number | null
  is_active: boolean
  last_triggered_at: string | null
  created_at: string | null
  symbol?: string
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [totalActive, setTotalActive] = useState(0)
  const [totalTriggered, setTotalTriggered] = useState(0)

  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [itemIndex, setItemIndex] = useState<Map<number, { symbol: string; watchlist_id: number }>>(new Map())
  const [form, setForm] = useState({
    watchlist_id: "",
    item_symbol: "",
    alert_type: "price",
    operator: ">",
    threshold_value: "",
  })

  const mounted = useRef(true)

  const loadAlerts = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const wlRes = await api.get<PaginatedResponse<Watchlist>>("/watchlists?limit=100")
      if (!mounted.current) return
      const lists = wlRes.items ?? []
      setWatchlists(lists)
      const allAlerts: Alert[] = []
      const idx = new Map<number, { symbol: string; watchlist_id: number }>()
      const fetchWatchlistData = async (wl: Watchlist) => {
        const [alRes, alertRes] = await Promise.all([
          api.get<{ items: WatchlistItem[] }>(`/watchlists/${wl.id}/items?limit=200`).catch(() => ({ items: [] })),
          api.get<Alert[]>(`/watchlists/${wl.id}/alerts`).catch(() => [] as Alert[]),
        ])
        const items = alRes.items ?? []
        const itemSymbols = new Map(items.map(i => [i.id, i.symbol]))
        for (const it of items) idx.set(it.id, { symbol: it.symbol, watchlist_id: wl.id })
        for (const a of (alertRes ?? [])) {
          allAlerts.push({ ...a, symbol: itemSymbols.get(a.watchlist_item_id) ?? undefined } as Alert)
        }
      }
      await Promise.all(lists.map(fetchWatchlistData))
      setItemIndex(idx)
      if (mounted.current) {
        setAlerts(allAlerts.sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0
          return tb - ta
        }))
        setTotalActive(allAlerts.filter(a => a.is_active).length)
        setTotalTriggered(allAlerts.filter(a => !a.is_active).length)
        setError(null)
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load alerts")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    loadAlerts()
    return () => { mounted.current = false }
  }, [loadAlerts])

  useLiveRefresh(() => void loadAlerts(true), [loadAlerts])

  const handleRefresh = () => { setRefreshing(true); void loadAlerts() }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const wlId = parseInt(form.watchlist_id)
      const item = Array.from(itemIndex.entries()).find(
        ([, v]) => v.watchlist_id === wlId && v.symbol === form.item_symbol.trim().toUpperCase()
      )
      const item_id = item ? item[0] : undefined
      await api.post(`/watchlists/${wlId}/alerts`, {
        item_id,
        alert_type: form.alert_type,
        operator: form.operator,
        threshold_value: parseFloat(form.threshold_value),
      })
      setShowCreate(false)
      setCreating(false)
      void loadAlerts()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create alert")
      setCreating(false)
    }
  }

  const handleToggleActive = async (alert: Alert) => {
    const entry = itemIndex.get(alert.watchlist_item_id)
    const watchlistId = entry?.watchlist_id
    if (!watchlistId) return
    try {
      await api.put(`/watchlists/${watchlistId}/alerts/${alert.id}`, {
        is_active: !alert.is_active,
      })
      void loadAlerts()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update alert")
    }
  }

  const handleDelete = async (alert: Alert) => {
    if (!confirm("Delete this alert?")) return
    const entry = itemIndex.get(alert.watchlist_item_id)
    const watchlistId = entry?.watchlist_id
    if (!watchlistId) return
    try {
      await api.delete(`/watchlists/${watchlistId}/alerts/${alert.id}`)
      void loadAlerts()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete alert")
    }
  }

  const formatDate = (s: string | null) => s ? new Date(s).toLocaleDateString() : "—"
  const formatCondition = (a: Alert) => `${a.alert_type} ${a.operator} ${a.threshold_value ?? ""}`

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
          <p className="text-gray-500 text-sm mt-1">Configure and manage your market alerts</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
            <Plus size={14} /> New Alert
          </button>
          <button onClick={handleRefresh} className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors">
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300">×</button>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Active Alerts", value: totalActive },
          { label: "Triggered", value: totalTriggered },
          { label: "Delivery Channels", value: "Web" },
        ].map((s) => (
          <div key={s.label} className="glass-card p-4">
            <div className="text-sm text-gray-400">{s.label}</div>
            <div className="text-lg font-bold text-white mt-1">{s.value}</div>
          </div>
        ))}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">New Alert</h2>
              <button onClick={() => { setShowCreate(false); setForm({ watchlist_id: "", item_symbol: "", alert_type: "price", operator: ">", threshold_value: "" }) }} className="text-gray-500 hover:text-white"><X size={20} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Watchlist</label>
                <select value={form.watchlist_id} onChange={e => setForm({...form, watchlist_id: e.target.value})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                  <option value="">Select a watchlist</option>
                  {watchlists.map(wl => (
                    <option key={wl.id} value={wl.id}>{wl.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Symbol</label>
                <input value={form.item_symbol} onChange={e => setForm({...form, item_symbol: e.target.value.toUpperCase()})} required placeholder="e.g. RELIANCE" className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Type</label>
                  <select value={form.alert_type} onChange={e => setForm({...form, alert_type: e.target.value})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                    <option value="price">Price</option>
                    <option value="volume">Volume</option>
                    <option value="pct_change">Percent Change</option>
                    <option value="rsi">RSI</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Operator</label>
                  <select value={form.operator} onChange={e => setForm({...form, operator: e.target.value})} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                    <option value=">">&gt;</option>
                    <option value="<">&lt;</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Threshold</label>
                <input type="number" step="0.01" value={form.threshold_value} onChange={e => setForm({...form, threshold_value: e.target.value})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="1350" />
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => { setShowCreate(false); setForm({ watchlist_id: "", item_symbol: "", alert_type: "price", operator: ">", threshold_value: "" }) }} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary flex-1">{creating ? "Creating..." : "Create Alert"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-titan-800/30 text-left">
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Symbol</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Type</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Condition</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Status</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Created</th>
                <th className="py-3 px-4 text-gray-500 text-xs uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center"><div className="animate-pulse text-gray-600">Loading alerts...</div></td>
                </tr>
              ) : alerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-500">No alerts configured. Create one to get started.</td>
                </tr>
              ) : (
                alerts.map((a) => (
                  <tr key={a.id} className="border-b border-titan-800/20 hover:bg-white/5">
                    <td className="py-3 px-4">
                      <span className="text-white font-medium">{a.symbol ?? a.watchlist_item_id}</span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="badge-blue text-[10px]">{a.alert_type}</span>
                    </td>
                    <td className="py-3 px-4 text-gray-400">{formatCondition(a)}</td>
                    <td className="py-3 px-4">
                      {a.is_active ? (
                        <span className="flex items-center gap-1 text-xs text-gray-400"><Bell size={12} /> Active</span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-emerald-400"><BellRing size={12} /> Triggered</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-xs">{formatDate(a.created_at)}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <button onClick={() => handleToggleActive(a)} className="btn-ghost text-xs px-2 py-1 text-gray-500 hover:text-yellow-400" title={a.is_active ? "Deactivate" : "Activate"}>
                          {a.is_active ? <BellOff size={12} /> : <Bell size={12} />}
                        </button>
                        <button onClick={() => handleDelete(a)} className="btn-ghost text-xs px-2 py-1 text-gray-500 hover:text-red-400" title="Delete"><Trash2 size={12} /></button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
