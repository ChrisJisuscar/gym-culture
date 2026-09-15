import * as THREE from '/static/vendor/three/three.module.min.js';
import { projectDecal } from './decal-projector.js';
import { createTextTexture } from './text-texture.js';
import { BackgroundRemovalService } from './background-removal-service.js';

export const DESIGN_LIMITS = {
  maxFileBytes: 10 * 1024 * 1024,
  minImageDimension: 64,
  maxImageDimension: 8192,
  minScale: 0.35,
  maxScale: 2.5,
  defaultSizeFactor: 0.2,
};

const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);
const vectorData = (vector) => ({ x: vector.x, y: vector.y, z: vector.z });
const toVector = (data) => new THREE.Vector3(data.x, data.y, data.z);
const createId = () => crypto.randomUUID?.() || `design-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const readImage = (file) => new Promise((resolve, reject) => {
  if (!IMAGE_TYPES.has(file.type)) return reject(new Error('Usá una imagen PNG, JPG o WebP válida.'));
  if (file.size > DESIGN_LIMITS.maxFileBytes) return reject(new Error('La imagen supera el límite de 10 MB.'));
  const reader = new FileReader();
  reader.onerror = () => reject(new Error('No se pudo leer el archivo seleccionado.'));
  reader.onload = () => {
    const image = new Image();
    image.onerror = () => reject(new Error('El archivo no contiene una imagen válida.'));
    image.onload = () => {
      if (Math.min(image.naturalWidth, image.naturalHeight) < DESIGN_LIMITS.minImageDimension) {
        reject(new Error('La imagen debe medir al menos 64 px por lado.'));
        return;
      }
      if (Math.max(image.naturalWidth, image.naturalHeight) > DESIGN_LIMITS.maxImageDimension) {
        reject(new Error('La imagen no puede superar 8192 px por lado.'));
        return;
      }
      resolve({ image, dataUrl: reader.result, aspectRatio: image.naturalWidth / image.naturalHeight, mimeType: file.type, size: file.size });
    };
    image.src = reader.result;
  };
  reader.readAsDataURL(file);
});

// Remote recommendations use the same validation and editable representation as uploads.
const readRemoteImage = async (url) => {
  let response;
  try {
    response = await fetch(url, { credentials: 'same-origin' });
  } catch (error) {
    throw new Error('No se pudo descargar el diseño recomendado.');
  }
  if (!response.ok) throw new Error('No se pudo descargar el diseño recomendado.');
  return readImage(await response.blob());
};

const loadTexture = (url) => new Promise((resolve, reject) => {
  new THREE.TextureLoader().load(url, (texture) => {
    texture.colorSpace = THREE.SRGBColorSpace;
    resolve(texture);
  }, undefined, () => reject(new Error('No se pudo cargar un asset de la personalización.')));
});

export class DesignManager {
  constructor({ scene, designs, garmentSize, onChange }) {
    this.scene = scene;
    this.designs = designs;
    this.garmentSize = garmentSize;
    this.onChange = onChange;
    this.resources = new Map();
    this.selectedId = null;
    this.pending = null;
    this.resourceVersion = 0;
    this.orientationHelper = new THREE.Object3D();
    this.processing = null;
  }

  async prepareImage(file) {
    const version = this.resourceVersion;
    const loaded = await readImage(file);
    if (version !== this.resourceVersion) throw new Error('La prenda cambió mientras se leía la imagen. Volvé a subirla.');
    const texture = new THREE.Texture(loaded.image);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    this.clearPending();
    this.pending = {
      type: 'image', texture, aspectRatio: loaded.aspectRatio,
      source: { name: file.name, mimeType: file.type, size: file.size, dataUrl: loaded.dataUrl },
    };
  }

  async applyRemoteDesign({ assetUrl, position, normal, mesh, rotation = 0, scale = 1, sourceName = 'Recomendación GYM CULTURE' }) {
    if (!position || !normal || !mesh) throw new Error('Falta la superficie donde colocar el diseño.');
    const version = this.resourceVersion;
    const loaded = await readRemoteImage(assetUrl);
    if (version !== this.resourceVersion) throw new Error('La prenda cambió mientras se preparaba la recomendación.');
    const texture = new THREE.Texture(loaded.image);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    this.clearPending();
    this.pending = {
      type: 'image', texture, aspectRatio: loaded.aspectRatio,
      source: { name: sourceName, mimeType: loaded.mimeType, size: loaded.size, dataUrl: loaded.dataUrl },
    };
    const design = this.place({
      point: toVector(position),
      normal: toVector(normal),
      mesh,
    });
    try {
      design.rotation = Math.max(-180, Math.min(180, rotation));
      design.scale = Math.max(DESIGN_LIMITS.minScale, Math.min(DESIGN_LIMITS.maxScale, scale));
      this.rebuild(design, mesh);
      this.notify();
    } catch (error) {
      this.removeSelected();
      throw error;
    }
    return design;
  }

  prepareText({ text, fontFamily, color }) {
    this.clearPending();
    const generated = createTextTexture({ text, fontFamily, color });
    this.pending = { type: 'text', ...generated, text, fontFamily, color };
  }

  clearPending() {
    this.pending?.texture?.dispose();
    this.pending = null;
  }

  place(hit) {
    if (!this.pending) return null;
    const id = createId();
    const base = this.garmentSize.y * DESIGN_LIMITS.defaultSizeFactor;
    const design = {
      id,
      type: this.pending.type,
      position: vectorData(hit.point),
      normal: vectorData(hit.normal),
      rotation: 0,
      projectionVersion: 2,
      scale: 1,
      aspectRatio: this.pending.aspectRatio,
      width: this.pending.aspectRatio >= 1 ? base : base * this.pending.aspectRatio,
      height: this.pending.aspectRatio >= 1 ? base / this.pending.aspectRatio : base,
    };
    if (design.type === 'image') design.source = this.pending.source;
    else Object.assign(design, { text: this.pending.text, fontFamily: this.pending.fontFamily, color: this.pending.color, fontSize: 280 });
    this.designs.push(design);
    this.resources.set(id, { texture: this.pending.texture, mesh: null, sourceMesh: hit.mesh });
    this.pending = null;
    try {
      this.rebuild(design, hit.mesh);
    } catch (error) {
      this.resources.get(id).texture.dispose();
      this.resources.delete(id);
      this.designs.splice(this.designs.indexOf(design), 1);
      throw error;
    }
    this.select(id);
    return design;
  }

  orientationFor(design) {
    const position = toVector(design.position);
    this.orientationHelper.position.copy(position);
    this.orientationHelper.lookAt(position.clone().add(toVector(design.normal)));
    if (design.projectionVersion === 2) {
      const rotation = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), THREE.MathUtils.degToRad(design.rotation));
      return new THREE.Euler().setFromQuaternion(this.orientationHelper.quaternion.clone().multiply(rotation));
    }
    const orientation = this.orientationHelper.rotation.clone();
    orientation.z += THREE.MathUtils.degToRad(design.rotation);
    return orientation;
  }

  rebuild(design, sourceMesh) {
    const resource = this.resources.get(design.id);
    if (!resource) return;
    const targetMesh = sourceMesh || resource.sourceMesh;
    const geometry = projectDecal(targetMesh, toVector(design.position), this.orientationFor(design), design.width * design.scale, design.height * design.scale, this.garmentSize);
    if (!geometry.attributes.position?.count) {
      geometry.dispose();
      throw new Error('Esa zona no admite un diseño con el tamaño actual.');
    }
    if (!resource.mesh) {
      const material = new THREE.MeshBasicMaterial({
        map: resource.texture,
        transparent: true,
        alphaTest: .01,
        toneMapped: false,
        depthTest: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -4,
        polygonOffsetUnits: -4,
        side: THREE.FrontSide,
      });
      resource.mesh = new THREE.Mesh(geometry, material);
      resource.mesh.userData.designId = design.id;
      resource.mesh.renderOrder = 2;
      this.scene.add(resource.mesh);
    } else {
      resource.mesh.geometry.dispose();
      resource.mesh.geometry = geometry;
    }
    resource.sourceMesh = targetMesh;
    design.surface = targetMesh.name;
    resource.mesh.visible = targetMesh.visible;
  }

  select(id) {
    if (this.selectedId !== id) this.cancelBackgroundRemoval();
    this.selectedId = this.resources.has(id) ? id : null;
    this.resources.forEach(({ mesh }, resourceId) => {
      if (mesh) mesh.material.opacity = resourceId === this.selectedId ? 0.82 : 1;
    });
    this.notify();
  }

  selected() { return this.designs.find((design) => design.id === this.selectedId) || null; }

  async removeBackground() {
    const design = this.selected();
    if (!design || design.type !== 'image' || this.processing) return;
    if (design.backgroundRemoved) {
      return { before: design.originalSource?.dataUrl || design.originalAssetUrl, after: design.source?.dataUrl || design.assetUrl, applied: true };
    }
    const resource = this.resources.get(design.id);
    const version = this.resourceVersion;
    const operation = {};
    this.processing = operation;
    try {
      const source = await new BackgroundRemovalService().remove(design.source?.dataUrl || design.assetUrl);
      if (version !== this.resourceVersion || this.resources.get(design.id) !== resource || this.selectedId !== design.id) return;
      this.backgroundPreview = { design, resource, version, source };
      return { before: design.source?.dataUrl || design.assetUrl, after: source.dataUrl, confidenceLevel: source.confidenceLevel };
    } finally {
      if (this.processing === operation) this.processing = null;
    }
  }
  cancelBackgroundRemoval() { this.backgroundPreview = null; }

  async applyBackgroundRemoval() {
    const pending = this.backgroundPreview;
    if (!pending || this.processing) return false;
    const { design, resource, version, source } = pending;
    this.processing = pending;
    try {
      const texture = await loadTexture(source.dataUrl);
      if (this.backgroundPreview !== pending || version !== this.resourceVersion || this.resources.get(design.id) !== resource || this.selectedId !== design.id) {
        texture.dispose(); return false;
      }
      if (!design.originalSource && !design.originalAssetId) {
        if (design.source) design.originalSource = { ...design.source };
        else Object.assign(design, { originalAssetId: design.assetId, originalAssetUrl: design.assetUrl });
      }
      design.source = source;
      design.backgroundRemoved = true;
      delete design.assetId; delete design.assetUrl;
      this.replaceTexture(resource, texture);
      this.cancelBackgroundRemoval(); this.notify();
      return true;
    } finally { if (this.processing === pending) this.processing = null; }
  }

  async restoreOriginal() {
    const design = this.selected();
    const url = design?.originalSource?.dataUrl || design?.originalAssetUrl;
    if (!url || this.processing) return false;
    const resource = this.resources.get(design.id), version = this.resourceVersion, operation = {};
    this.processing = operation;
    try {
      const texture = await loadTexture(url);
      if (version !== this.resourceVersion || this.resources.get(design.id) !== resource) { texture.dispose(); return false; }
      delete design.source; delete design.assetId; delete design.assetUrl;
      if (design.originalSource) design.source = { ...design.originalSource };
      else Object.assign(design, { assetId: design.originalAssetId, assetUrl: design.originalAssetUrl });
      delete design.originalSource; delete design.originalAssetId; delete design.originalAssetUrl;
      design.backgroundRemoved = false;
      this.replaceTexture(resource, texture); this.notify();
      return true;
    } finally { if (this.processing === operation) this.processing = null; }
  }

  replaceTexture(resource, texture) {
    const previous = resource.texture;
    resource.texture = texture; resource.mesh.material.map = texture;
    resource.mesh.material.needsUpdate = true; previous.dispose();
  }
  meshes() { return [...this.resources.values()].map((resource) => resource.mesh).filter(Boolean); }

  moveSelected(hit) {
    this.updateSelected({ position: vectorData(hit.point), normal: vectorData(hit.normal) }, hit.mesh);
  }

  updateSelected(changes, sourceMesh) {
    const design = this.selected();
    if (!design) return;
    const candidate = { ...design, ...changes };
    let generated;
    try {
      if (design.type === 'text' && ['text', 'fontFamily', 'color'].some((key) => key in changes)) {
        generated = createTextTexture(candidate);
        candidate.aspectRatio = generated.aspectRatio;
        candidate.width = candidate.height * generated.aspectRatio;
      }
      // Commit state and texture only after the new projection is valid.
      this.rebuild(candidate, sourceMesh);
    } catch (error) {
      generated?.texture.dispose();
      throw error;
    }
    Object.assign(design, candidate);
    if (generated) this.replaceTexture(this.resources.get(design.id), generated.texture);
    this.notify();
  }

  removeSelected() {
    this.cancelBackgroundRemoval();
    const design = this.selected();
    if (!design) return;
    const resource = this.resources.get(design.id);
    this.scene.remove(resource.mesh);
    resource.mesh.geometry.dispose();
    resource.mesh.material.dispose();
    resource.texture.dispose();
    this.resources.delete(design.id);
    this.designs.splice(this.designs.indexOf(design), 1);
    this.selectedId = null;
    this.notify();
  }

  notify() { this.onChange?.(this.selected()); }

  setSelectionHighlight(visible) {
    this.resources.forEach(({ mesh }, resourceId) => {
      if (mesh) mesh.material.opacity = visible && resourceId === this.selectedId ? 0.82 : 1;
    });
  }

  clearResources({ clearState = true } = {}) {
    this.cancelBackgroundRemoval();
    this.resourceVersion += 1;
    this.clearPending();
    this.resources.forEach((resource) => {
      this.scene.remove(resource.mesh);
      resource.mesh?.geometry.dispose();
      resource.mesh?.material.dispose();
      resource.texture?.dispose();
    });
    this.resources.clear();
    this.selectedId = null;
    if (clearState) this.designs.splice(0);
    this.notify();
  }

  async restoreAll(sourceMeshes) {
    const meshes = Array.isArray(sourceMeshes) ? sourceMeshes : [sourceMeshes];
    this.clearResources({ clearState: false });
    const version = this.resourceVersion;
    const failed = [];
    for (const design of this.designs) {
      let texture;
      try {
        if (design.type === 'text') {
          texture = createTextTexture(design).texture;
        } else {
          const url = design.source?.dataUrl || design.assetUrl;
          if (!url) throw new Error('La configuración contiene una imagen sin URL.');
          texture = await loadTexture(url);
        }
        if (version !== this.resourceVersion) {
          texture.dispose();
          throw new Error('La restauración de diseños fue cancelada.');
        }
        const sourceMesh = meshes.find((mesh) => mesh.name === design.surface) || meshes[0];
        this.resources.set(design.id, { texture, mesh: null, sourceMesh });
        this.rebuild(design, sourceMesh);
      } catch (error) {
        texture?.dispose();
        this.resources.delete(design.id);
        if (version !== this.resourceVersion) throw error;
        failed.push(design);
        console.warn('[GYM CULTURE 3D] No se pudo restaurar un diseño.', error);
      }
    }
    this.select(null);
    return failed;
  }

  dispose() {
    this.clearResources();
  }
}
