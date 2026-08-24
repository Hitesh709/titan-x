"use client"

import Script from "next/script"
import { useEffect, useRef, useState } from "react"
import type { PointerEvent } from "react"
import { Rotate3D, Sparkles, Target, TrendingUp } from "lucide-react"
import { usePublicMarket } from "./MarketTicker"

declare global { interface Window { THREE?: any } }

type Winner = "bull" | "bear" | "neutral"

function buildBeast(THREE: any, kind: "bull" | "bear") {
  const group = new THREE.Group()
  const isBull = kind === "bull"
  const color = isBull ? 0x36e6a0 : 0xff315c
  const dark = isBull ? 0x061914 : 0x21060d
  const material = new THREE.MeshStandardMaterial({ color, metalness: 0.78, roughness: 0.25, flatShading: true, emissive: color, emissiveIntensity: 0.08 })
  const darkMat = new THREE.MeshStandardMaterial({ color: dark, metalness: 0.86, roughness: 0.2, flatShading: true })
  const hornMat = new THREE.MeshStandardMaterial({ color: 0xdbe7ee, metalness: 0.9, roughness: 0.16, flatShading: true })
  const eyeMat = new THREE.MeshBasicMaterial({ color: isBull ? 0x5effc2 : 0xff7890 })
  const add = (geometry: any, mat: any, position: [number, number, number], scale?: [number, number, number]) => {
    const m = new THREE.Mesh(geometry, mat)
    m.position.set(...position)
    if (scale) m.scale.set(...scale)
    m.castShadow = true
    m.receiveShadow = true
    group.add(m)
    return m
  }

  add(new THREE.IcosahedronGeometry(1, 2), material, [0, 0.9, 0], [1.65, 1.0, 0.78])
  add(new THREE.IcosahedronGeometry(0.72, 2), material, [isBull ? 1.12 : -1.12, 1.28, 0], [0.92, 0.82, 0.72])
  add(new THREE.IcosahedronGeometry(0.42, 1), darkMat, [isBull ? 1.65 : -1.65, 1.1, 0], [0.72, 0.46, 0.55])
  const legGeo = new THREE.CylinderGeometry(0.18, 0.23, 1.15, 8)
  const hoofGeo = new THREE.BoxGeometry(0.42, 0.2, 0.48)
  ;[-0.9, 0.85].forEach(x => [-0.42, 0.42].forEach(z => { add(legGeo, material, [x, 0.05, z]); add(hoofGeo, darkMat, [x + (isBull ? 0.06 : -0.06), -0.55, z]) }))

  if (isBull) {
    const hornGeo = new THREE.ConeGeometry(0.16, 0.9, 12)
    const h1 = add(hornGeo, hornMat, [1.0, 1.94, 0.32]); h1.rotation.z = -0.82
    const h2 = add(hornGeo, hornMat, [1.0, 1.94, -0.32]); h2.rotation.z = -0.82
    add(new THREE.SphereGeometry(0.13, 10, 8), eyeMat, [1.42, 1.5, 0.38])
    add(new THREE.SphereGeometry(0.13, 10, 8), eyeMat, [1.42, 1.5, -0.38])
    const tail = add(new THREE.ConeGeometry(0.1, 0.9, 8), material, [-1.62, 1.02, 0]); tail.rotation.z = 1.05
  } else {
    add(new THREE.SphereGeometry(0.3, 12, 8), material, [-1.35, 1.88, 0.48])
    add(new THREE.SphereGeometry(0.3, 12, 8), material, [-1.35, 1.88, -0.48])
    add(new THREE.SphereGeometry(0.1, 10, 8), eyeMat, [-1.58, 1.5, 0.38])
    add(new THREE.SphereGeometry(0.1, 10, 8), eyeMat, [-1.58, 1.5, -0.38])
    const armGeo = new THREE.CylinderGeometry(0.23, 0.3, 1.25, 8)
    ;[-0.45, 0.45].forEach(z => { const arm = add(armGeo, material, [-0.15, 0.55, z]); arm.rotation.z = z > 0 ? -0.5 : 0.5 })
  }
  group.userData.homeX = isBull ? -1.55 : 1.55
  group.userData.attackX = isBull ? 0.65 : -0.65
  group.position.x = group.userData.homeX
  group.rotation.y = isBull ? 0.12 : -0.12
  return group
}

const movers = [["RELIANCE", "+2.34%", "2,854.10"], ["TCS", "+1.87%", "4,218.75"], ["HDFCBANK", "+1.45%", "1,678.20"], ["INFY", "+1.23%", "1,432.60"], ["SBIN", "-0.76%", "812.40"]]

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
    const THREE = window.THREE, host = hostRef.current
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, host.clientWidth / Math.max(host.clientHeight, 1), 0.1, 100)
    camera.position.set(0, 1.7, 9.4)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8)); renderer.setSize(host.clientWidth, host.clientHeight); renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.shadowMap.enabled = true
    host.innerHTML = ""; host.appendChild(renderer.domElement)
    scene.add(new THREE.HemisphereLight(0xb7e8ff, 0x02040a, 1.55))
    const key = new THREE.DirectionalLight(0xffffff, 3.3); key.position.set(3, 7, 6); key.castShadow = true; scene.add(key)
    const blue = new THREE.PointLight(0x159dff, 10, 10); blue.position.set(-3, 1.5, 3); scene.add(blue)
    const red = new THREE.PointLight(0xff164e, 8, 9); red.position.set(3, 1.5, 2); scene.add(red)
    const floor = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.2, 0.14, 96), new THREE.MeshStandardMaterial({ color: 0x020713, metalness: 0.88, roughness: 0.18 })); floor.position.y = -0.7; floor.receiveShadow = true; scene.add(floor)
    const ring = new THREE.Mesh(new THREE.TorusGeometry(3.5, 0.025, 8, 128), new THREE.MeshBasicMaterial({ color: 0x2bd7ff, transparent: true, opacity: 0.72 })); ring.rotation.x = Math.PI / 2; ring.position.y = -0.6; scene.add(ring)
    const battle = new THREE.Group(), bull = buildBeast(THREE, "bull"), bear = buildBeast(THREE, "bear"); battle.add(bull, bear); scene.add(battle)
    const particleGeometry = new THREE.BufferGeometry(), positions = new Float32Array(240 * 3)
    for (let i = 0; i < positions.length; i += 3) { positions[i] = (Math.random() - 0.5) * 8; positions[i+1] = Math.random() * 4 - 0.7; positions[i+2] = (Math.random() - 0.5) * 3 }
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3)); scene.add(new THREE.Points(particleGeometry, new THREE.PointsMaterial({ color: 0x4fc3ff, size: 0.035, transparent: true, opacity: 0.62 })))
    const resize = () => { if (!host.clientWidth) return; camera.aspect = host.clientWidth / Math.max(host.clientHeight, 1); camera.updateProjectionMatrix(); renderer.setSize(host.clientWidth, host.clientHeight) }
    window.addEventListener("resize", resize)
    let previous = performance.now()
    const animate = (now: number) => { const dt = Math.min((now - previous) / 1000, 0.05); previous = now; if (!dragRef.current.active) battle.rotation.y += dt * 0.07; bull.position.y = Math.sin(now * 0.0018) * 0.035; bear.position.y = Math.sin(now * 0.0018 + 1.4) * 0.035; renderer.render(scene, camera); frameRef.current = requestAnimationFrame(animate) }
    frameRef.current = requestAnimationFrame(animate); sceneRef.current = { scene, camera, renderer, battle, bull, bear }
    return () => { if (frameRef.current) cancelAnimationFrame(frameRef.current); window.removeEventListener("resize", resize); renderer.dispose(); scene.traverse((obj: any) => { obj.geometry?.dispose?.(); const mats = Array.isArray(obj.material) ? obj.material : [obj.material]; mats.forEach((m: any) => m?.dispose?.()) }); sceneRef.current = null }
  }, [threeReady])

  useEffect(() => {
    const s = sceneRef.current; if (!s) return
    const win = winner === "bull" ? s.bull : winner === "bear" ? s.bear : null
    const lose = winner === "bull" ? s.bear : winner === "bear" ? s.bull : null
    const start = performance.now(), duration = 1050
    const winFrom = win?.position.x ?? 0, winTo = win?.userData.attackX ?? winFrom, loseFrom = lose?.position.x ?? 0, loseTo = lose?.userData.homeX ?? loseFrom
    const tick = (now: number) => { const t = Math.min((now-start)/duration,1); const e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2; if(win) win.position.x=winFrom+(winTo-winFrom)*e; if(lose) lose.position.x=loseFrom+(loseTo-loseFrom)*e; if(t<1) requestAnimationFrame(tick) }
    requestAnimationFrame(tick)
  }, [winner])

  const down = (e: PointerEvent<HTMLDivElement>) => { dragRef.current={active:true,x:e.clientX,rotation:sceneRef.current?.battle.rotation.y??0}; setDragging(true); e.currentTarget.setPointerCapture(e.pointerId) }
  const move = (e: PointerEvent<HTMLDivElement>) => { if(!dragRef.current.active||!sceneRef.current) return; sceneRef.current.battle.rotation.y=dragRef.current.rotation+(e.clientX-dragRef.current.x)*0.008 }
  const up = (e: PointerEvent<HTMLDivElement>) => { dragRef.current.active=false; setDragging(false); e.currentTarget.releasePointerCapture?.(e.pointerId) }

  return <div className={`battle-shell-3d battle-${winner}`}>
    <Script src="https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.min.js" strategy="afterInteractive" onLoad={()=>setThreeReady(true)} />
    <div className="battle-main-3d">
      <div className="battle-header-3d"><div><div className="battle-kicker"><Sparkles size={12}/> AI MARKET SENTIMENT</div><div className="battle-title">{winner==='bear'?'BEAR MARKET':winner==='bull'?'BULL MARKET':'MARKET IN BALANCE'}</div><div className="battle-subtitle">{winner==='bear'?'BEAR DOMINATING':winner==='bull'?'BULL DOMINATING':'WAITING FOR CONFIRMATION'}</div></div><div className="battle-score"><span>AI SCORE</span><strong>{Math.round(numericScore)}</strong><small>{winner.toUpperCase()}</small></div></div>
      <div className={`battle-canvas ${dragging?'is-dragging':''}`} ref={hostRef} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}><div className="battle-glow battle-glow-left"/><div className="battle-glow battle-glow-right"/><div className="battle-status">{winner==='bull'?'BULL ATTACKING • BULL WINS':winner==='bear'?'BEAR ATTACKING • BEAR WINS':'MARKET WAITING'}</div><div className="battle-instruction"><Rotate3D size={13}/> DRAG TO ROTATE 3D</div><div className="battle-win"><Target size={12}/> {winner==='bull'?'BULL WIN':winner==='bear'?'BEAR WIN':'NEUTRAL'}</div></div>
      <div className="battle-footer-3d"><span><i/> LIVE REGIME ENGINE</span><span>30s market refresh</span><span>Interactive 3D model</span></div>
    </div>
    <aside className="battle-insights">
      <div className="insight-panel"><div className="insight-title">AI MARKET SENTIMENT</div><div className="gauge"><div className="gauge-ring"/><strong>{Math.round(numericScore)}</strong><span className={winner==='bear'?'down':winner==='bull'?'up':'flat'}>{winner==='bear'?'BEARISH':winner==='bull'?'BULLISH':'NEUTRAL'}</span></div>{[['Momentum',winner==='bear'?22:78],['Volume',winner==='bear'?28:72],['News',winner==='bear'?33:81],['Technical',winner==='bear'?29:76],['Overall',Math.round(numericScore)]].map(([n,v])=><div className="meter" key={n}><span>{n}</span><i><b style={{width:`${v}%`}}/></i><em>{v}%</em></div>)}</div>
      <div className="insight-panel movers"><div className="insight-title">TOP MOVERS <small>NIFTY 50⌄</small></div>{movers.map(([name,change,price],i)=><div className="mover" key={name}><span>{i+1}. <b>{name}</b></span><span>{price}</span><em className={change.startsWith('+')?'up':'down'}>{change}</em></div>)}</div>
    </aside>
    <style jsx global>{` .battle-shell-3d{display:grid;grid-template-columns:minmax(0,1fr) 235px;gap:12px;border:1px solid rgba(60,150,255,.22);border-radius:22px;overflow:hidden;background:linear-gradient(145deg,rgba(2,8,20,.98),rgba(2,4,12,.98));box-shadow:0 30px 90px rgba(0,0,0,.52),inset 0 1px rgba(255,255,255,.04);min-width:0}.battle-main-3d{position:relative;min-width:0}.battle-header-3d{position:absolute;z-index:5;top:16px;left:18px;right:18px;display:flex;justify-content:space-between;pointer-events:none}.battle-kicker{display:flex;gap:6px;align-items:center;color:#60a5fa;font:800 9px/1 'Inter';letter-spacing:.15em}.battle-title{margin-top:6px;font:900 17px/1 'Inter';letter-spacing:.08em}.battle-subtitle{margin-top:4px;color:#64748b;font:700 8px/1 'JetBrains Mono';letter-spacing:.13em}.battle-score{min-width:70px;padding:7px 9px;border:1px solid rgba(56,189,248,.18);border-radius:11px;background:rgba(2,6,23,.72);text-align:right}.battle-score span,.battle-score small{display:block;color:#64748b;font:700 7px/1.2 'JetBrains Mono';letter-spacing:.12em}.battle-score strong{display:block;color:#fff;font:900 22px/1.05 'JetBrains Mono';margin:3px 0}.battle-score small{color:#38bdf8}.battle-canvas{height:470px;position:relative;cursor:grab;touch-action:none;overflow:hidden}.battle-canvas.is-dragging{cursor:grabbing}.battle-canvas canvas{width:100%!important;height:100%!important;display:block}.battle-glow{position:absolute;width:180px;height:180px;border-radius:50%;filter:blur(55px);opacity:.16;pointer-events:none}.battle-glow-left{left:8%;bottom:8%;background:#00d9ff}.battle-glow-right{right:8%;bottom:8%;background:#ff1e52}.battle-status{position:absolute;left:50%;top:21%;transform:translateX(-50%);white-space:nowrap;color:#e2e8f0;font:800 9px 'JetBrains Mono';letter-spacing:.12em;text-shadow:0 0 18px rgba(56,189,248,.45);pointer-events:none}.battle-instruction{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);display:flex;gap:6px;align-items:center;color:#94a3b8;font:700 8px 'JetBrains Mono';letter-spacing:.08em;white-space:nowrap;pointer-events:none}.battle-win{position:absolute;right:14px;bottom:13px;padding:6px 9px;border:1px solid rgba(56,189,248,.22);border-radius:999px;background:rgba(2,6,23,.72);color:#fff;font:800 8px 'JetBrains Mono';pointer-events:none}.battle-bear .battle-win{border-color:rgba(244,63,94,.35)}.battle-footer-3d{height:34px;border-top:1px solid rgba(56,189,248,.1);display:flex;align-items:center;justify-content:space-between;padding:0 14px;color:#64748b;font:700 7px 'JetBrains Mono';letter-spacing:.05em}.battle-footer-3d span:first-child{color:#5ee7ff}.battle-footer-3d i{display:inline-block;width:5px;height:5px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;margin-right:5px}.battle-insights{padding:10px 10px 10px 0;display:flex;flex-direction:column;gap:10px;min-width:0}.insight-panel{border:1px solid rgba(59,130,246,.16);border-radius:14px;background:linear-gradient(145deg,rgba(7,16,32,.92),rgba(3,8,18,.92));padding:12px;box-shadow:inset 0 1px rgba(255,255,255,.03)}.insight-title{font:800 8px 'JetBrains Mono';letter-spacing:.1em;color:#dbeafe;margin-bottom:10px}.insight-title small{float:right;color:#64748b;font-weight:600}.gauge{height:90px;position:relative;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;overflow:hidden}.gauge-ring{position:absolute;top:6px;width:100px;height:100px;border-radius:50%;border:9px solid transparent;border-top-color:#ef4444;border-right-color:#f59e0b;border-bottom-color:#34d399;transform:rotate(-35deg);opacity:.95}.gauge strong{position:relative;font:900 27px 'JetBrains Mono';z-index:1}.gauge span{position:relative;font:800 8px 'JetBrains Mono';z-index:1;margin-bottom:7px}.up{color:#34d399}.down{color:#fb7185}.flat{color:#fbbf24}.meter{display:grid;grid-template-columns:48px 1fr 28px;gap:6px;align-items:center;margin-top:7px}.meter span,.meter em{font:600 7px 'Inter';color:#94a3b8;font-style:normal}.meter em{text-align:right;color:#cbd5e1}.meter i{height:4px;background:#172033;border-radius:99px;overflow:hidden}.meter i b{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#ef4444,#f97316,#34d399)}.mover{display:grid;grid-template-columns:1.4fr .8fr .55fr;gap:4px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font:600 8px 'JetBrains Mono';color:#94a3b8}.mover:last-child{border-bottom:0}.mover b{color:#e2e8f0}.mover span:nth-child(2){text-align:right}.mover em{text-align:right;font-style:normal}.battle-bear{border-color:rgba(244,63,94,.3)}@media(max-width:1100px){.battle-shell-3d{grid-template-columns:1fr}.battle-insights{display:grid;grid-template-columns:1fr 1fr;padding:0 10px 10px}.battle-canvas{height:430px}}@media(max-width:700px){.battle-shell-3d{border-radius:18px}.battle-canvas{height:340px}.battle-insights{grid-template-columns:1fr}.battle-footer-3d span:nth-child(2),.battle-footer-3d span:nth-child(3){display:none}.battle-status{top:25%;font-size:7px}.battle-title{font-size:14px}.battle-score{min-width:62px}.battle-score strong{font-size:18px}}`}</style>
  </div>
}
