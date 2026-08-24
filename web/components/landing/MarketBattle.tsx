"use client"

import Script from "next/script"
import { useEffect, useRef, useState } from "react"
import { Rotate3D, Sparkles, Target } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

declare global {
  interface Window { THREE?: any }
}

type Winner = "bull" | "bear" | "neutral"

function buildBeast(THREE: any, kind: "bull" | "bear", winner: Winner) {
  const group = new THREE.Group()
  const isBull = kind === "bull"
  const color = isBull ? 0x39e6a0 : 0xff315c
  const dark = isBull ? 0x071b17 : 0x21070d
  const material = new THREE.MeshStandardMaterial({ color, metalness: 0.72, roughness: 0.27, flatShading: true, emissive: color, emissiveIntensity: 0.08 })
  const darkMat = new THREE.MeshStandardMaterial({ color: dark, metalness: 0.85, roughness: 0.2, flatShading: true })
  const hornMat = new THREE.MeshStandardMaterial({ color: 0xd7e4ea, metalness: 0.85, roughness: 0.18, flatShading: true })
  const eyeMat = new THREE.MeshBasicMaterial({ color: isBull ? 0x5effc2 : 0xff6d88 })

  const mesh = (geometry: any, mat: any, position: [number, number, number], scale?: [number, number, number]) => {
    const m = new THREE.Mesh(geometry, mat)
    m.position.set(...position)
    if (scale) m.scale.set(...scale)
    m.castShadow = true
    m.receiveShadow = true
    group.add(m)
    return m
  }

  mesh(new THREE.IcosahedronGeometry(1, 2), material, [0, 0.95, 0], [1.65, 1.0, 0.78])
  mesh(new THREE.IcosahedronGeometry(0.72, 2), material, [isBull ? 1.15 : -1.15, 1.32, 0], [0.9, 0.82, 0.72])
  mesh(new THREE.IcosahedronGeometry(0.42, 1), darkMat, [isBull ? 1.68 : -1.68, 1.15, 0], [0.72, 0.46, 0.55])

  const legGeo = new THREE.CylinderGeometry(0.18, 0.23, 1.15, 8)
  const hoofGeo = new THREE.BoxGeometry(0.42, 0.2, 0.48)
  ;[-0.9, 0.85].forEach((x) => {
    ;[-0.42, 0.42].forEach((z) => {
      mesh(legGeo, material, [x, 0.08, z])
      mesh(hoofGeo, darkMat, [x + (isBull ? 0.06 : -0.06), -0.52, z])
    })
  })

  if (isBull) {
    const hornGeo = new THREE.ConeGeometry(0.16, 0.9, 12)
    const h1 = mesh(hornGeo, hornMat, [1.0, 1.95, 0.32])
    h1.rotation.z = -0.82
    const h2 = mesh(hornGeo, hornMat, [1.0, 1.95, -0.32])
    h2.rotation.z = -0.82
    mesh(new THREE.SphereGeometry(0.13, 10, 8), eyeMat, [1.42, 1.52, 0.38])
    mesh(new THREE.SphereGeometry(0.13, 10, 8), eyeMat, [1.42, 1.52, -0.38])
    const tail = mesh(new THREE.ConeGeometry(0.1, 0.9, 8), material, [-1.62, 1.05, 0])
    tail.rotation.z = 1.05
  } else {
    mesh(new THREE.SphereGeometry(0.3, 12, 8), material, [-1.35, 1.9, 0.48])
    mesh(new THREE.SphereGeometry(0.3, 12, 8), material, [-1.35, 1.9, -0.48])
    mesh(new THREE.SphereGeometry(0.1, 10, 8), eyeMat, [-1.58, 1.5, 0.38])
    mesh(new THREE.SphereGeometry(0.1, 10, 8), eyeMat, [-1.58, 1.5, -0.38])
    const armGeo = new THREE.CylinderGeometry(0.23, 0.3, 1.25, 8)
    ;[-0.45, 0.45].forEach((z) => {
      const arm = mesh(armGeo, material, [-0.15, 0.55, z])
      arm.rotation.z = z > 0 ? -0.5 : 0.5
    })
  }

  group.userData.homeX = isBull ? -1.55 : 1.55
  group.userData.attackX = isBull ? 0.72 : -0.72
  group.userData.kind = kind
  group.userData.winner = winner
  group.position.x = group.userData.homeX
  group.rotation.y = isBull ? 0.12 : -0.12
  return group
}

export default function MarketBattle() {
  const { score, regime } = usePublicMarket()
  const hostRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<any>(null)
  const frameRef = useRef<number | null>(null)
  const dragRef = useRef({ active: false, x: 0, rotation: 0 })
  const [threeReady, setThreeReady] = useState(false)
  const [dragging, setDragging] = useState(false)

  const numericScore = typeof score === "number" ? score : 72
  const textRegime = (regime ?? "").toLowerCase()
  const winner: Winner = textRegime.includes("bear") || numericScore <= 40 ? "bear" : textRegime.includes("bull") || numericScore >= 60 ? "bull" : "neutral"

  useEffect(() => {
    if (!threeReady || !hostRef.current || !window.THREE) return
    const THREE = window.THREE
    const host = hostRef.current
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, host.clientWidth / Math.max(host.clientHeight, 1), 0.1, 100)
    camera.position.set(0, 1.8, 9.5)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8))
    renderer.setSize(host.clientWidth, host.clientHeight)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    host.innerHTML = ""
    host.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0x9bdcff, 0x02050a, 1.5))
    const key = new THREE.DirectionalLight(0xffffff, 3.2)
    key.position.set(3, 7, 6)
    key.castShadow = true
    scene.add(key)
    const blue = new THREE.PointLight(0x1e9bff, 9, 9)
    blue.position.set(-3, 1.5, 3)
    scene.add(blue)
    const red = new THREE.PointLight(0xff164e, 8, 8)
    red.position.set(3, 1.5, 2)
    scene.add(red)

    const floor = new THREE.Mesh(new THREE.CylinderGeometry(4.3, 4.3, 0.16, 96), new THREE.MeshStandardMaterial({ color: 0x030914, metalness: 0.85, roughness: 0.2 }))
    floor.position.y = -0.7
    floor.receiveShadow = true
    scene.add(floor)
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.7 })
    const ring = new THREE.Mesh(new THREE.TorusGeometry(3.55, 0.025, 8, 128), ringMat)
    ring.rotation.x = Math.PI / 2
    ring.position.y = -0.6
    scene.add(ring)

    const battle = new THREE.Group()
    const bull = buildBeast(THREE, "bull", winner)
    const bear = buildBeast(THREE, "bear", winner)
    battle.add(bull, bear)
    scene.add(battle)

    const particles = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0x4fc3ff, size: 0.035, transparent: true, opacity: 0.65 }))
    const positions = new Float32Array(240 * 3)
    for (let i = 0; i < positions.length; i += 3) {
      positions[i] = (Math.random() - 0.5) * 8
      positions[i + 1] = Math.random() * 4 - 0.7
      positions[i + 2] = (Math.random() - 0.5) * 3
    }
    particles.geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
    scene.add(particles)

    const resize = () => {
      if (!host.clientWidth) return
      camera.aspect = host.clientWidth / Math.max(host.clientHeight, 1)
      camera.updateProjectionMatrix()
      renderer.setSize(host.clientWidth, host.clientHeight)
    }
    window.addEventListener("resize", resize)

    let previous = performance.now()
    const animate = (now: number) => {
      const dt = Math.min((now - previous) / 1000, 0.05)
      previous = now
      if (!dragRef.current.active) battle.rotation.y += dt * 0.08
      particles.rotation.y += dt * 0.02
      bull.position.y = Math.sin(now * 0.0018) * 0.035
      bear.position.y = Math.sin(now * 0.0018 + 1.4) * 0.035
      renderer.render(scene, camera)
      frameRef.current = requestAnimationFrame(animate)
    }
    frameRef.current = requestAnimationFrame(animate)

    sceneRef.current = { scene, camera, renderer, battle, bull, bear, resize }
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
      window.removeEventListener("resize", resize)
      renderer.dispose()
      scene.traverse((obj: any) => { if (obj.geometry) obj.geometry.dispose?.(); if (obj.material) { const mats = Array.isArray(obj.material) ? obj.material : [obj.material]; mats.forEach((m: any) => m.dispose?.()) } })
      sceneRef.current = null
    }
  }, [threeReady])

  useEffect(() => {
    const state = sceneRef.current
    if (!state) return
    const winnerGroup = winner === "bull" ? state.bull : winner === "bear" ? state.bear : null
    const loserGroup = winner === "bull" ? state.bear : winner === "bear" ? state.bull : null
    const start = performance.now()
    const duration = 1200
    const fromWinner = winnerGroup?.position.x ?? 0
    const toWinner = winnerGroup?.userData.attackX ?? fromWinner
    const fromLoser = loserGroup?.position.x ?? 0
    const toLoser = loserGroup?.userData.homeX ?? fromLoser
    const attack = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
      if (winnerGroup) winnerGroup.position.x = fromWinner + (toWinner - fromWinner) * eased
      if (loserGroup) loserGroup.position.x = fromLoser + (toLoser - fromLoser) * eased
      if (t < 1) requestAnimationFrame(attack)
    }
    requestAnimationFrame(attack)
  }, [winner])

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    dragRef.current = { active: true, x: e.clientX, rotation: sceneRef.current?.battle.rotation.y ?? 0 }
    setDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active || !sceneRef.current) return
    sceneRef.current.battle.rotation.y = dragRef.current.rotation + (e.clientX - dragRef.current.x) * 0.008
  }
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    dragRef.current.active = false
    setDragging(false)
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  return (
    <div className={`battle-shell-3d battle-${winner}`}>
      <Script src="https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.min.js" strategy="afterInteractive" onLoad={() => setThreeReady(true)} />
      <div className="battle-header-3d">
        <div><div className="battle-kicker"><Sparkles size={13} /> AI MARKET SENTIMENT</div><div className="battle-title">{winner === "bear" ? "BEAR MARKET" : winner === "bull" ? "BULL MARKET" : "MARKET IN BALANCE"}</div><div className="battle-subtitle">{winner === "bear" ? "BEAR DOMINATING" : winner === "bull" ? "BULL DOMINATING" : "WAITING FOR CONFIRMATION"}</div></div>
        <div className="battle-score"><span>AI SCORE</span><strong>{Math.round(numericScore)}</strong><small>{winner.toUpperCase()}</small></div>
      </div>
      <div className={`battle-canvas ${dragging ? "is-dragging" : ""}`} ref={hostRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} aria-label="Interactive 3D bull and bear market battle">
        <div className="battle-glow battle-glow-left" /><div className="battle-glow battle-glow-right" />
        <div className="battle-status">{winner === "bull" ? "BULL ATTACKING • BULL WINS" : winner === "bear" ? "BEAR ATTACKING • BEAR WINS" : "MARKET WAITING"}</div>
        <div className="battle-instruction"><Rotate3D size={14} /> DRAG TO ROTATE 3D</div>
        <div className="battle-win"><Target size={13} /> {winner === "bull" ? "BULL WIN" : winner === "bear" ? "BEAR WIN" : "NEUTRAL"}</div>
      </div>
      <div className="battle-footer-3d"><span><i /> LIVE REGIME ENGINE</span><span>30s market refresh</span><span>Interactive 3D model</span></div>
    </div>
  )
}
