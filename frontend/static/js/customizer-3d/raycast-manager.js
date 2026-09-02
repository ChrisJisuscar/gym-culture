import * as THREE from '/static/vendor/three/three.module.min.js';

export class RaycastManager {
  constructor(camera, canvas) {
    this.camera = camera;
    this.canvas = canvas;
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
  }

  cast(event, objects, recursive = false) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(objects, recursive);
  }

  garmentHit(event, meshes) {
    const hit = this.cast(event, meshes)[0];
    if (!hit?.face) return null;
    const normal = hit.face.normal.clone().transformDirection(hit.object.matrixWorld).normalize();
    return { mesh: hit.object, point: hit.point.clone(), normal };
  }
}
