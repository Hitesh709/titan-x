"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/lib/api"
import type { NewsArticle, NewsRow, PaginatedResponse } from "@/types"
import { MarketNewsWidget } from "@/components/dashboard/MarketNews"
import { RefreshCw } from "lucide-react"
import { useLiveRefresh } from "@/lib/live"

type Sentiment = "positive" | "negative" | "neutral"

const deriveSentiment = (article: { title?: string | null; summary?: string | null }): Sentiment => {
  const text = `${(article.title ?? "").toLowerCase()} ${(article.summary ?? "").toLowerCase()}`
  if (/\b(bull|bullish|rall|surge|gain|profit|beat|record|strong|up)\b/.test(text)) return "positive"
  if (/\b(bear|bearish|slump|loss|miss|down|fall|drop|cut|warn)\b/.test(text)) return "negative"
  return "neutral"
}

export default function NewsPage() {
  const [news, setNews] = useState<NewsRow[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const limit = 20
  const mounted = useRef(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await api.get<PaginatedResponse<NewsArticle>>(
        `/news?limit=${limit}&skip=${skip}`
      )
      if (!mounted.current) return
      const toNewsRow = (n: NewsArticle): NewsRow => ({
        id: n.id,
        symbol: n.symbol ?? null,
        title: n.title,
        source: n.source,
        published_at: n.published_at ?? null,
        sentiment: deriveSentiment(n),
        sentiment_confidence: 0.5,
        url: n.url,
      })
      const rows: NewsRow[] = (res.items ?? []).map(toNewsRow)
      setNews(rows)
      setTotal(res.total ?? 0)
      setError(null)
    } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : "Failed to load news")
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [skip])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLiveRefresh(() => void load(true), [load])

  const handleRefresh = () => {
    setRefreshing(true)
    void load(true)
  }

  const handleLoadMore = () => {
    if (skip + limit < total) {
      setSkip((s) => s + limit)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">News & Market Intelligence</h1>
          <p className="text-gray-500 text-sm mt-1">Real-time news with AI-powered categorization</p>
        </div>
        <button onClick={handleRefresh} className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <MarketNewsWidget
        data={news}
        loading={loading}
        error={error}
        onRetry={handleRefresh}
      />

      {total > skip + news.length && (
        <div className="text-center">
          <button
            onClick={handleLoadMore}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-white/10 rounded-lg text-sm text-gray-400 hover:text-white hover:border-titan-600/40 transition-colors disabled:opacity-50"
          >
            Load more ({news.length} / {total})
          </button>
        </div>
      )}
    </div>
  )
}
