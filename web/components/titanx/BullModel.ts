import * as THREE from "three"
import type { BeastMaterials } from "./BearModel"

function mesh(group: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material, p: [number, number, number], s: [number, number, number] = [1, 1, 1]) {
  const m = new THREE.Mesh(geometry, material)
  m.position.set(...p); m.scale.set(...s); m.castShadow = true; m.receiveShadow = true; group.add(m); return m
}

/** Procedural fallback: a genuine WebGL 3D armored bull, ready for GLB replacement. */
export function createBull(materials: BeastMaterials) {
  const g = new THREE.Group(); const { body, dark, energy } = materials
  mesh(g,new THREE.SphereGeometry(1.25,48,32),body,[0,1.5,0],[1.62,1.08,1.88])
  mesh(g,new THREE.SphereGeometry(.98,42,28),body,[0,2.5,-.95],[1.08,1.02,1.16])
  mesh(g,new THREE.SphereGeometry(.7,36,24),dark,[0,2.28,-1.7],[1.18,.7,.82])
  const muzzle=mesh(g,new THREE.SphereGeometry(.48,28,18),dark,[0,2.38,-1.99],[1.18,.72,.58])
  muzzle.rotation.x=.05
  const horn = new THREE.ConeGeometry(.19,1.5,24)
  const h1=mesh(g,horn,energy,[-.62,3.08,-.82],[1,1,1]); const h2=mesh(g,horn,energy,[.62,3.08,-.82],[1,1,1]); h1.rotation.z=-.62; h2.rotation.z=.62; h1.rotation.x=-.18; h2.rotation.x=-.18
  const shoulder=new THREE.SphereGeometry(.72,34,22)
  mesh(g,shoulder,body,[-1.06,1.62,-.35],[.82,1.08,.98]); mesh(g,shoulder,body,[1.06,1.62,-.35],[.82,1.08,.98])
  const leg=new THREE.CylinderGeometry(.23,.34,1.5,20)
  ;[[-1.08,.55,-.68],[1.08,.55,-.68],[-.86,.52,.68],[.86,.52,.68]].forEach(p=>mesh(g,leg,body,p as [number,number,number]))
  const hoof=new THREE.SphereGeometry(.38,24,16)
  ;[[-1.1,-.18,-.84],[1.1,-.18,-.84],[-.86,-.2,.78],[.86,-.2,.78]].forEach(p=>mesh(g,hoof,dark,p as [number,number,number],[1.3,.55,1.55]))
  const eye=new THREE.SphereGeometry(.105,20,14); mesh(g,eye,energy,[-.34,2.56,-1.88]); mesh(g,eye,energy,[.34,2.56,-1.88])
  const hornBase=new THREE.TorusGeometry(.27,.055,10,32); const hb1=mesh(g,hornBase,energy,[-.5,2.86,-1.05]); const hb2=mesh(g,hornBase,energy,[.5,2.86,-1.05]); hb1.rotation.x=Math.PI/2; hb2.rotation.x=Math.PI/2
  const armor=new THREE.BoxGeometry(.66,.38,.18)
  for(let i=0;i<4;i++) mesh(g,armor,dark,[0,1.35+i*.25,1.38-i*.18],[1.8-i*.1,1,1])
  const shoulderRing=new THREE.TorusGeometry(1.08,.045,10,64,Math.PI*1.25); const r=mesh(g,shoulderRing,energy,[0,1.58,.24],[1.08,1,1.28]); r.rotation.x=Math.PI/2
  const tail=new THREE.CylinderGeometry(.07,.14,1,14); const t=mesh(g,tail,energy,[0,1.55,1.75]); t.rotation.x=-.55
  g.userData.kind="bull"; return g
}
