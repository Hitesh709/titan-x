"use client"

import { usePublicMarket } from "./MarketTicker"

/**
 * Neutral homepage market visual.
 * The previous 3D bull/bear scene has been intentionally removed.
 * This component keeps the hero layout stable and displays market breadth only.
 */
export default function MarketBattle({ className = "" }: { className?: string }) {
  const { score, markets } = usePublicMarket()
  const value = typeof score === "number" ? Math.round(score) : 50
  const live = markets.filter((m: any) => m.price != null).length
  const positive = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct > 0).length
  const negative = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct < 0).length

  return (
    <div className={`titan-market-engine ${className}`} aria-label="TITAN X live market intelligence">
      <div className="tme-grid" />
      <div className="tme-head">
        <span>LIVE MARKET ENGINE</span>
        <b>INDEX BREADTH</b>
      </div>
      <div className="tme-core">
        <div className="tme-orbit orbit-a" />
        <div className="tme-orbit orbit-b" />
        <div className="tme-ring">
          <strong>{value}</strong>
          <span>AI MARKET SCORE</span>
        </div>
        <div className="tme-pulse pulse-a" />
        <div className="tme-pulse pulse-b" />
      </div>
      <div className="tme-bars" aria-hidden="true">
        {[32, 48, 39, 64, 55, 76, 61, 86, 70, 92, 78, 96].map((height, i) => (
          <i key={i} style={{ height: `${height}%` }} />
        ))}
      </div>
      <div className="tme-footer">
        <span><i className="up-dot" /> UP <b>{positive}</b></span>
        <span><i className="down-dot" /> DOWN <b>{negative}</b></span>
        <span><i className="live-dot" /> LIVE <b>{live}</b></span>
      </div>
    </div>
  )
}
