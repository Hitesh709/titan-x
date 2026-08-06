"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Star, Plus, MoreHorizontal, ExternalLink, TrendingUp, TrendingDown, Trash2, Edit, RefreshCw, FolderPlus, X } from "lucide-react"
import Link from "next/link"
import api from "@/lib/api"
import { useLiveRefresh } from "@/lib/live"
import { formatCurrency, getChangeColor } from "@/lib/utils"

interface Watchlist {
  id: number
  user_id: number
  folder_id: number | null
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
  sort_order: number
  added_at: string | null
  tags: Array<{ id: number; name: string; color: string | null }>
}

interface MarketQuote {
  symbol: string
  name: string
  last_price: number | null
  change: number | null
  change_percent: number | null
  volume: number
  market_cap?: number | null
  exchange: string
  market_state?: string
  currency: string
  timestamp: string
  source?: string
}

interface BatchQuotesResponse {
  quotes: MarketQuote[]
  count: number
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export default function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [quotes, setQuotes] = useState<Record<string, MarketQuote>>({})

  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({ name: "", description: "", folder_id: null as number | null })

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState({ name: "", description: "" })

  const [showAddSymbol, setShowAddSymbol] = useState<number | null>(null)
  const [addSymbol, setAddSymbol] = useState("")

  const mounted = useRef(true)

  const loadWatchlists = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<PaginatedResponse<Watchlist>>("/watchlists?limit=100")
      if (!mounted.current) return
      setWatchlists(res.items ?? [])
      setError(null)
      // Fetch quotes for all symbols across all watchlists
      const allSymbols = [...new Set(res.items?.flatMap(w => w.items?.map(i => i.symbol) ?? []) ?? [])]
      if (allSymbols.length > 0) {
        const qRes = await api.get<BatchQuotesResponse>(`/market-data/quotes?symbols=${allSymbols.join(",")}`, { cacheTTL: 15_000 })
        if (mounted.current) {
          const quoteMap: Record<string, MarketQuote> = {}
          qRes.quotes.forEach(q => { if (q.symbol) quoteMap[q.symbol] = q })
          setQuotes(quoteMap)
        }
      }
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load watchlists")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    loadWatchlists()
    return () => { mounted.current = false }
  }, [loadWatchlists])

  useLiveRefresh(() => void loadWatchlists(true), [loadWatchlists])

  const handleRefresh = () => { setRefreshing(true); void loadWatchlists() }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.post("/watchlists", { name: createForm.name, description: createForm.description, folder_id: createForm.folder_id })
      setShowCreate(false)
      setCreateForm({ name: "", description: "", folder_id: null })
      void loadWatchlists()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create watchlist")
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this watchlist?")) return
    try {
      await api.delete(`/watchlists/${id}`)
      void loadWatchlists()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete watchlist")
    }
  }

  const handleAddSymbol = async (watchlistId: number, symbol: string) => {
    if (!symbol.trim()) return
    try {
      await api.post(`/watchlists/${watchlistId}/items`, { symbol: symbol.trim().toUpperCase() })
      setShowAddSymbol(null)
      setAddSymbol("")
      void loadWatchlists()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add symbol")
    }
  }

  const handleRemoveSymbol = async (watchlistId: number, itemId: number) => {
    if (!confirm("Remove this symbol?")) return
    try {
      await api.delete(`/watchlists/${watchlistId}/items/${itemId}`)
      void loadWatchlists()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove symbol")
    }
  }

  const formatDate = (s: string | null) => s ? new Date(s).toLocaleDateString() : "—"
  const getQuote = (sym: string) => quotes[sym]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlists</h1>
          <p className="text-gray-500 text-sm mt-1">Monitor your favorite symbols and custom watchlists</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
            <Plus size={14} /> New Watchlist
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

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">New Watchlist</h2>
              <button onClick={() => { setShowCreate(false); setCreateForm({ name: "", description: "", folder_id: null }) }} className="text-gray-500 hover:text-white"><X size={20} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Name</label>
                <input value={createForm.name} onChange={e => setCreateForm({...createForm, name: e.target.value})} required className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="My Watchlist" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Description</label>
                <textarea value={createForm.description} onChange={e => setCreateForm({...createForm, description: e.target.value})} rows={2} className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="Optional" />
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => { setShowCreate(false); setCreateForm({ name: "", description: "", folder_id: null }) }} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary flex-1">{creating ? "Creating..." : "Create"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAddSymbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-titan-900 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-white mb-4">Add Symbol</h2>
            <form onSubmit={e => { e.preventDefault(); handleAddSymbol(showAddSymbol, addSymbol) }} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Symbol (e.g. RELIANCE)</label>
                <input value={addSymbol} onChange={e => setAddSymbol(e.target.value.toUpperCase())} required autoFocus className="w-full bg-titan-800 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500" placeholder="RELIANCE" />
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => { setShowAddSymbol(null); setAddSymbol("") }} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">Add Symbol</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading && watchlists.length === 0 ? (
        <div className="p-8"><div className="space-y-3 animate-pulse">{[1,2,3].map(i => <div key={i} className="h-24 rounded-lg bg-white/5" />)}</div></div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-6">
          {watchlists.length === 0 ? (
            <div className="lg:col-span-2 glass-card p-12 text-center">
              <Star size={48} className="mx-auto text-gray-600 mb-4" />
              <h3 className="text-lg font-medium text-white mb-2">No watchlists yet</h3>
              <p className="text-gray-500 mb-6">Create your first watchlist to start tracking symbols</p>
              <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={14} /> Create Watchlist</button>
            </div>
          ) : (
            watchlists.map((list) => (
              <div key={list.id} className="glass-card p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Star size={14} className="fill-yellow-500 text-yellow-500" />
                    {editingId === list.id ? (
                      <input value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} className="text-sm font-semibold text-white bg-titan-800 border border-white/10 rounded px-2 py-1 w-48" onBlur={() => setEditingId(null)} onKeyDown={e => e.key === "Enter" && setEditingId(null)} autoFocus />
                    ) : (
                      <h3 className="text-sm font-semibold text-white cursor-pointer" onClick={() => { setEditForm({ name: list.name, description: list.description || "" }); setEditingId(list.id) }}>
                        {list.name}
                        {list.is_default && <span className="badge-blue text-[10px] ml-1">Default</span>}
                      </h3>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setShowAddSymbol(list.id)} className="btn-ghost text-xs px-2 py-1" title="Add Symbol"><Plus size={12} /></button>
                    {editingId === list.id ? (
                      <button onClick={() => setEditingId(null)} className="btn-ghost text-xs px-2 py-1" title="Save"><RefreshCw size={12} /></button>
                    ) : (
                      <button onClick={() => { setEditForm({ name: list.name, description: list.description || "" }); setEditingId(list.id) }} className="btn-ghost text-xs px-2 py-1" title="Edit"><Edit size={12} /></button>
                    )}
                    <button onClick={() => handleDelete(list.id)} className="btn-ghost text-xs px-2 py-1 text-red-500 hover:text-red-400" title="Delete"><Trash2 size={12} /></button>
                  </div>
                </div>
                {list.description && <p className="text-xs text-gray-500 mb-3 line-clamp-2">{list.description}</p>}
                <div className="space-y-2">
                  {(list.items ?? []).length === 0 ? (
                    <div className="text-center py-6 text-gray-500 text-sm">
                      Empty — <button onClick={() => setShowAddSymbol(list.id)} className="text-titan-400 hover:underline">add a symbol</button>
                    </div>
                  ) : (
                    list.items?.map((item) => {
                      const quote = getQuote(item.symbol)
                      const up = (quote?.change_percent ?? 0) >= 0
                      return (
                        <div key={item.id} className="flex items-center justify-between py-2 px-3 bg-white/5 rounded-lg">
                          <div className="flex items-center gap-2">
                            <Link href={`/dashboard/stocks/${item.symbol}`} className="text-sm font-medium text-white hover:text-titan-400">{item.symbol}</Link>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className="text-sm text-white">
                              {quote?.last_price !== null ? formatCurrency(quote.last_price).replace("₹", "") : "—"}
                            </span>
                            {quote?.change_percent !== null && (
                              <span className={`flex items-center gap-1 text-xs font-medium ${getChangeColor(quote.change_percent)}`}>
                                {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {quote.change_percent >= 0 ? "+" : ""}{quote.change_percent.toFixed(2)}%
                              </span>
                            )}
                            <button onClick={() => handleRemoveSymbol(list.id, item.id)} className="text-gray-500 hover:text-red-400" title="Remove"><Trash2 size={12} /></button>
                          </div>
                         </div>
                       )
                     })
                   )
                 }
               </div>
             </div>
             ))
          )}
          </div>
        )
      }
    </div>
  )
}

