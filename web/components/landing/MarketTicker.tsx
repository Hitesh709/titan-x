"use client"

import { useEffect, useMemo, useState } from "react"

export type MarketRow = {
  name: string
  symbol: string
  price: number | null
  change_pct: number | null
}

type Snapshot = {
  ok: boolean
  source?: string
  timestamp?: string
  score?: number | null
  regime?: string
  markets?: MarketRow[]
}

const fallback: MarketRow[] = [
  { name: "NIFTY 50", symbol: "^NSEI", price: null, change_pct: null },
  { name: "SENSEX", symbol: "^BSESN", price: null, change_pct: null },
  { name: "BANK NIFTY", symbol: "^NSEBANK", price: null, change_pct: null },
  { name: "FINNIFTY", symbol: "^CNXFIN", price: null, change_pct: null },
  { name: "GOLD", symbol: "GC=F", price: null, change_pct: null },
]

export function usePublicMarket() {
  const [snapshot, setSnapshot] = useState<Snapshot>({ ok: false, markets: fallback })

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const response = await fetch("/api/v1/public-market/snapshot", { cache: "no-store" })
        if (!response.ok) throw new Error("market snapshot failed")
        const data = (await response.json()) as Snapshot
        if (active) setSnapshot({ ...data, markets: data.markets?.length ? data.markets : fallback })
      } catch {
        if (active) setSnapshot((current) => ({ ...current, markets: current.markets?.length ? current.markets : fallback }))
      }
    }

    load()
    const timer = window.setInterval(load, 30_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const markets = useMemo(() => snapshot.markets?.length ? snapshot.markets : fallback, [snapshot.markets])
  return { ...snapshot, markets }
}

function formatPrice(value: number | null) {
  if (value == null) return "—"
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

export default function MarketTicker() {
  const { markets } = usePublicMarket()
  const items = [...markets, ...markets]

  return (
    <div className="market-ticker" aria-label="Live market indices">
      <div className="market-ticker__label"><span className="market-ticker__dot" /> LIVE MARKETS</div>
      <div className="market-ticker__viewport">
        <div className="market-ticker__track">
          {items.map((item, index) => {
            const positive = (item.change_pct ?? 0) >= 0
            return (
              <div className="market-ticker__item" key={`${item.symbol}-${index}`}>
                <span className="market-ticker__name">{item.name}</span>
                <span className="market-ticker__price">{formatPrice(item.price)}</span>
                <span className={positive ? "market-ticker__change is-up" : "market-ticker__change is-down"}>
                  {item.change_pct == null ? "LIVE" : `${positive ? "▲" : "▼"} ${Math.abs(item.change_pct).toFixed(2)}%`}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
