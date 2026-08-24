"use client"

import { useEffect, useRef, useState } from "react"
import type { PointerEvent } from "react"
import { Rotate3D, Sparkles, Target, Zap } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

type Winner = "bull" | "bear" | "neutral"

function Beast({ kind }: { kind: "bull" | "bear" }) {
  const bull = kind === "bull"
  return (
    <div className={`beast-3d ${bull ? "beast-bull" : "beast-bear"}`} aria-label={bull ? "3D bull" : "3D bear"}>
      <div className="beast-body" />
      <div className="beast-chest" />
      <div className="beast-head"><div className="beast-eye" /><div className="beast-eye second" /></div>
      <div className="beast-leg l1" /><div className="beast-leg l2" /><div className="beast-leg l3" /><div className="beast-leg l4" />
      {bull ? <><div className="beast-horn h1" /><div className="beast-horn h2" /><div className="beast-tail" /></> : <><div className="beast-ear e1" /><div className="beast-ear e2" /><div className="beast-arm a1" /><div className="beast-arm a2" /></>}
      <div className="beast-highlight" />
    </div>
  )
}

export default function MarketBattle() {
  const { score, regime } = usePublicMarket()
  const canvasRef = useRef<HTMLDivElement>(null)
  const [rotation, setRotation] = useState(0)
  const [dragging, setDragging] = useState(false)
  const drag = useRef({ active: false, x: 0, rotation: 0 })
  const numericScore = typeof score === "number" ? score : 50
  const normalized = (regime || "").toLowerCase()
  const winner: Winner = normalized.includes("bear") || numericScore < 45 ? "bear" : normalized.includes("bull") || numericScore > 55 ? "bull" : "neutral"

  useEffect(() => {
    if (drag.current.active) return
    const timer = window.setInterval(() => setRotation((r) => r + 0.35), 40)
    return () => window.clearInterval(timer)
  }, [])

  const down = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = { active: true, x: e.clientX, rotation }
    setDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current.active) return
    setRotation(drag.current.rotation + (e.clientX - drag.current.x) * 0.22)
  }
  const up = (e: PointerEvent<HTMLDivElement>) => {
    drag.current.active = false
    setDragging(false)
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  const isBull = winner === "bull"
  const isBear = winner === "bear"
  return (
    <div className={`titan-battle ${isBear ? "is-bear" : isBull ? "is-bull" : "is-neutral"}`}>
      <div className="titan-battle-main">
        <div className="titan-battle-head"><div><div className="titan-kicker"><Sparkles size={12} /> AI MARKET REGIME</div><div className="titan-battle-title">{isBull ? "BULL MARKET" : isBear ? "BEAR MARKET" : "MARKET BALANCED"}</div><div className="titan-battle-sub">{isBull ? "BULL DOMINATING • BUY PRESSURE" : isBear ? "BEAR DOMINATING • SELL PRESSURE" : "WAITING FOR CONFIRMATION"}</div></div><div className="titan-score"><small>AI SCORE</small><b>{Math.round(numericScore)}</b></div></div>
        <div className={`titan-canvas ${dragging ? "dragging" : ""}`} ref={canvasRef} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
          <div className="titan-battle-grid" />
          <div className="titan-battle-label left">BULL <span>LONG</span></div><div className="titan-battle-label right">BEAR <span>SHORT</span></div>
          <div className="titan-3d-stage" style={{ transform: `rotateY(${rotation}deg)` }}><Beast kind="bull" /><Beast kind="bear" /></div>
          <div className="titan-attack-line" /><div className="titan-impact"><Zap size={18} /></div><div className="titan-winner"><Target size={12} /> {isBull ? "BULL WINS" : isBear ? "BEAR WINS" : "NEUTRAL"}</div><div className="titan-rotate"><Rotate3D size={14} /> DRAG TO ROTATE • 3D</div>
        </div>
        <div className="titan-battle-foot"><span><i /> LIVE REGIME ENGINE</span><span>30 SEC REFRESH</span><span>CSS 3D ENGINE</span></div>
      </div>
      <aside className="titan-insights">
        <div className="titan-panel"><div className="titan-panel-title">AI MARKET SENTIMENT</div><div className="titan-gauge"><div className="titan-gauge-arc" /><strong>{Math.round(numericScore)}</strong><span className={isBear ? "down" : isBull ? "up" : "flat"}>{isBear ? "BEARISH" : isBull ? "BULLISH" : "NEUTRAL"}</span></div>{[["Momentum", isBear ? 22 : isBull ? 81 : 50], ["Volume", isBear ? 28 : isBull ? 74 : 50], ["News", isBear ? 33 : isBull ? 79 : 50], ["Technical", isBear ? 29 : isBull ? 76 : 50], ["Overall", Math.round(numericScore)]].map(([n, v]) => <div className="titan-meter" key={n}><span>{n}</span><i><b style={{ width: `${v}%` }} /></i><em>{v}%</em></div>)}</div>
        <div className="titan-panel"><div className="titan-panel-title">MARKET SIGNAL <small>INDEX ENGINE</small></div><div className="titan-mover"><span><b>{isBull ? "BULLISH MOMENTUM" : isBear ? "BEARISH PRESSURE" : "NEUTRAL FLOW"}</b></span><em className={isBull ? "up" : isBear ? "down" : "flat"}>{Math.round(numericScore)}%</em></div><div className="titan-mover"><span>Regime confidence</span><small>LIVE</small><em className="up">AI</em></div><div className="titan-mover"><span>Index universe</span><small>GLOBAL</small><em className="up">LIVE</em></div></div>
      </aside>
    </div>
  )
}
