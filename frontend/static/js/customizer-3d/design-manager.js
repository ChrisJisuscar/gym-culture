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
      resolve({ image, dataUrl: reader.result, aspectRatio: image.naturalWidth / image.naturalHeight });
    };
    image.src = reader.result;
  };
  reader.readAsDataURL(file);
});

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
    this.rebuild(design, hit.mesh);
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
    const resource = this.resources.get(design.id);
    const version = this.resourceVersion;
    const operation = {};
    this.processing = operation;
    try {
      const source = await new BackgroundRemovalService().remove(design.source?.dataUrl || design.assetUrl);
      const texture = await loadTexture(source.dataUrl);
      if (version !== this.resourceVersion || this.resources.get(design.id) !== resource) {
        texture.dispose();
        return;
      }
      if (!design.originalSource && !design.originalAssetId) {
        if (design.source) design.originalSource = { ...design.source };
        else Object.assign(design, { originalAssetId: design.assetId, originalAssetUrl: design.assetUrl });
      }
      design.source = source;
      design.backgroundRemoved = true;
      delete design.assetId;
      delete design.assetUrl;
      const previous = resource.texture;
      resource.texture = texture;
      resource.mesh.material.map = texture;
      resource.mesh.material.needsUpdate = true;
      previous.dispose();
      this.notify();
    } finally {
      if (this.processing === operation) this.processing = null;
    }
  }
  meshes() { return [...this.resources.values()].map((resource) => resource.mesh).filter(Boolean); }

  moveSelected(hit) {
    const design = this.selected();
    if (!design) return;
    design.position = vectorData(hit.point);
    design.normal = vectorData(hit.normal);
    this.rebuild(design, hit.mesh);
    this.notify();
  }

  updateSelected(changes) {
    const design = this.selected();
    if (!design) return;
    Object.assign(design, changes);
    if (design.type === 'text' && ['text', 'fontFamily', 'color'].some((key) => key in changes)) {
      const resource = this.resources.get(design.id);
      const generated = createTextTexture(design);
      resource.texture.dispose();
      resource.texture = generated.texture;
      resource.mesh.material.map = generated.texture;
      resource.mesh.material.needsUpdate = true;
      design.aspectRatio = generated.aspectRatio;
      design.width = design.height * generated.aspectRatio;
    }
    this.rebuild(design);
    this.notify();
  }

  removeSelected() {
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
          if (!design.assetUrl) throw new Error('La configuración contiene una imagen sin URL.');
          texture = await loadTexture(design.assetUrl);
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
