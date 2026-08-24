import * as THREE from "three"

export function createTradingPlatform() {
  const g = new THREE.Group()
  const dark = new THREE.MeshPhysicalMaterial({color:0x050b14,metalness:.92,roughness:.2,clearcoat:1,clearcoatRoughness:.12})
  const base = new THREE.Mesh(new THREE.CylinderGeometry(5.55,5.75,.28,128),dark); base.position.y=-.22; base.receiveShadow=true; g.add(base)
  const rings:[number,number,number,number][]=[[5.25,.045,0x1d9dff,.75],[4.72,.065,0xff274d,.9],[3.95,.04,0x18f39a,.8],[2.85,.025,0x4cc9ff,.5]]
  for(const [r,t,c,o] of rings){const m=new THREE.Mesh(new THREE.TorusGeometry(r,t,10,160),new THREE.MeshBasicMaterial({color:c,transparent:true,opacity:o}));m.rotation.x=Math.PI/2;m.position.y=.02;g.add(m)}
  const segments=new THREE.Group()
  for(let i=0;i<24;i++){const a=i/24*Math.PI*2;const m=new THREE.Mesh(new THREE.BoxGeometry(.5,.035,.07),new THREE.MeshBasicMaterial({color:i%2?0x15dfff:0x637cff,transparent:true,opacity:.8}));m.position.set(Math.cos(a)*4.45,.08,Math.sin(a)*4.45);m.rotation.y=-a;segments.add(m)}
  g.add(segments)
  const grid=new THREE.Mesh(new THREE.CircleGeometry(4.7,96),new THREE.MeshBasicMaterial({color:0x06111f,transparent:true,opacity:.75,side:THREE.DoubleSide}));grid.rotation.x=-Math.PI/2;grid.position.y=.035;g.add(grid)
  g.userData.segments=segments; g.userData.platform=true
  return g
}
