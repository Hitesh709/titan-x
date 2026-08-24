"use client"

import { useEffect, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"
import { Rotate3D, Sparkles, Target, Zap } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"
import "./MarketBattle.css"

type ThreeModule = any
type Winner = "bull" | "bear" | "neutral"

function buildBeast(THREE: ThreeModule, kind: "bull" | "bear") {
  const group = new THREE.Group()
  const bull = kind === "bull"
  const bodyColor = bull ? 0x263a4b : 0x30423a
  const accentColor = bull ? 0xff365b : 0x20f29a
  const edgeColor = bull ? 0xff8b9c : 0x72ffd0
  const primary = new THREE.MeshPhysicalMaterial({ color: bodyColor, metalness: 0.68, roughness: 0.24, clearcoat: 1, clearcoatRoughness: 0.14, emissive: bull ? 0x240812 : 0x062a1c, emissiveIntensity: 0.55 })
  const accent = new THREE.MeshPhysicalMaterial({ color: accentColor, metalness: 0.45, roughness: 0.18, clearcoat: 1, emissive: accentColor, emissiveIntensity: 2.8 })
  const edge = new THREE.MeshBasicMaterial({ color: edgeColor })
  const dark = new THREE.MeshStandardMaterial({ color: 0x111a23, metalness: 0.45, roughness: 0.32 })

  const mesh = (geometry: any, material: any, position: [number, number, number], scale?: [number, number, number]) => {
    const m = new THREE.Mesh(geometry, material)
    m.position.set(...position)
    if (scale) m.scale.set(...scale)
    m.castShadow = true
    m.receiveShadow = true
    group.add(m)
    return m
  }

  mesh(new THREE.SphereGeometry(1, 32, 20), primary, [0, 1.38, 0], bull ? [1.55, 0.92, 2.0] : [1.62, 1.02, 1.85])
  mesh(new THREE.SphereGeometry(0.78, 28, 18), primary, [0, 2.22, -1.02], bull ? [0.98, 0.86, 0.98] : [1.05, 0.92, 1.02])
  mesh(new THREE.SphereGeometry(0.42, 24, 16), dark, [0, 2.03, -1.72], bull ? [1.1, 0.72, 0.82] : [1.18, 0.78, 0.9])
  mesh(new THREE.SphereGeometry(0.72, 24, 16), primary, [-0.82, 1.55, -0.42], [0.65, 0.85, 0.85])
  mesh(new THREE.SphereGeometry(0.72, 24, 16), primary, [0.82, 1.55, -0.42], [0.65, 0.85, 0.85])

  const legGeo = new THREE.CylinderGeometry(0.18, 0.30, 1.30, 16)
  ;[[-0.72, 0.48, -0.62], [0.72, 0.48, -0.62], [-0.62, 0.48, 0.62], [0.62, 0.48, 0.62]].forEach(([x, y, z]) => {
    const leg = mesh(legGeo, primary, [x, y, z])
    leg.rotation.z = x > 0 ? -0.07 : 0.07
  })
  const footGeo = new THREE.SphereGeometry(0.28, 18, 12)
  ;[[-0.72, -0.16, -0.78], [0.72, -0.16, -0.78], [-0.62, -0.16, 0.68], [0.62, -0.16, 0.68]].forEach(([x, y, z]) => mesh(footGeo, dark, [x, y, z], [1.2, 0.55, 1.35]))

  if (bull) {
    const hornGeo = new THREE.ConeGeometry(0.22, 1.18, 16)
    const h1 = mesh(hornGeo, accent, [-0.56, 2.80, -1.0], [1, 1, 1.25])
    const h2 = mesh(hornGeo, accent, [0.56, 2.80, -1.0], [1, 1, 1.25])
    h1.rotation.z = -0.65; h2.rotation.z = 0.65
    h1.rotation.x = -0.15; h2.rotation.x = -0.15
  } else {
    const earGeo = new THREE.SphereGeometry(0.28, 18, 12)
    mesh(earGeo, accent, [-0.68, 2.78, -0.88], [1.25, 0.7, 0.8])
    mesh(earGeo, accent, [0.68, 2.78, -0.88], [1.25, 0.7, 0.8])
    const inner = new THREE.SphereGeometry(0.13, 16, 10)
    mesh(inner, dark, [-0.68, 2.78, -1.12], [1.1, 0.7, 0.7])
    mesh(inner, dark, [0.68, 2.78, -1.12], [1.1, 0.7, 0.7])
  }

  const eyeGeo = new THREE.SphereGeometry(0.095, 18, 12)
  mesh(eyeGeo, accent, [-0.30, 2.38, -1.72])
  mesh(eyeGeo, accent, [0.30, 2.38, -1.72])
  mesh(new THREE.SphereGeometry(0.13, 16, 10), edge, [0, 2.03, -2.05], [1.5, 0.65, 0.7])

  const spine = mesh(new THREE.TorusGeometry(1.18, 0.035, 8, 48, Math.PI), accent, [0, 1.48, 0.15], [1, 1, 1.35])
  spine.rotation.x = Math.PI / 2
  const tail = mesh(new THREE.CylinderGeometry(0.08, 0.15, 0.9, 12), edge, [0, 1.38, 1.82])
  tail.rotation.x = bull ? -0.65 : 0.65

  group.rotation.y = bull ? Math.PI * 0.18 : -Math.PI * 0.18
  group.scale.setScalar(1.08)
  return group
}

export default function MarketBattle() {
  const { score, regime, markets } = usePublicMarket()
  const hostRef = useRef<HTMLDivElement>(null)
  const [rotation, setRotation] = useState(0)
  const [dragging, setDragging] = useState(false)
  const drag = useRef({ active: false, x: 0, rotation: 0 })
  const numericScore = typeof score === "number" ? score : 50
  const normalized = (regime || "").toLowerCase()
  const winner: Winner = normalized.includes("bear") || numericScore < 45 ? "bear" : normalized.includes("bull") || numericScore > 55 ? "bull" : "neutral"
  const positive = markets.filter(m => typeof m.change_pct === "number" && m.change_pct > 0).length
  const negative = markets.filter(m => typeof m.change_pct === "number" && m.change_pct < 0).length

  useEffect(() => {
    let disposed = false
    let cleanup = () => {}
    const load = async () => {
      if (!hostRef.current) return
      try {
        const THREE: ThreeModule = await import(/* webpackIgnore: true */ "https://unpkg.com/three@0.164.1/build/three.module.js")
        if (disposed || !hostRef.current) return
        const host = hostRef.current
        const scene = new THREE.Scene()
        const camera = new THREE.PerspectiveCamera(30, Math.max(host.clientWidth, 280) / Math.max(host.clientHeight, 420), 0.1, 100)
        camera.position.set(0, 3.0, 13.5)
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" })
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        renderer.setSize(Math.max(host.clientWidth, 280), Math.max(host.clientHeight, 420))
        renderer.shadowMap.enabled = true
        renderer.shadowMap.type = THREE.PCFSoftShadowMap
        renderer.outputColorSpace = THREE.SRGBColorSpace
        renderer.toneMapping = THREE.ACESFilmicToneMapping
        renderer.toneMappingExposure = 1.25
        host.innerHTML = ""
        host.appendChild(renderer.domElement)

        const arena = new THREE.Group()
        scene.add(arena)
        const floor = new THREE.Mesh(new THREE.CylinderGeometry(4.9, 4.9, 0.24, 96), new THREE.MeshPhysicalMaterial({ color: 0x07101b, metalness: 0.82, roughness: 0.24, clearcoat: 1 }))
        floor.receiveShadow = true
        floor.position.y = -0.12
        arena.add(floor)
        const ringColor = winner === "bear" ? 0xff174e : winner === "bull" ? 0x18f39a : 0x4ebaff
        const ring = new THREE.Mesh(new THREE.TorusGeometry(4.65, 0.075, 10, 144), new THREE.MeshBasicMaterial({ color: ringColor }))
        ring.position.y = 0.12; ring.rotation.x = Math.PI / 2; arena.add(ring)
        const inner = new THREE.Mesh(new THREE.TorusGeometry(3.75, 0.025, 8, 128), new THREE.MeshBasicMaterial({ color: 0x38aaff, transparent: true, opacity: 0.75 }))
        inner.position.y = 0.15; inner.rotation.x = Math.PI / 2; arena.add(inner)

        const bull = buildBeast(THREE, "bull")
        const bear = buildBeast(THREE, "bear")
        bull.position.set(-2.05, 0.18, 0)
        bear.position.set(2.05, 0.18, 0)
        bull.rotation.y += 0.25; bear.rotation.y -= 0.25
        arena.add(bull, bear)

        const particleGeo = new THREE.BufferGeometry()
        const positions = new Float32Array(240 * 3)
        for (let i = 0; i < positions.length; i += 3) {
          const a = Math.random() * Math.PI * 2; const r = 4.5 + Math.random() * 3.5
          positions[i] = Math.cos(a) * r; positions[i + 1] = Math.random() * 5; positions[i + 2] = Math.sin(a) * r
        }
        particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3))
        scene.add(new THREE.Points(particleGeo, new THREE.PointsMaterial({ color: 0x5fc8ff, size: 0.045, transparent: true, opacity: 0.8 })))

        scene.add(new THREE.HemisphereLight(0xc9eaff, 0x07101a, 2.0))
        const key = new THREE.DirectionalLight(0xffffff, 4.0)
        key.position.set(0, 8, 8); key.castShadow = true; key.shadow.mapSize.set(1024, 1024); scene.add(key)
        const bullLight = new THREE.PointLight(0xff284f, 7.0, 9); bullLight.position.set(-3.5, 2.8, 4.0); scene.add(bullLight)
        const bearLight = new THREE.PointLight(0x18f29a, 7.0, 9); bearLight.position.set(3.5, 2.8, 4.0); scene.add(bearLight)
        const front = new THREE.PointLight(0x8fd7ff, 4.0, 14); front.position.set(0, 4.0, 8.0); scene.add(front)
        const winnerLight = new THREE.PointLight(ringColor, 6.0, 10)
        winnerLight.position.set(winner === "bear" ? 3 : winner === "bull" ? -3 : 0, 2.0, 2.0); scene.add(winnerLight)

        const clock = new THREE.Clock()
        let frame = 0
        const animate = () => {
          frame = requestAnimationFrame(animate)
          const t = clock.getElapsedTime()
          arena.rotation.y = rotation * Math.PI / 180
          const bullBase = winner === "bull" ? -0.55 : winner === "bear" ? -2.25 : -2.0
          const bearBase = winner === "bear" ? 0.55 : winner === "bull" ? 2.25 : 2.0
          const attack = winner !== "neutral" ? Math.abs(Math.sin(t * 1.7)) * 0.24 : 0
          bull.position.x = bullBase + (winner === "bull" ? attack : 0)
          bear.position.x = bearBase - (winner === "bear" ? attack : 0)
          bull.position.y = 0.18 + Math.sin(t * 2.0) * 0.045
          bear.position.y = 0.18 + Math.sin(t * 1.8 + 1.1) * 0.045
          bull.rotation.z = Math.sin(t * 1.4) * 0.022
          bear.rotation.z = Math.sin(t * 1.25 + 0.8) * 0.022
          if (winner === "bull") { bull.rotation.x = -0.045 - Math.abs(Math.sin(t * 1.7)) * 0.035; bear.rotation.x = 0.02 }
          if (winner === "bear") { bear.rotation.x = -0.045 - Math.abs(Math.sin(t * 1.7)) * 0.035; bull.rotation.x = 0.02 }
          renderer.render(scene, camera)
        }
        animate()

        const resize = () => {
          const w = Math.max(host.clientWidth, 280); const h = Math.max(host.clientHeight, 420)
          camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h)
        }
        window.addEventListener("resize", resize)
        cleanup = () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); renderer.dispose(); host.innerHTML = "" }
      } catch { cleanup = () => {} }
    }
    load()
    return () => { disposed = true; cleanup() }
  }, [winner])

  const down = (e: ReactPointerEvent<HTMLDivElement>) => { drag.current = { active: true, x: e.clientX, rotation }; setDragging(true); e.currentTarget.setPointerCapture(e.pointerId) }
  const move = (e: ReactPointerEvent<HTMLDivElement>) => { if (drag.current.active) setRotation(drag.current.rotation + (e.clientX - drag.current.x) * 0.22) }
  const up = (e: ReactPointerEvent<HTMLDivElement>) => { drag.current.active = false; setDragging(false); e.currentTarget.releasePointerCapture?.(e.pointerId) }
  const isBull = winner === "bull"; const isBear = winner === "bear"

  return <div className={`titan-battle titan-webgl-battle ${isBear ? "is-bear" : isBull ? "is-bull" : "is-neutral"}`}>
    <div className="titan-battle-main">
      <div className="titan-battle-head"><div><div className="titan-kicker"><Sparkles size={12}/> AI MARKET REGIME</div><div className="titan-battle-title">{isBull ? "BULL MARKET" : isBear ? "BEAR MARKET" : "MARKET BALANCED"}</div><div className="titan-battle-sub">{isBull ? "BULL DOMINATING • BUY PRESSURE" : isBear ? "BEAR DOMINATING • SELL PRESSURE" : "WAITING FOR CONFIRMATION"}</div></div><div className="titan-score"><small>AI SCORE</small><b>{Math.round(numericScore)}</b></div></div>
      <div className={`titan-canvas titan-webgl-canvas ${dragging ? "dragging" : ""}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <div ref={hostRef} className="titan-webgl-host" />
        <div className="beast-label bull-label">BULL <small>BUY FORCE</small></div>
        <div className="beast-label bear-label">BEAR <small>SELL FORCE</small></div>
        <div className="battle-hud top-left">INDEX BREADTH <b>{positive} ↑</b> <em>{negative} ↓</em></div>
        <div className="battle-hud top-right">LIVE 3D ENGINE <i /></div>
        <div className="titan-attack-line" />
        <div className="titan-impact"><Zap size={18}/></div>
        <div className="titan-winner"><Target size={12}/> {isBull ? "BULL WINS" : isBear ? "BEAR WINS" : "NEUTRAL"}</div>
        <div className="titan-rotate"><Rotate3D size={14}/> DRAG TO ROTATE • WEBGL 3D</div>
      </div>
      <div className="titan-battle-foot"><span><i/> LIVE REGIME ENGINE</span><span>30 SEC REFRESH</span><span>WEBGL / GPU</span></div>
    </div>
    <aside className="titan-insights">
      <div className="titan-panel"><div className="titan-panel-title">AI MARKET SENTIMENT</div><div className="titan-gauge"><div className="titan-gauge-arc"/><strong>{Math.round(numericScore)}</strong><span className={isBear ? "down" : isBull ? "up" : "flat"}>{isBear ? "BEARISH" : isBull ? "BULLISH" : "NEUTRAL"}</span></div>{[["Momentum",isBear?22:isBull?81:50],["Volume",isBear?28:isBull?74:50],["News",isBear?33:isBull?79:50],["Technical",isBear?29:isBull?76:50],["Overall",Math.round(numericScore)]].map(([n,v])=><div className="titan-meter" key={String(n)}><span>{n}</span><i><b style={{width:`${v}%`}}/></i><em>{v}%</em></div>)}</div>
      <div className="titan-panel"><div className="titan-panel-title">INDEX INTELLIGENCE <small>GLOBAL</small></div><div className="titan-mover"><span><b>{isBull?"BULLISH MOMENTUM":isBear?"BEARISH PRESSURE":"NEUTRAL FLOW"}</b></span><em className={isBull?"up":isBear?"down":"flat"}>{Math.round(numericScore)}%</em></div><div className="titan-mover"><span>Indices positive</span><small>{positive}</small><em className="up">LIVE</em></div><div className="titan-mover"><span>Indices negative</span><small>{negative}</small><em className="down">LIVE</em></div></div>
    </aside>
  </div>
}
