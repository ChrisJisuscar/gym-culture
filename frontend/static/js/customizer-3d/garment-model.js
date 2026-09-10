import * as THREE from '/static/vendor/three/three.module.min.js';

export const disposeModel = (model) => {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  model?.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    const sources = Array.isArray(object.material) ? object.material : [object.material];
    sources.filter(Boolean).forEach((material) => materials.add(material));
  });
  materials.forEach((material) => {
    Object.values(material).forEach((value) => { if (value?.isTexture) textures.add(value); });
    material.dispose();
  });
  textures.forEach((texture) => {
    texture.dispose();
    texture.source?.data?.close?.();
  });
  geometries.forEach((geometry) => geometry.dispose());
  model?.removeFromParent();
};

export const prepareGarment = (model, color) => {
  const meshes = [];
  const sourceMaterials = new Set();
  const sourceTextures = new Set();
  model.traverse((object) => {
    if (!object.isMesh || !object.geometry) return;
    meshes.push(object);
    const sources = Array.isArray(object.material) ? object.material : [object.material];
    sources.filter(Boolean).forEach((material) => sourceMaterials.add(material));
  });
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  if (!meshes.length || box.isEmpty() || !Number.isFinite(size.length()) || size.y <= 0 || size.x <= 0) {
    throw new Error('El modelo no contiene una prenda con volumen válido.');
  }
  model.position.sub(box.getCenter(new THREE.Vector3()));
  model.updateMatrixWorld(true);
  // The tshirt maps contain branding; Oversize is exported with no maps.
  // One fabric material preserves geometry and vertex normals on both models.
  const material = new THREE.MeshStandardMaterial({
    name: 'plain_fabric', color, metalness: 0, roughness: 0.88, side: THREE.DoubleSide,
  });
  meshes.forEach((mesh) => { mesh.material = material; });
  sourceMaterials.forEach((source) => {
    Object.values(source).forEach((value) => { if (value?.isTexture) sourceTextures.add(value); });
    source.dispose();
  });
  sourceTextures.forEach((texture) => {
    texture.dispose();
    texture.source?.data?.close?.();
  });
  return { model, meshes, materials: [material], size };
};

export const getFrameDistance = (size, fieldOfView, aspect, fillRatio) => {
  const halfFov = THREE.MathUtils.degToRad(fieldOfView / 2);
  return Math.max(size.y, size.x / aspect) / (2 * fillRatio * Math.tan(halfFov)) + size.z * 0.6;
};
