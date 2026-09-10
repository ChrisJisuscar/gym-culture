import * as THREE from '/static/vendor/three/three.module.min.js';
import { DecalGeometry } from '/static/vendor/three/geometries/DecalGeometry.js';

// All inputs and generated vertices are world coordinates. Model UVs are unused.
export function projectDecal(mesh, position, orientation, width, height, garmentSize) {
  mesh.updateWorldMatrix(true, false);
  const depth = Math.min(garmentSize.z, Math.max(garmentSize.z * .35, Math.hypot(width, height) * .65));
  const raw = new DecalGeometry(mesh, position, orientation, new THREE.Vector3(width, height, depth));
  const direction = new THREE.Vector3(0, 0, 1).applyEuler(orientation);
  const positions = [], normals = [], uvs = [];
  const p = raw.attributes.position, n = raw.attributes.normal, uv = raw.attributes.uv;
  const normal = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 3) {
    normal.set(0, 0, 0);
    for (let j = 0; j < 3; j++) normal.add(new THREE.Vector3().fromBufferAttribute(n, i + j));
    // Exclude inner/opposite faces and grazing surfaces which stretch the print.
    if (normal.normalize().dot(direction) <= .15) continue;
    for (let j = 0; j < 3; j++) {
      const k = i + j;
      positions.push(p.getX(k), p.getY(k), p.getZ(k));
      normals.push(n.getX(k), n.getY(k), n.getZ(k));
      uvs.push(uv.getX(k), uv.getY(k));
    }
  }
  raw.dispose();
  const result = new THREE.BufferGeometry();
  result.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  result.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  result.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  result.computeBoundingBox();
  result.computeBoundingSphere();
  return result;
}
