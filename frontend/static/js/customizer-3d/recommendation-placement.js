import * as THREE from '/static/vendor/three/three.module.min.js';
import { garmentSurfaceHit } from './raycast-manager.js';

// Position is relative to the centered garment dimensions; z chooses front/back.
// Raycasting against geometry makes the same preset work at every camera angle.
export function recommendationHit(meshes, size, position = {}) {
  const x = Number.isFinite(position?.x) ? position.x : 0;
  const y = Number.isFinite(position?.y) ? position.y : .12;
  const side = position?.z < 0 ? -1 : 1;
  const ray = new THREE.Raycaster(
    new THREE.Vector3(x * size.x, y * size.y, side * (size.z + size.y)),
    new THREE.Vector3(0, 0, -side),
  );
  meshes.forEach((mesh) => mesh.updateWorldMatrix(true, false));
  const hit = ray.intersectObjects(meshes.filter((mesh) => mesh.visible), false)[0];
  if (!hit?.face) throw new Error('La posición elegida queda fuera de la prenda. Revisá la recomendación.');
  return garmentSurfaceHit(hit, ray.ray.direction);
}
