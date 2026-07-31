"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { RefreshCw } from "lucide-react"
import api from "@/lib/api"
import type {
  DashboardData,
  MarketHeatmapData,
  NewsArticle,
} from "@/types"
import { MarketOverview } from "@/components/dashboard/MarketOverview"
import { PortfolioSummaryWidget } from "@/components/dashboard/PortfolioSummary"
import { AiRecommendations } from "@/components/dashboard/AiRecommendations"
import { WatchlistWidget } from "@/components/dashboard/Watchlist"
import { MarketNewsWidget } from "@/components/dashboard/MarketNews"
import { TopMoversWidget } from "@/components/dashboard/TopMovers"
import { SectorHeatmap } from "@/components/dashboard/SectorHeatmap"
import { RecentAlertsWidget } from "@/components/dashboard/RecentAlerts"
import type { NewsRow } from "@/components/dashboard/types"

const PERIODS = ["1W", "1M", "3M", "6M", "YTD"] as const
const REFRESH_INTERVAL_MS = 60_000

function normalizeNews(
  marketNews: NewsArticle[],
  dashboardNews: DashboardData["news"],
): NewsRow[] {
  const rows: NewsRow[] = marketNews.map((a) => ({
    id: a.id,
    symbol: a.symbol ?? null,
    title: a.title,
    source: a.source,
    published_at: a.published_at ?? null,
    sentiment: "neutral",
    sentiment_confidence: null,
    url: a.url,
  }))
  if (rows.length > 0) return rows
  return dashboardNews.map((n) => ({
    id: n.id,
    symbol: n.symbol ?? null,
    title: n.title,
    source: n.source,
    published_at: n.published_at ?? null,
    sentiment: n.sentiment,
    sentiment_confidence: n.sentiment_confidence ?? null,
    url: null,
  }))
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [heatmap, setHeatmap] = useState<MarketHeatmapData | null>(null)
  const [newsRows, setNewsRows] = useState<NewsRow[]>([])
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("1W")
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const mounted = useRef(true)

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      const nextErrors: Record<string, string> = {}
      const [dashRes, heatRes, newsRes] = await Promise.allSettled([
        api.get<DashboardData>("/dashboard"),
        api.get<MarketHeatmapData>(`/market-heatmap?period=${period}`),
        api.get<{ items: NewsArticle[] }>("/news?limit=6&skip=0"),
      ])
      if (!mounted.current) return

      let dash: DashboardData | null = null
      if (dashRes.status === "fulfilled") {
        dash = dashRes.value
        setDashboard(dash)
      } else {
        nextErrors.dashboard = "Failed to load portfolio, watchlist and alerts."
      }
      if (heatRes.status === "fulfilled") {
        setHeatmap(heatRes.value)
      } else {
        nextErrors.heatmap = "Failed to load market overview, movers and sectors."
      }
      if (newsRes.status === "fulfilled") {
        setNewsRows(normalizeNews(newsRes.value.items, dash?.news ?? []))
      } else if (dash) {
        setNewsRows(normalizeNews([], dash.news))
      }
      setErrors(nextErrors)
      setLoading(false)
      setRefreshing(false)
    },
    [period],
  )

  useEffect(() => {
    mounted.current = true
    void load()
    const interval = setInterval(() => {
      void load(true)
    }, REFRESH_INTERVAL_MS)
    return () => {
      mounted.current = false
      clearInterval(interval)
    }
  }, [load])

  const handleRefresh = () => {
    setRefreshing(true)
    void load(true)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Live market, portfolio and AI intelligence</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center rounded-lg bg-white/5 border border-white/10 p-0.5">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  period === p ? "bg-titan-600 text-white" : "text-gray-500 hover:text-gray-200"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-white/10 rounded-lg px-3 py-2 transition-colors"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <MarketOverview heatmap={heatmap} loading={loading} error={errors.heatmap ?? null} onRetry={handleRefresh} />
        <PortfolioSummaryWidget
          data={dashboard?.portfolio ?? { has_account: false }}
          loading={loading}
          error={errors.dashboard ?? null}
          onRetry={handleRefresh}
        />
        <AiRecommendations />
        <WatchlistWidget
          data={dashboard?.watchlists ?? []}
          loading={loading}
          error={errors.dashboard ?? null}
          onRetry={handleRefresh}
        />
        <MarketNewsWidget
          data={newsRows}
          loading={loading}
          error={errors.dashboard ?? null}
          onRetry={handleRefresh}
        />
        <TopMoversWidget
          title="Top Gainers"
          type="gainers"
          data={heatmap?.leaders ?? []}
          loading={loading}
          error={errors.heatmap ?? null}
          onRetry={handleRefresh}
        />
        <TopMoversWidget
          title="Top Losers"
          type="losers"
          data={heatmap?.laggards ?? []}
          loading={loading}
          error={errors.heatmap ?? null}
          onRetry={handleRefresh}
        />
        <SectorHeatmap
          data={heatmap?.sectors ?? []}
          loading={loading}
          error={errors.heatmap ?? null}
          onRetry={handleRefresh}
        />
        <RecentAlertsWidget
          data={dashboard?.alerts ?? []}
          loading={loading}
          error={errors.dashboard ?? null}
          onRetry={handleRefresh}
        />
      </div>
    </div>
  )
}
