import * as THREE from '/static/vendor/three/three.module.min.js';

export function garmentSurfaceHit(hit, rayDirection) {
  if (!hit?.face) return null;
  const { object: mesh, face } = hit, geometry = mesh.geometry;
  const point = mesh.worldToLocal(hit.point.clone());
  const vertices = [face.a, face.b, face.c].map(index => new THREE.Vector3().fromBufferAttribute(geometry.attributes.position, index));
  const barycentric = THREE.Triangle.getBarycoord(point, ...vertices, new THREE.Vector3());
  const normal = face.normal.clone();
  // Interpolated normals avoid an orientation jump at each triangle boundary.
  if (geometry.attributes.normal && barycentric) {
    normal.set(0, 0, 0);
    [face.a, face.b, face.c].forEach((index, offset) => normal.addScaledVector(new THREE.Vector3().fromBufferAttribute(geometry.attributes.normal, index), barycentric.getComponent(offset)));
  }
  normal.applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld));
  if (rayDirection && normal.dot(rayDirection) > 0) normal.negate();
  return { mesh, point: hit.point.clone(), normal };
}

export class RaycastManager {
  constructor(camera, canvas) {
    this.camera = camera;
    this.canvas = canvas;
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
  }

  cast(event, objects, recursive = false) {
    objects.forEach((object) => object.updateWorldMatrix(true, false));
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(objects.filter((object) => object.visible), recursive);
  }

  garmentHit(event, meshes) {
    return garmentSurfaceHit(this.cast(event, meshes)[0], this.raycaster.ray.direction);
  }
}
