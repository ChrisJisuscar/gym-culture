// Run from the repository root after installing the documented tooling in .venv.
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as THREE from '../../.venv/custom-lab-tools/node_modules/three/build/three.module.js';
import { FBXLoader } from '../../.venv/custom-lab-tools/node_modules/three/examples/jsm/loaders/FBXLoader.js';
import { GLTFExporter } from '../../.venv/custom-lab-tools/node_modules/three/examples/jsm/exporters/GLTFExporter.js';
import validator from '../../.venv/custom-lab-tools/node_modules/gltf-validator/index.js';

// GLTFExporter uses the browser FileReader API to package its binary buffer.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then((buffer) => {
      this.result = buffer;
      this.onloadend?.();
    });
  }
};

const source = 'frontend/static/models/Low_Hoodie.fbx';
const destination = 'frontend/static/models/hoodie.glb';
const bytes = await fs.readFile(source);
const model = new FBXLoader().parse(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
model.updateMatrixWorld(true);
const originalBox = new THREE.Box3().setFromObject(model);
const center = originalBox.getCenter(new THREE.Vector3());
const scale = 1 / originalBox.getSize(new THREE.Vector3()).y;
const report = {
  source, sha256: createHash('sha256').update(bytes).digest('hex'),
  conversion: 'Three.js r160 FBXLoader / GLTFExporter',
  originalBox, scale, orientation: 'Y up, front +Z; no rotation', meshes: [],
};
const plain = new THREE.MeshStandardMaterial({
  name: 'hoodie_plain_fabric', color: '#ffffff', metalness: 0, roughness: 0.88, side: THREE.DoubleSide,
});
model.traverse((object) => {
  if (!object.isMesh) return;
  const geometry = object.geometry;
  const materials = Array.isArray(object.material) ? object.material : [object.material];
  const uv = geometry.getAttribute('uv');
  const uvBox = new THREE.Box2();
  for (let i = 0; i < uv.count; i++) uvBox.expandByPoint(new THREE.Vector2(uv.getX(i), uv.getY(i)));
  report.meshes.push({
    name: object.name, morphTargets: object.morphTargetDictionary, vertices: geometry.attributes.position.count,
    triangles: geometry.attributes.position.count / 3, attributes: Object.keys(geometry.attributes), uvBox,
    materials: materials.map((material) => ({
      name: material.name, color: material.color.toArray(),
      maps: Object.entries(material).filter(([, value]) => value?.isTexture).map(([name]) => name),
    })),
    groups: geometry.groups.map((group) => {
      const box = new THREE.Box3();
      for (let i = group.start; i < group.start + group.count; i++) {
        box.expandByPoint(new THREE.Vector3().fromBufferAttribute(geometry.attributes.position, i));
      }
      return { ...group, box };
    }),
  });
  // Preserve every face, UV and vertex normal. Only consolidate material slots.
  geometry.clearGroups();
  object.material = plain;
  object.userData = {};
});
// Normalize scene coordinates, not the physical product size. Keep proportions.
const root = new THREE.Group();
root.name = 'Hoodie';
root.add(model);
root.scale.setScalar(scale);
root.position.copy(center).multiplyScalar(-scale);
root.updateMatrixWorld(true);
report.finalBox = new THREE.Box3().setFromObject(root);
const glb = await new GLTFExporter().parseAsync(root, { binary: true, onlyVisible: true });
const validation = await validator.validateBytes(new Uint8Array(glb), { uri: 'hoodie.glb' });
report.validation = validation.issues;
if (validation.issues.numErrors) throw new Error(JSON.stringify(validation.issues));
await fs.writeFile(destination, Buffer.from(glb));
await fs.writeFile('tools/custom-lab/hoodie-inspection.json', JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ destination, bytes: glb.byteLength, box: report.finalBox, validation: validation.issues }, null, 2));
