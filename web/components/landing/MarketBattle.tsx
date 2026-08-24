"use client"

import { useEffect, useRef, useState } from "react"
import type { PointerEvent } from "react"
import { Rotate3D, Sparkles, Target } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

export default function MarketBattle() {
  const { score, regime } = usePublicMarket()
  const [rotation, setRotation] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [pulse, setPulse] = useState(false)
  const startX = useRef(0)
  const startRotation = useRef(0)

  const numericScore = typeof score === "number" ? score : 72
  const bearish = numericScore <= 40 || (regime ?? "").toLowerCase().includes("bear")
  const bullish = numericScore >= 60 || (regime ?? "").toLowerCase().includes("bull")
  const winner = bearish ? "bear" : bullish ? "bull" : "neutral"

  useEffect(() => {
    setPulse(false)
    const timer = window.setTimeout(() => setPulse(true), 180)
    return () => window.clearTimeout(timer)
  }, [winner])

  const down = (event: PointerEvent<HTMLDivElement>) => {
    setDragging(true)
    startX.current = event.clientX
    startRotation.current = rotation
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return
    const delta = event.clientX - startX.current
    setRotation(Math.max(-35, Math.min(35, startRotation.current + delta * 0.22)))
  }

  const up = (event: PointerEvent<HTMLDivElement>) => {
    setDragging(false)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  const bullTransform = `translateX(-7%) translateZ(20px) rotateY(${-12 + rotation}deg)`
  const bearTransform = `translateX(7%) translateZ(20px) rotateY(${12 + rotation}deg)`

  return (
    <div className={`battle-shell battle-${winner}`}>
      <div className="battle-header">
        <div>
          <div className="battle-kicker"><Sparkles size={13} /> AI MARKET REGIME</div>
          <div className="battle-title">{winner === "bear" ? "BEAR MARKET" : winner === "bull" ? "BULL MARKET" : "MARKET IN BALANCE"}</div>
          <div className="battle-subtitle">{winner === "bear" ? "BEAR DOMINATING" : winner === "bull" ? "BULL DOMINATING" : "WAITING FOR CONFIRMATION"}</div>
        </div>
        <div className="battle-score"><span>AI SCORE</span><strong>{Math.round(numericScore)}</strong></div>
      </div>

      <div className={`battle-stage ${dragging ? "is-dragging" : ""}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <div className="battle-grid" /><div className="battle-ring battle-ring-one" /><div className="battle-ring battle-ring-two" />
        <div className={`battle-impact ${winner !== "neutral" ? "is-active" : ""}`} />

        <div className="battle-beast battle-bull" style={{ transform: bullTransform }}>
          <img className={winner === "bull" ? "battle-hit-bull" : ""} src="/titanx-3d-bull.svg" alt="3D TITAN X bull" draggable={false} />
          {winner === "bull" && <div className="winner-tag"><Target size={12} /> WIN</div>}
        </div>
        <div className="battle-beast battle-bear" style={{ transform: bearTransform }}>
          <img className={winner === "bear" ? "battle-hit-bear" : ""} src="/titanx-3d-bear.svg" alt="3D TITAN X bear" draggable={false} />
          {winner === "bear" && <div className="winner-tag"><Target size={12} /> WIN</div>}
        </div>

        <div className="battle-strike" aria-hidden="true"><span /><span /><span /></div>
        <div className="battle-instruction"><Rotate3D size={14} /> DRAG TO ROTATE</div>
      </div>

      <div className="battle-footer"><span className="battle-live"><i /> LIVE REGIME ENGINE</span><span>30s refresh</span><span>Score is momentum, not a trade signal</span></div>
    </div>
  )
}
