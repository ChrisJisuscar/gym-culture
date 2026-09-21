import * as THREE from '/static/vendor/three/three.module.min.js';
import { garmentSurfaceHit } from './raycast-manager.js';

const PRINT_ZONE = Object.freeze({ torsoHeightRatio: .52, duplicateOffsetRatio: .025 });

export function printZone(meshes) {
  const bounds = new THREE.Box3();
  // Hood alternatives do not belong to the torso's alignment area.
  const body = meshes.filter(mesh => mesh.visible && !/^Hood_/.test(mesh.name));
  for (const mesh of body.length ? body : meshes.filter(mesh => mesh.visible)) bounds.union(new THREE.Box3().setFromObject(mesh));
  const size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
  center.y = bounds.min.y + size.y * PRINT_ZONE.torsoHeightRatio;
  return { center, size, bounds };
}

function projectToSurface(meshes, zone, design, x, y) {
  const side = design.normal.z < 0 ? -1 : 1;
  const ray = new THREE.Raycaster(new THREE.Vector3(x, y, side > 0 ? zone.bounds.max.z + zone.size.y : zone.bounds.min.z - zone.size.y), new THREE.Vector3(0, 0, -side));
  const hit = ray.intersectObjects(meshes.filter(mesh => mesh.visible))[0];
  return garmentSurfaceHit(hit, ray.ray.direction);
}

export function transformSelection(manager, meshes, action) {
  const design = manager.selected();
  if (!design) return;
  if (action === 'flipX' || action === 'flipY') { manager.updateSelected({ [action]: !design[action] }); return; }
  const zone = printZone(meshes);
  let x = design.position.x, y = design.position.y;
  if (action === 'duplicate') {
    const offset = zone.size.y * PRINT_ZONE.duplicateOffsetRatio;
    const hit = projectToSurface(meshes, zone, design, x + offset, y) || projectToSurface(meshes, zone, design, x - offset, y);
    if (!hit) throw new Error('No hay espacio para duplicar en esta zona. Mové el diseño hacia el torso.');
    return manager.duplicateSelected(hit);
  }
  if (action === 'centerX' || action === 'center') x = zone.center.x;
  if (action === 'centerY' || action === 'center') y = zone.center.y;
  const hit = projectToSurface(meshes, zone, design, x, y);
  if (!hit) throw new Error('No se pudo alinear sobre esta superficie. Probá en el torso.');
  manager.moveSelected(hit);
}
