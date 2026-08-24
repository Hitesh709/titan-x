"use client"

import { useEffect, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"
import { Rotate3D, Sparkles, Target, Zap } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

type ThreeModule = any

type Winner = "bull" | "bear" | "neutral"

function buildBeast(THREE: ThreeModule, kind: "bull" | "bear") {
  const group = new THREE.Group()
  const bull = kind === "bull"
  const primary = new THREE.MeshPhysicalMaterial({
    color: bull ? 0x17212b : 0x172a26,
    metalness: 0.9,
    roughness: 0.22,
    clearcoat: 0.8,
    emissive: bull ? 0x180000 : 0x00170c,
    emissiveIntensity: 0.42,
  })
  const accent = new THREE.MeshPhysicalMaterial({
    color: bull ? 0xff284a : 0x27e58b,
    metalness: 0.8,
    roughness: 0.2,
    emissive: bull ? 0xff071f : 0x00a95c,
    emissiveIntensity: 1.6,
  })
  const dark = new THREE.MeshStandardMaterial({ color: 0x050a10, metalness: 0.8, roughness: 0.3 })

  const mesh = (geometry: any, material: any, position: [number, number, number], scale?: [number, number, number]) => {
    const m = new THREE.Mesh(geometry, material)
    m.position.set(...position)
    if (scale) m.scale.set(...scale)
    m.castShadow = true
    m.receiveShadow = true
    group.add(m)
    return m
  }

  mesh(new THREE.IcosahedronGeometry(1.2, 2), primary, [0, 1.35, 0], bull ? [1.45, 0.95, 2.0] : [1.55, 1.05, 1.85])
  mesh(new THREE.IcosahedronGeometry(0.82, 2), primary, [0, 2.25, -1.05], bull ? [0.95, 0.8, 1.0] : [1.05, 0.88, 0.95])
  mesh(new THREE.CylinderGeometry(0.35, 0.55, 1.1, 8), dark, [0, 1.0, 1.15], [1, 1, 0.8])

  const legGeo = new THREE.CylinderGeometry(0.18, 0.28, 1.35, 8)
  ;[[-0.7, 0.45, -0.55], [0.7, 0.45, -0.55], [-0.62, 0.45, 0.65], [0.62, 0.45, 0.65]].forEach(([x, y, z]) => {
    const leg = mesh(legGeo, primary, [x, y, z])
    leg.rotation.z = x > 0 ? -0.08 : 0.08
  })

  const hornGeo = new THREE.ConeGeometry(0.22, 1.05, 8)
  if (bull) {
    const h1 = mesh(hornGeo, accent, [-0.52, 2.75, -1.0], [1, 1, 1.15])
    const h2 = mesh(hornGeo, accent, [0.52, 2.75, -1.0], [1, 1, 1.15])
    h1.rotation.z = -0.55; h2.rotation.z = 0.55
  } else {
    const earGeo = new THREE.ConeGeometry(0.28, 0.55, 6)
    const e1 = mesh(earGeo, accent, [-0.65, 2.75, -1.0]); const e2 = mesh(earGeo, accent, [0.65, 2.75, -1.0])
    e1.rotation.z = -0.35; e2.rotation.z = 0.35
  }

  const eyeGeo = new THREE.SphereGeometry(0.075, 12, 12)
  mesh(eyeGeo, accent, [-0.28, 2.38, -1.72]); mesh(eyeGeo, accent, [0.28, 2.38, -1.72])
  const jaw = mesh(new THREE.IcosahedronGeometry(0.34, 1), dark, [0, 2.0, -1.58], [1.2, 0.65, 0.85])
  if (!bull) jaw.rotation.x = 0.15

  const spineGeo = new THREE.TorusGeometry(1.15, 0.025, 6, 32, Math.PI)
  const spine = mesh(spineGeo, accent, [0, 1.5, 0.1], [1, 1, 1.3])
  spine.rotation.x = Math.PI / 2

  group.rotation.y = bull ? Math.PI * 0.18 : -Math.PI * 0.18
  group.scale.setScalar(bull ? 1.05 : 1.0)
  return group
}

export default function MarketBattle() {
  const { score, regime, markets } = usePublicMarket()
  const hostRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<any>(null)
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
        const camera = new THREE.PerspectiveCamera(34, host.clientWidth / Math.max(host.clientHeight, 1), 0.1, 100)
        camera.position.set(0, 3.1, 11.5)
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" })
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        renderer.setSize(host.clientWidth, host.clientHeight)
        renderer.shadowMap.enabled = true
        renderer.shadowMap.type = THREE.PCFSoftShadowMap
        renderer.outputColorSpace = THREE.SRGBColorSpace
        host.innerHTML = ""
        host.appendChild(renderer.domElement)

        const arena = new THREE.Group()
        scene.add(arena)
        const floor = new THREE.Mesh(new THREE.CylinderGeometry(4.25, 4.25, 0.25, 96), new THREE.MeshPhysicalMaterial({ color: 0x050a12, metalness: 0.95, roughness: 0.25, clearcoat: 1 }))
        floor.receiveShadow = true
        floor.position.y = -0.05
        arena.add(floor)
        const ring = new THREE.Mesh(new THREE.TorusGeometry(4.15, 0.055, 8, 128), new THREE.MeshBasicMaterial({ color: winner === "bear" ? 0xff204d : 0x24e58a, transparent: true, opacity: 0.9 }))
        ring.position.y = 0.14
        ring.rotation.x = Math.PI / 2
        arena.add(ring)
        const inner = new THREE.Mesh(new THREE.TorusGeometry(3.55, 0.018, 6, 128), new THREE.MeshBasicMaterial({ color: 0x2ca9ff, transparent: true, opacity: 0.55 }))
        inner.position.y = 0.16; inner.rotation.x = Math.PI / 2; arena.add(inner)

        const bull = buildBeast(THREE, "bull")
        const bear = buildBeast(THREE, "bear")
        bull.position.set(-2.0, 0.1, 0)
        bear.position.set(2.0, 0.1, 0)
        bull.rotation.y += 0.35
        bear.rotation.y -= 0.35
        arena.add(bull, bear)

        const particleGeo = new THREE.BufferGeometry()
        const positions = new Float32Array(180 * 3)
        for (let i = 0; i < positions.length; i += 3) {
          const a = Math.random() * Math.PI * 2; const r = 4.5 + Math.random() * 3.5
          positions[i] = Math.cos(a) * r; positions[i + 1] = Math.random() * 3.8; positions[i + 2] = Math.sin(a) * r
        }
        particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3))
        const particles = new THREE.Points(particleGeo, new THREE.PointsMaterial({ color: 0x4ebaff, size: 0.035, transparent: true, opacity: 0.65 }))
        scene.add(particles)

        scene.add(new THREE.HemisphereLight(0x9bdcff, 0x05070d, 1.3))
        const key = new THREE.DirectionalLight(winner === "bear" ? 0xff3159 : 0x5fffb0, 4.5)
        key.position.set(3, 7, 5); key.castShadow = true; key.shadow.mapSize.set(1024, 1024); scene.add(key)
        const fill = new THREE.PointLight(0x2f8cff, 3, 14); fill.position.set(-4, 3, 4); scene.add(fill)
        const rim = new THREE.PointLight(winner === "bear" ? 0xff183f : 0x00d890, 3.5, 12); rim.position.set(4, 2, -3); scene.add(rim)

        const clock = new THREE.Clock()
        let frame = 0
        const animate = () => {
          frame = requestAnimationFrame(animate)
          const t = clock.getElapsedTime()
          arena.rotation.y = rotation * Math.PI / 180
          bull.position.y = 0.1 + Math.sin(t * 2.2) * 0.035
          bear.position.y = 0.1 + Math.sin(t * 2.0 + 1.2) * 0.035
          bull.rotation.z = Math.sin(t * 1.4) * 0.018
          bear.rotation.z = Math.sin(t * 1.25 + 0.8) * 0.018
          particles.rotation.y = t * 0.025
          renderer.render(scene, camera)
        }
        animate()

        const resize = () => {
          if (!host.clientWidth || !host.clientHeight) return
          camera.aspect = host.clientWidth / host.clientHeight; camera.updateProjectionMatrix(); renderer.setSize(host.clientWidth, host.clientHeight)
        }
        window.addEventListener("resize", resize)
        cleanup = () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); renderer.dispose(); host.innerHTML = "" }
      } catch {
        cleanup = () => {}
      }
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
