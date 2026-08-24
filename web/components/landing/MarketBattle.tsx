"use client"

import { useEffect, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"
import { Rotate3D, Sparkles } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"
import "./MarketBattle.css"

type ThreeModule = any
type Winner = "bull" | "bear" | "neutral"

function buildBeast(THREE: ThreeModule, kind: "bull" | "bear") {
  const group = new THREE.Group()
  const bull = kind === "bull"
  const primary = new THREE.MeshPhysicalMaterial({ color: bull ? 0x182b31 : 0x272424, metalness: 0.72, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.12, emissive: bull ? 0x06301f : 0x30070c, emissiveIntensity: 0.72 })
  const accentColor = bull ? 0x18f39a : 0xff3558
  const accent = new THREE.MeshPhysicalMaterial({ color: accentColor, metalness: 0.42, roughness: 0.16, clearcoat: 1, emissive: accentColor, emissiveIntensity: 2.8 })
  const dark = new THREE.MeshStandardMaterial({ color: 0x070b10, metalness: 0.5, roughness: 0.28 })
  const mesh = (geometry: any, material: any, position: [number, number, number], scale?: [number, number, number]) => { const m = new THREE.Mesh(geometry, material); m.position.set(...position); if (scale) m.scale.set(...scale); m.castShadow = true; m.receiveShadow = true; group.add(m); return m }
  mesh(new THREE.SphereGeometry(1, 40, 26), primary, [0, 1.35, 0], bull ? [1.5, 0.92, 1.85] : [1.6, 1.02, 1.78])
  mesh(new THREE.SphereGeometry(0.82, 36, 24), primary, [0, 2.18, -0.96], bull ? [0.96, 0.9, 1] : [1.08, 0.96, 1.05])
  mesh(new THREE.SphereGeometry(0.42, 28, 18), dark, [0, 2.02, -1.62], bull ? [1.12, 0.72, 0.78] : [1.18, 0.76, 0.86])
  mesh(new THREE.SphereGeometry(0.7, 28, 18), primary, [-0.86, 1.52, -0.34], [0.62, 0.88, 0.9])
  mesh(new THREE.SphereGeometry(0.7, 28, 18), primary, [0.86, 1.52, -0.34], [0.62, 0.88, 0.9])
  const legGeo = new THREE.CylinderGeometry(0.17, 0.28, 1.28, 18)
  ;[[-0.7, 0.42, -0.58], [0.7, 0.42, -0.58], [-0.62, 0.42, 0.58], [0.62, 0.42, 0.58]].forEach(([x, y, z]) => mesh(legGeo, primary, [x, y, z]))
  const footGeo = new THREE.SphereGeometry(0.27, 20, 14)
  ;[[-0.7, -0.15, -0.72], [0.7, -0.15, -0.72], [-0.62, -0.15, 0.66], [0.62, -0.15, 0.66]].forEach(([x, y, z]) => mesh(footGeo, dark, [x, y, z], [1.2, 0.55, 1.35]))
  if (bull) { const horn = new THREE.ConeGeometry(0.2, 1.25, 18); const h1 = mesh(horn, accent, [-0.55, 2.78, -0.86]); const h2 = mesh(horn, accent, [0.55, 2.78, -0.86]); h1.rotation.z = -0.62; h2.rotation.z = 0.62; h1.rotation.x = -0.12; h2.rotation.x = -0.12 }
  else { const ear = new THREE.SphereGeometry(0.3, 22, 14); mesh(ear, accent, [-0.7, 2.76, -0.78], [1.25, 0.7, 0.82]); mesh(ear, accent, [0.7, 2.76, -0.78], [1.25, 0.7, 0.82]) }
  const eye = new THREE.SphereGeometry(0.1, 18, 12); mesh(eye, accent, [-0.3, 2.34, -1.65]); mesh(eye, accent, [0.3, 2.34, -1.65])
  const rim = mesh(new THREE.TorusGeometry(1.12, 0.035, 8, 48, Math.PI), accent, [0, 1.44, 0.1], [1, 1, 1.28]); rim.rotation.x = Math.PI / 2
  const tail = mesh(new THREE.CylinderGeometry(0.07, 0.14, 0.9, 12), accent, [0, 1.38, 1.7]); tail.rotation.x = bull ? -0.7 : 0.55
  group.scale.setScalar(1.12); group.rotation.y = bull ? 0.18 : -0.18
  return group
}

export default function MarketBattle() {
  const { score, regime, markets } = usePublicMarket()
  const hostRef = useRef<HTMLDivElement>(null)
  const rotationRef = useRef(0)
  const [rotation, setRotation] = useState(0)
  const [dragging, setDragging] = useState(false)
  const drag = useRef({ active: false, x: 0, rotation: 0 })
  const numericScore = typeof score === "number" ? score : 50
  const normalized = (regime || "").toLowerCase()
  const winner: Winner = normalized.includes("bear") || numericScore < 45 ? "bear" : normalized.includes("bull") || numericScore > 55 ? "bull" : "neutral"
  const isBull = winner === "bull"
  const isBear = winner === "bear"
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
        const camera = new THREE.PerspectiveCamera(28, Math.max(host.clientWidth, 280) / Math.max(host.clientHeight, 420), 0.1, 100)
        camera.position.set(0, 2.9, 14.5); camera.lookAt(0, 1.5, 0)
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" })
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setSize(Math.max(host.clientWidth, 280), Math.max(host.clientHeight, 420)); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.35
        host.innerHTML = ""; host.appendChild(renderer.domElement)
        const arena = new THREE.Group(); scene.add(arena)
        const floor = new THREE.Mesh(new THREE.CylinderGeometry(5.3, 5.3, 0.22, 96), new THREE.MeshPhysicalMaterial({ color: 0x050b12, metalness: 0.9, roughness: 0.2, clearcoat: 1 })); floor.position.y = -0.16; floor.receiveShadow = true; arena.add(floor)
        const bullRing = new THREE.Mesh(new THREE.TorusGeometry(2.05, 0.055, 10, 128), new THREE.MeshBasicMaterial({ color: 0x18f39a })); bullRing.position.set(-2.35, 0.06, 0); bullRing.rotation.x = Math.PI / 2; arena.add(bullRing)
        const bearRing = new THREE.Mesh(new THREE.TorusGeometry(2.05, 0.055, 10, 128), new THREE.MeshBasicMaterial({ color: 0xff3558 })); bearRing.position.set(2.35, 0.06, 0); bearRing.rotation.x = Math.PI / 2; arena.add(bearRing)
        const outerRing = new THREE.Mesh(new THREE.TorusGeometry(4.95, 0.045, 8, 144), new THREE.MeshBasicMaterial({ color: isBull ? 0x18f39a : isBear ? 0xff3558 : 0x42baff, transparent: true, opacity: 0.9 })); outerRing.position.y = 0.08; outerRing.rotation.x = Math.PI / 2; arena.add(outerRing)
        const bull = buildBeast(THREE, "bull"); const bear = buildBeast(THREE, "bear")
        bull.position.set(-2.35, isBull ? 0.52 : -0.02, 0); bear.position.set(2.35, isBear ? 0.52 : -0.02, 0); bull.rotation.x = isBull ? -0.12 : 0.12; bear.rotation.x = isBear ? -0.12 : 0.12; arena.add(bull, bear)
        const particleGeo = new THREE.BufferGeometry(); const positions = new Float32Array(260 * 3)
        for (let i = 0; i < positions.length; i += 3) { const a = Math.random() * Math.PI * 2; const r = 4.7 + Math.random() * 3.2; positions[i] = Math.cos(a) * r; positions[i + 1] = Math.random() * 5.4; positions[i + 2] = Math.sin(a) * r }
        particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3)); scene.add(new THREE.Points(particleGeo, new THREE.PointsMaterial({ color: 0x62cfff, size: 0.045, transparent: true, opacity: 0.72 })))
        scene.add(new THREE.HemisphereLight(0xd8edff, 0x050910, 2.4))
        const key = new THREE.DirectionalLight(0xffffff, 4.8); key.position.set(0, 8, 9); key.castShadow = true; scene.add(key)
        const green = new THREE.PointLight(0x18f39a, 8, 9); green.position.set(-2.5, 3.2, 4.2); scene.add(green)
        const red = new THREE.PointLight(0xff3558, 8, 9); red.position.set(2.5, 3.2, 4.2); scene.add(red)
        const front = new THREE.PointLight(0x9cddff, 4.5, 16); front.position.set(0, 4.5, 8); scene.add(front)
        const winnerLight = new THREE.PointLight(isBull ? 0x18f39a : isBear ? 0xff3558 : 0x4ebaff, 5.5, 10); winnerLight.position.set(isBull ? -2.4 : isBear ? 2.4 : 0, 2.8, 3.2); scene.add(winnerLight)
        const clock = new THREE.Clock(); let frame = 0
        const animate = () => { frame = requestAnimationFrame(animate); const t = clock.getElapsedTime(); arena.rotation.y = rotationRef.current * Math.PI / 180; bull.position.y = (isBull ? 0.52 : -0.02) + Math.sin(t * 1.7) * 0.035; bear.position.y = (isBear ? 0.52 : -0.02) + Math.sin(t * 1.55 + 0.7) * 0.035; bull.rotation.z = Math.sin(t * 1.2) * 0.018; bear.rotation.z = Math.sin(t * 1.1 + 0.8) * 0.018; renderer.render(scene, camera) }
        animate()
        const resize = () => { const w = Math.max(host.clientWidth, 280); const h = Math.max(host.clientHeight, 420); camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h) }
        window.addEventListener("resize", resize)
        cleanup = () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); renderer.dispose(); host.innerHTML = "" }
      } catch { cleanup = () => {} }
    }
    load(); return () => { disposed = true; cleanup() }
  }, [winner])

  const down = (e: ReactPointerEvent<HTMLDivElement>) => { drag.current = { active: true, x: e.clientX, rotation }; setDragging(true); e.currentTarget.setPointerCapture(e.pointerId) }
  const move = (e: ReactPointerEvent<HTMLDivElement>) => { if (drag.current.active) { const next = drag.current.rotation + (e.clientX - drag.current.x) * 0.22; rotationRef.current = next; setRotation(next) } }
  const up = (e: ReactPointerEvent<HTMLDivElement>) => { drag.current.active = false; setDragging(false); e.currentTarget.releasePointerCapture?.(e.pointerId) }

  return <div className={`titan-battle titan-webgl-battle ${isBear ? "is-bear" : isBull ? "is-bull" : "is-neutral"}`}>
    <div className="titan-battle-main">
      <div className="titan-battle-head"><div><div className="titan-kicker"><Sparkles size={12}/> AI MARKET REGIME</div><div className="titan-battle-title">{isBull ? "BULL MARKET" : isBear ? "BEAR MARKET" : "MARKET BALANCED"}</div><div className="titan-battle-sub">{isBull ? "BULL ABOVE • BEAR BELOW" : isBear ? "BEAR ABOVE • BULL BELOW" : "WAITING FOR CONFIRMATION"}</div></div><div className="titan-score"><small>AI SCORE</small><strong>{Math.round(numericScore)}</strong></div></div>
      <div className={`titan-webgl-canvas ${dragging ? "dragging" : ""}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <div className="battle-hud top-left"><span>MARKET REGIME</span><b>{isBull ? "BULLISH" : isBear ? "BEARISH" : "NEUTRAL"}</b><i/></div>
        <div className="battle-hud top-right"><span>INDEX BREADTH</span><b>{positive} UP</b><em>{negative} DOWN</em></div>
        <div ref={hostRef} className="titan-webgl-host" />
        <div className="beast-label bull-label">BULL<small>{isBull ? "DOMINANT / ABOVE" : "BELOW / RESTING"}</small></div>
        <div className="beast-label bear-label">BEAR<small>{isBear ? "DOMINANT / ABOVE" : "BELOW / RESTING"}</small></div>
        <div className="titan-winner">{isBull ? "▲ BULL MARKET • BULL POSITION UP" : isBear ? "▲ BEAR MARKET • BEAR POSITION UP" : "◆ MARKET BALANCED"}</div>
        <div className="titan-rotate"><Rotate3D size={12}/> DRAG TO ROTATE • VIEW MARKET STATE</div>
      </div>
    </div>
  </div>
}
