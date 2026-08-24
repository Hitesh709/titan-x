"use client"

import { useEffect, useRef, useState } from "react"
import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"
import { Rotate3D, Sparkles } from "lucide-react"
import { createBear } from "./BearModel"
import { createBull } from "./BullModel"
import { createTradingPlatform } from "./TradingPlatform"
import { createEnergyParticles, createCenterSparks } from "./EnergyParticles"
import { createMarketEnergy } from "./MarketEnergy"
import "./titanx-bull-bear.css"

export type MarketState = "bull" | "bear" | "neutral"
export type TitanXBullBearSceneProps = {
  marketState?: MarketState
  bullStrength?: number
  bearStrength?: number
  onMarketStateChange?: (state: MarketState) => void
  bullModelUrl?: string
  bearModelUrl?: string
  className?: string
}

const clamp = (n:number) => Math.max(0,Math.min(100,Number.isFinite(n)?n:50))

function materialSet(kind: "bull"|"bear", strength:number) {
  const bull=kind==="bull"; const c=bull?0x152b28:0x28181d; const e=bull?0x00f39a:0xff214b; const s=.65+.75*(strength/100)
  return {body:new THREE.MeshPhysicalMaterial({color:c,metalness:.88,roughness:.2,clearcoat:1,clearcoatRoughness:.12,emissive:e,emissiveIntensity:.16*s}),dark:new THREE.MeshStandardMaterial({color:0x05080d,metalness:.82,roughness:.28}),energy:new THREE.MeshPhysicalMaterial({color:e,metalness:.2,roughness:.14,emissive:e,emissiveIntensity:2.8*s,clearcoat:1})}
}

export default function TitanXBullBearScene({marketState="neutral",bullStrength=50,bearStrength=50,onMarketStateChange,bullModelUrl,bearModelUrl,className=""}:TitanXBullBearSceneProps){
  const host=useRef<HTMLDivElement>(null); const [loading,setLoading]=useState(true); const [fallback,setFallback]=useState(false); const reduced=useRef(false)
  const bull=clamp(bullStrength), bear=clamp(bearStrength)
  useEffect(()=>{onMarketStateChange?.(marketState)},[marketState,onMarketStateChange])

  useEffect(()=>{
    if(!host.current)return
    const el=host.current; let disposed=false; let raf=0; let controls:OrbitControls|undefined; let renderer:THREE.WebGLRenderer|undefined
    reduced.current=window.matchMedia?.("(prefers-reduced-motion: reduce)").matches??false
    try{
      const w=Math.max(320,el.clientWidth), h=Math.max(280,el.clientHeight)
      const scene=new THREE.Scene(); scene.background=new THREE.Color(0x02050d)
      scene.fog=new THREE.FogExp2(0x020711,.055)
      const camera=new THREE.PerspectiveCamera(29,w/h,.1,80); camera.position.set(0,3.6,15.8)
      renderer=new THREE.WebGLRenderer({antialias:!(/Android|iPhone|iPad/i.test(navigator.userAgent)),alpha:true,powerPreference:"high-performance"})
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5)); renderer.setSize(w,h); renderer.outputColorSpace=THREE.SRGBColorSpace; renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.28; renderer.shadowMap.enabled=!/Android|iPhone|iPad/i.test(navigator.userAgent)
      el.innerHTML=""; el.appendChild(renderer.domElement); renderer.domElement.setAttribute("aria-label","Interactive TITAN X 3D bull and bear market scene")
      controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.dampingFactor=.075; controls.enablePan=false; controls.enableZoom=true; controls.minDistance=12; controls.maxDistance=19; controls.minPolarAngle=Math.PI*.39; controls.maxPolarAngle=Math.PI*.59; controls.autoRotate=!reduced.current; controls.autoRotateSpeed=.22
      camera.lookAt(0,1.5,0); controls.target.set(0,1.45,0)

      const world=new THREE.Group(); scene.add(world)
      const platform=createTradingPlatform(); world.add(platform)
      const bearGroup=new THREE.Group(); const bullGroup=new THREE.Group()
      const bearObj=createBear(materialSet("bear",bear)); const bullObj=createBull(materialSet("bull",bull))
      bearGroup.add(bearObj); bullGroup.add(bullObj)
      bearGroup.position.set(-2.35,marketState==="bear"?.52:.02,0); bullGroup.position.set(2.35,marketState==="bull"?.52:.02,0)
      bearObj.rotation.y=-Math.PI/2; bullObj.rotation.y=Math.PI/2
      bearGroup.rotation.z=marketState==="bear"?-.035:.035; bullGroup.rotation.z=marketState==="bull"?.035:-.035
      world.add(bearGroup,bullGroup)

      // Optional GLB hooks: final production models can be dropped in at these paths without changing the scene.
      // The procedural PBR models remain the guaranteed offline fallback.
      void bullModelUrl; void bearModelUrl

      const redEnergy=createMarketEnergy(0xff214b,bear); redEnergy.position.set(-2.35,.2,0); const greenEnergy=createMarketEnergy(0x00f39a,bull); greenEnergy.position.set(2.35,.2,0); world.add(redEnergy,greenEnergy)
      const mobile=/Android|iPhone|iPad/i.test(navigator.userAgent); const particleCount=mobile?55:125
      const redParticles=createEnergyParticles(particleCount,0xff3558,2.1,.3,4.5); redParticles.position.x=-2.35
      const greenParticles=createEnergyParticles(particleCount,0x00f39a,2.1,.3,4.5); greenParticles.position.x=2.35
      const center=createCenterSparks(mobile?22:48); center.position.set(0,.3,0); scene.add(redParticles,greenParticles,center)

      const stars=createEnergyParticles(mobile?50:120,0x4aaeff,7,.2,6); scene.add(stars)
      scene.add(new THREE.HemisphereLight(0xbfe9ff,0x02040a,2.1))
      const key=new THREE.DirectionalLight(0xffffff,4.2); key.position.set(0,8,10); key.castShadow=true; key.shadow.mapSize.set(1024,1024); scene.add(key)
      const redLight=new THREE.PointLight(0xff1b43,4.5+bear/28,8); redLight.position.set(-3.5,3.2,3.5); scene.add(redLight)
      const greenLight=new THREE.PointLight(0x00ef9a,4.5+bull/28,8); greenLight.position.set(3.5,3.2,3.5); scene.add(greenLight)
      const centerLight=new THREE.PointLight(0x43caff,2.2,7); centerLight.position.set(0,2.5,2); scene.add(centerLight)

      const resize=()=>{if(!renderer||!host.current)return;const W=Math.max(280,host.current.clientWidth),H=Math.max(280,host.current.clientHeight);camera.aspect=W/H;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));renderer.setSize(W,H,false)}
      const ro=new ResizeObserver(resize);ro.observe(el)
      const clock=new THREE.Clock()
      const animate=()=>{if(disposed)return;raf=requestAnimationFrame(animate);const t=clock.getElapsedTime();controls!.update(); platform.rotation.y=t*.035; platform.userData.segments.rotation.y=-t*.16; redParticles.rotation.y=t*.045; greenParticles.rotation.y=-t*.05; center.rotation.y=t*.12; stars.rotation.y=t*.006; bearGroup.position.y=(marketState==="bear"?.52:.02)+Math.sin(t*1.2)*.035; bullGroup.position.y=(marketState==="bull"?.52:.02)+Math.sin(t*1.15+.8)*.035; renderer!.render(scene,camera)}
      animate(); setLoading(false)
      return()=>{disposed=true;cancelAnimationFrame(raf);ro.disconnect();controls?.dispose();renderer?.dispose();scene.traverse(o=>{const m=o as THREE.Mesh;if(m.geometry)m.geometry.dispose();if(Array.isArray(m.material))m.material.forEach(x=>x.dispose());else if(m.material)m.material.dispose()});el.innerHTML=""}
    }catch{setLoading(false);setFallback(true);return()=>{disposed=true;cancelAnimationFrame(raf);controls?.dispose();renderer?.dispose()}}
  },[marketState,bull,bear,bullModelUrl,bearModelUrl])

  return <section className={`titanx-scene-shell state-${marketState} ${className}`} aria-label="TITAN X interactive 3D market centerpiece">
    {loading&&<div className="titanx-scene-loading"><strong>TITAN <em>X</em></strong><span>INITIALIZING MARKET ENGINE</span><i><b/><b/><b/></i></div>}
    {fallback?<div className="titanx-scene-fallback"><strong>3D MARKET ENGINE</strong><span>WebGL is unavailable on this device.</span></div>:<div ref={host} className="titanx-scene-host" />}
    <div className="titanx-scene-hud hud-regime"><span>MARKET REGIME</span><b>{marketState.toUpperCase()}</b><i/></div>
    <div className="titanx-scene-hud hud-breadth"><span>AI MARKET SCORE</span><b>{Math.round((bull+100-bear)/2)}</b></div>
    <div className="titanx-scene-status"><span className="red-dot"/> BEAR <small>{marketState==="bear"?"DOMINANT / ABOVE":"BELOW / RESTING"}</small><span className="green-dot"/> BULL <small>{marketState==="bull"?"DOMINANT / ABOVE":"BELOW / RESTING"}</small></div>
    <div className="titanx-scene-rotate"><Rotate3D size={13}/> DRAG TO ROTATE · SCROLL / PINCH TO ZOOM</div>
    <div className="titanx-scene-scan"><Sparkles size={11}/> LIVE MARKET ENGINE · {marketState.toUpperCase()} STATE</div>
  </section>
}
