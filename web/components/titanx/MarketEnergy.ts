import * as THREE from "three"

export function createMarketEnergy(color:number, strength:number){
  const g=new THREE.Group(); const s=Math.max(.15,Math.min(1,strength/100))
  const mat=new THREE.MeshBasicMaterial({color,transparent:true,opacity:.08+.16*s,blending:THREE.AdditiveBlending,side:THREE.DoubleSide,depthWrite:false})
  for(let i=0;i<3;i++){const ring=new THREE.Mesh(new THREE.TorusGeometry(1.45+i*.22,.025+i*.012,8,96),mat.clone());ring.rotation.x=Math.PI/2;ring.position.y=1.2+i*.35;ring.scale.set(1,.7,1);g.add(ring)}
  const light=new THREE.PointLight(color,2.5*s,5);light.position.y=1.5;g.add(light)
  return g
}
