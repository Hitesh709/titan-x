"use client"

import { useEffect, useRef, useState } from "react"
import * as THREE from "three"
import { Rotate3D, Sparkles, Target, Zap } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

type Winner = "bull" | "bear" | "neutral"

function mat(THREE_: typeof THREE, color: number, metalness = 0.85, roughness = 0.24, emissive = 0) {
  return new THREE_.MeshStandardMaterial({ color, metalness, roughness, emissive, emissiveIntensity: emissive ? 0.28 : 0 })
}

function addPart(group: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material, p: [number, number, number], s?: [number, number, number]) {
  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.set(...p)
  if (s) mesh.scale.set(...s)
  mesh.castShadow = true
  mesh.receiveShadow = true
  group.add(mesh)
  return mesh
}

function createBeast(kind: "bull" | "bear") {
  const bull = kind === "bull"
  const g = new THREE.Group()
  const bodyMat = mat(THREE, bull ? 0x19d69b : 0x9e1838, 0.92, 0.2, bull ? 0x063c2d : 0x3b0714)
  const darkMat = mat(THREE, bull ? 0x061a17 : 0x16050b, 0.96, 0.16)
  const hornMat = mat(THREE, bull ? 0xcff8ef : 0xffa0ad, 0.9, 0.12, bull ? 0x2affcf : 0xff294f)
  const eyeMat = new THREE.MeshBasicMaterial({ color: bull ? 0x73ffd2 : 0xff5b79 })

  addPart(g, new THREE.IcosahedronGeometry(1.35, 2), bodyMat, [0, 1.25, 0], [1.65, 0.98, 0.85])
  addPart(g, new THREE.SphereGeometry(0.92, 20, 14), bodyMat, [bull ? 1.12 : -1.08, 1.62, 0], [1, 0.9, 0.82])
  addPart(g, new THREE.SphereGeometry(0.58, 18, 12), darkMat, [bull ? 1.75 : -1.68, 1.42, 0], [1, 0.75, 0.8])

  const legGeo = new THREE.CapsuleGeometry(0.18, 0.75, 6, 10)
  const hoofGeo = new THREE.BoxGeometry(0.45, 0.18, 0.55)
  for (const x of [-0.92, 0.72]) for (const z of [-0.42, 0.42]) {
    addPart(g, legGeo, bodyMat, [x, 0.18, z])
    addPart(g, hoofGeo, darkMat, [x + (bull ? 0.12 : -0.12), -0.34, z])
  }

  if (bull) {
    const hornGeo = new THREE.ConeGeometry(0.22, 1.12, 18)
    const h1 = addPart(g, hornGeo, hornMat, [1.1, 2.38, 0.42]); h1.rotation.z = -0.88
    const h2 = addPart(g, hornGeo, hornMat, [1.1, 2.38, -0.42]); h2.rotation.z = -0.88
    addPart(g, new THREE.SphereGeometry(0.12, 12, 10), eyeMat, [1.92, 1.72, 0.35])
    addPart(g, new THREE.SphereGeometry(0.12, 12, 10), eyeMat, [1.92, 1.72, -0.35])
    const tail = addPart(g, new THREE.CylinderGeometry(0.07, 0.12, 0.85, 10), bodyMat, [-1.58, 1.45, 0]); tail.rotation.z = 0.9
    const tailTip = addPart(g, new THREE.SphereGeometry(0.17, 10, 8), darkMat, [-1.94, 1.8, 0])
    tailTip.scale.set(1.2, 0.65, 0.7)
  } else {
    const earGeo = new THREE.ConeGeometry(0.28, 0.62, 14)
    const e1 = addPart(g, earGeo, bodyMat, [-1.35, 2.35, 0.48]); e1.rotation.z = -0.25
    const e2 = addPart(g, earGeo, bodyMat, [-1.35, 2.35, -0.48]); e2.rotation.z = -0.25
    addPart(g, new THREE.SphereGeometry(0.12, 12, 10), eyeMat, [-1.93, 1.78, 0.36])
    addPart(g, new THREE.SphereGeometry(0.12, 12, 10), eyeMat, [-1.93, 1.78, -0.36])
    const armGeo = new THREE.CapsuleGeometry(0.2, 0.7, 6, 10)
    for (const z of [-0.5, 0.5]) {
      const arm = addPart(g, armGeo, bodyMat, [-0.8, 0.72, z])
      arm.rotation.z = z > 0 ? -0.72 : 0.72
    }
    addPart(g, new THREE.SphereGeometry(0.33, 14, 10), darkMat, [-2.12, 1.35, 0], [0.8, 0.65, 0.7])
  }

  g.userData.homeX = bull ? -2.0 : 2.0
  g.userData.attackX = bull ? 0.55 : -0.55
  g.userData.kind = kind
  g.position.x = g.userData.homeX
  g.rotation.y = bull ? -0.18 : 0.18
  g.scale.setScalar(1.12)
  return g
}

export default function MarketBattle() {
  const { score, regime } = usePublicMarket()
  const mountRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef<{ scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer; arena: THREE.Group; bull: THREE.Group; bear: THREE.Group } | null>(null)
  const drag = useRef({ active: false, x: 0, rotation: 0 })
  const [dragging, setDragging] = useState(false)
  const numericScore = typeof score === "number" ? score : 50
  const normalized = (regime || "").toLowerCase()
  const winner: Winner = normalized.includes("bear") || numericScore < 45 ? "bear" : normalized.includes("bull") || numericScore > 55 ? "bull" : "neutral"

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
    camera.position.set(0, 2.2, 10.8)
    camera.lookAt(0, 1, 0)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.outputColorSpace = THREE.SRGBColorSpace
    mount.innerHTML = ""
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0x9fdcff, 0x02030a, 1.3))
    const key = new THREE.DirectionalLight(0xffffff, 3.8); key.position.set(3, 8, 7); key.castShadow = true; scene.add(key)
    const cyan = new THREE.PointLight(0x00bfff, 13, 12); cyan.position.set(-4, 2, 4); scene.add(cyan)
    const red = new THREE.PointLight(0xff164e, 12, 12); red.position.set(4, 2, 4); scene.add(red)

    const arena = new THREE.Group()
    const base = new THREE.Mesh(new THREE.CylinderGeometry(4.65, 4.65, 0.22, 96), new THREE.MeshStandardMaterial({ color: 0x020713, metalness: 0.95, roughness: 0.18 }))
    base.position.y = -0.72; base.receiveShadow = true; arena.add(base)
    for (const [r, color, y] of [[4.2, 0x19d9ff, -0.58], [3.25, 0x9b5cff, -0.55], [2.35, 0x19d9ff, -0.52]] as [number, number, number][]) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(r, 0.028, 10, 160), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8 }))
      ring.rotation.x = Math.PI / 2; ring.position.y = y; arena.add(ring)
    }
    const grid = new THREE.GridHelper(13, 26, 0x0a8bd6, 0x08304c)
    grid.position.y = -0.58; (grid.material as THREE.Material).transparent = true; (grid.material as THREE.Material).opacity = 0.32; arena.add(grid)
    scene.add(arena)

    const bull = createBeast("bull"), bear = createBeast("bear")
    arena.add(bull, bear)

    const sparkGeo = new THREE.BufferGeometry()
    const pts = new Float32Array(420 * 3)
    for (let i = 0; i < pts.length; i += 3) { pts[i] = (Math.random() - .5) * 10; pts[i + 1] = Math.random() * 5 - .5; pts[i + 2] = (Math.random() - .5) * 4 }
    sparkGeo.setAttribute("position", new THREE.BufferAttribute(pts, 3))
    scene.add(new THREE.Points(sparkGeo, new THREE.PointsMaterial({ color: 0x36cfff, size: .025, transparent: true, opacity: .72 })))

    const resize = () => { const w = mount.clientWidth, h = mount.clientHeight; if (!w || !h) return; camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h, false) }
    resize(); window.addEventListener("resize", resize)
    let raf = 0, previous = performance.now()
    const loop = (now: number) => { const dt = Math.min((now - previous) / 1000, .05); previous = now; if (!drag.current.active) arena.rotation.y += dt * .035; bull.position.y = Math.sin(now * .0018) * .035; bear.position.y = Math.sin(now * .0018 + 1.2) * .035; renderer.render(scene, camera); raf = requestAnimationFrame(loop) }
    raf = requestAnimationFrame(loop)
    stateRef.current = { scene, camera, renderer, arena, bull, bear }

    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); renderer.dispose(); scene.traverse(o => { o.geometry?.dispose?.(); const m = o.material; if (Array.isArray(m)) m.forEach(x => x.dispose?.()); else m?.dispose?.() }); stateRef.current = null }
  }, [])

  useEffect(() => {
    const s = stateRef.current
    if (!s || winner === "neutral") return
    const win = winner === "bull" ? s.bull : s.bear
    const lose = winner === "bull" ? s.bear : s.bull
    const winFrom = winner === "bull" ? -2 : 2, winTo = winner === "bull" ? .55 : -.55
    const loseFrom = winner === "bull" ? 2 : -2, loseTo = winner === "bull" ? 2.35 : -2.35
    win.position.x = winFrom; lose.position.x = loseFrom
    const start = performance.now(), duration = 1250
    const tick = (now: number) => { const t = Math.min((now - start) / duration, 1); const e = 1 - Math.pow(1 - t, 3); win.position.x = winFrom + (winTo - winFrom) * e; lose.position.x = loseFrom + (loseTo - loseFrom) * e; if (t < 1) requestAnimationFrame(tick) }
    const timer = window.setTimeout(() => requestAnimationFrame(tick), 500)
    return () => window.clearTimeout(timer)
  }, [winner])

  const down = (e: React.PointerEvent<HTMLDivElement>) => { drag.current = { active: true, x: e.clientX, rotation: stateRef.current?.arena.rotation.y || 0 }; setDragging(true); e.currentTarget.setPointerCapture(e.pointerId) }
  const move = (e: React.PointerEvent<HTMLDivElement>) => { if (!drag.current.active || !stateRef.current) return; stateRef.current.arena.rotation.y = drag.current.rotation + (e.clientX - drag.current.x) * .008 }
  const up = (e: React.PointerEvent<HTMLDivElement>) => { drag.current.active = false; setDragging(false); e.currentTarget.releasePointerCapture?.(e.pointerId) }

  const isBull = winner === "bull", isBear = winner === "bear"
  return (
    <div className={`titan-battle ${isBear ? "is-bear" : isBull ? "is-bull" : "is-neutral"}`}>
      <div className="titan-battle-main">
        <div className="titan-battle-head">
          <div><div className="titan-kicker"><Sparkles size={12}/> AI MARKET REGIME</div><div className="titan-battle-title">{isBull ? "BULL MARKET" : isBear ? "BEAR MARKET" : "MARKET BALANCED"}</div><div className="titan-battle-sub">{isBull ? "BULL DOMINATING • BUY PRESSURE" : isBear ? "BEAR DOMINATING • SELL PRESSURE" : "WAITING FOR CONFIRMATION"}</div></div>
          <div className="titan-score"><small>AI SCORE</small><b>{Math.round(numericScore)}</b></div>
        </div>
        <div className={`titan-canvas ${dragging ? "dragging" : ""}`} ref={mountRef} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
          <div className="titan-battle-label left">BULL <span>LONG</span></div><div className="titan-battle-label right">BEAR <span>SHORT</span></div>
          <div className="titan-attack-line"/><div className="titan-impact"><Zap size={18}/></div>
          <div className="titan-winner"><Target size={12}/> {isBull ? "BULL WINS" : isBear ? "BEAR WINS" : "NEUTRAL"}</div>
          <div className="titan-rotate"><Rotate3D size={14}/> DRAG TO ROTATE • 3D</div>
        </div>
        <div className="titan-battle-foot"><span><i/> LIVE REGIME ENGINE</span><span>30 SEC REFRESH</span><span>WEBGL 3D</span></div>
      </div>
      <aside className="titan-insights">
        <div className="titan-panel"><div className="titan-panel-title">AI MARKET SENTIMENT</div><div className="titan-gauge"><div className="titan-gauge-arc"/><strong>{Math.round(numericScore)}</strong><span className={isBear ? "down" : isBull ? "up" : "flat"}>{isBear ? "BEARISH" : isBull ? "BULLISH" : "NEUTRAL"}</span></div>
          {[['Momentum', isBear ? 22 : isBull ? 81 : 50], ['Volume', isBear ? 28 : isBull ? 74 : 50], ['News', isBear ? 33 : isBull ? 79 : 50], ['Technical', isBear ? 29 : isBull ? 76 : 50], ['Overall', Math.round(numericScore)]].map(([n,v]) => <div className="titan-meter" key={n}><span>{n}</span><i><b style={{width:`${v}%`}}/></i><em>{v}%</em></div>)}
        </div>
        <div className="titan-panel"><div className="titan-panel-title">TOP MOVERS <small>NIFTY 50⌄</small></div>{[['RELIANCE','+2.34%','2,854.10'],['TCS','+1.87%','4,218.75'],['HDFCBANK','+1.45%','1,678.20'],['INFY','+1.23%','1,432.60'],['SBIN','-0.76%','812.40']].map(([n,c,p],i)=><div className="titan-mover" key={n}><span>{i+1}. <b>{n}</b></span><small>{p}</small><em className={c.startsWith('+')?'up':'down'}>{c}</em></div>)}</div>
      </aside>
    </div>
  )
}
