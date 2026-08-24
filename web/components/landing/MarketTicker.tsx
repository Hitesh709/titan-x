"use client"

import { useEffect, useMemo, useState } from "react"

export type MarketRow = {
  name: string
  symbol: string
  price: number | null
  change_pct: number | null
  region?: string
}

type Snapshot = {
  ok: boolean
  source?: string
  timestamp?: string
  score?: number | null
  regime?: string
  markets?: MarketRow[]
}

const globalIndexUniverse: MarketRow[] = [
  { name: "NIFTY 50", symbol: "^NSEI", price: null, change_pct: null, region: "India" },
  { name: "SENSEX", symbol: "^BSESN", price: null, change_pct: null, region: "India" },
  { name: "BANK NIFTY", symbol: "^NSEBANK", price: null, change_pct: null, region: "India" },
  { name: "NIFTY IT", symbol: "^CNXIT", price: null, change_pct: null, region: "India" },
  { name: "NIFTY FIN", symbol: "^CNXFIN", price: null, change_pct: null, region: "India" },
  { name: "S&P 500", symbol: "^GSPC", price: null, change_pct: null, region: "US" },
  { name: "NASDAQ", symbol: "^IXIC", price: null, change_pct: null, region: "US" },
  { name: "DOW JONES", symbol: "^DJI", price: null, change_pct: null, region: "US" },
  { name: "RUSSELL 2000", symbol: "^RUT", price: null, change_pct: null, region: "US" },
  { name: "FTSE 100", symbol: "^FTSE", price: null, change_pct: null, region: "UK" },
  { name: "DAX", symbol: "^GDAXI", price: null, change_pct: null, region: "Germany" },
  { name: "CAC 40", symbol: "^FCHI", price: null, change_pct: null, region: "France" },
  { name: "NIKKEI 225", symbol: "^N225", price: null, change_pct: null, region: "Japan" },
  { name: "HANG SENG", symbol: "^HSI", price: null, change_pct: null, region: "Hong Kong" },
  { name: "SHANGHAI", symbol: "000001.SS", price: null, change_pct: null, region: "China" },
  { name: "KOSPI", symbol: "^KS11", price: null, change_pct: null, region: "South Korea" },
  { name: "ASX 200", symbol: "^AXJO", price: null, change_pct: null, region: "Australia" },
  { name: "GOLD", symbol: "GC=F", price: null, change_pct: null, region: "Global" },
  { name: "USD/INR", symbol: "INR=X", price: null, change_pct: null, region: "FX" },
  { name: "BTC/USD", symbol: "BTC-USD", price: null, change_pct: null, region: "Digital" },
]

function mergeUniverse(apiMarkets: MarketRow[] | undefined) {
  const incoming = apiMarkets ?? []
  return globalIndexUniverse.map((base) => {
    const match = incoming.find((m) =>
      m.symbol?.toUpperCase() === base.symbol.toUpperCase() ||
      m.name?.toUpperCase() === base.name.toUpperCase()
    )
    return match ? { ...base, ...match, region: match.region ?? base.region } : base
  })
}

export function usePublicMarket() {
  const [snapshot, setSnapshot] = useState<Snapshot>({ ok: false, markets: globalIndexUniverse })

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const response = await fetch("/api/v1/public-market/snapshot", { cache: "no-store" })
        if (!response.ok) throw new Error("market snapshot failed")
        const data = (await response.json()) as Snapshot
        if (active) setSnapshot({ ...data, markets: mergeUniverse(data.markets) })
      } catch {
        if (active) setSnapshot((current) => ({ ...current, markets: current.markets?.length ? current.markets : globalIndexUniverse }))
      }
    }
    load()
    const timer = window.setInterval(load, 30_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const markets = useMemo(() => mergeUniverse(snapshot.markets), [snapshot.markets])
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
    <div className="market-ticker" aria-label="Global live market indices">
      <div className="market-ticker__label"><span className="market-ticker__dot" /> GLOBAL MARKETS</div>
      <div className="market-ticker__viewport">
        <div className="market-ticker__track">
          {items.map((item, index) => {
            const positive = (item.change_pct ?? 0) >= 0
            const live = item.price != null
            return (
              <div className="market-ticker__item" key={`${item.symbol}-${index}`}>
                <span className="market-ticker__region">{item.region}</span>
                <span className="market-ticker__name">{item.name}</span>
                <span className="market-ticker__price">{formatPrice(item.price)}</span>
                <span className={positive ? "market-ticker__change is-up" : "market-ticker__change is-down"}>
                  {item.change_pct == null ? (live ? "LIVE" : "FEED") : `${positive ? "▲" : "▼"} ${Math.abs(item.change_pct).toFixed(2)}%`}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
