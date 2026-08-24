"use client"

import { useMemo } from "react"
import { usePublicMarket } from "./MarketTicker"
import TitanXBullBearScene, { type MarketState } from "../titanx/TitanXBullBearScene"
import "../titanx/titanx-bull-bear.css"

type MarketBattleProps = { className?: string }

/** Homepage adapter: keeps the existing market feed while delegating the visual centerpiece to the reusable TITAN X 3D engine. */
export default function MarketBattle({ className = "" }: MarketBattleProps) {
  const { score, regime, markets } = usePublicMarket()
  const numericScore = typeof score === "number" ? score : 50
  const state = useMemo<MarketState>(() => {
    const r = String(regime || "").toLowerCase()
    if (r.includes("bear") || numericScore < 45) return "bear"
    if (r.includes("bull") || numericScore > 55) return "bull"
    return "neutral"
  }, [regime, numericScore])
  const bullStrength = state === "bull" ? Math.max(58, numericScore) : state === "bear" ? Math.max(20, 100 - numericScore) : 50
  const bearStrength = state === "bear" ? Math.max(58, 100 - numericScore) : state === "bull" ? Math.max(20, numericScore) : 50
  const positive = markets.filter(m => typeof m.change_pct === "number" && m.change_pct > 0).length
  const negative = markets.filter(m => typeof m.change_pct === "number" && m.change_pct < 0).length

  return <div className={`titan-battle ${className}`} data-up={positive} data-down={negative}>
    <TitanXBullBearScene marketState={state} bullStrength={bullStrength} bearStrength={bearStrength} />
  </div>
}
