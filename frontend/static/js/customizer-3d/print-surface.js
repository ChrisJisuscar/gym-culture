import * as THREE from '/static/vendor/three/three.module.min.js';

// Relax depth on the torso only. Keeping every x/y coordinate fixes the outline,
// sleeves and neckline while removing high-frequency folds under the print.
export function relaxPrintSurface(mesh, height, options) {
  const geometry = mesh.geometry, positions = geometry.attributes.position;
  const inverse = mesh.matrixWorld.clone().invert();
  const vertices = [], indices = [], lookup = new Map();
  const smooth = THREE.MathUtils.smoothstep;
  const point = new THREE.Vector3();
  for (let index = 0; index < positions.count; index++) {
    point.fromBufferAttribute(positions, index).applyMatrix4(mesh.matrixWorld);
    const key = point.toArray().map(value => Math.round(value / height * 1e6)).join(',');
    if (!lookup.has(key)) {
      const x = point.x / height, y = point.y / height;
      const weight = (1 - smooth(Math.abs(x), options.innerWidth, options.outerWidth))
        * smooth(y, options.bottom, options.bottomFade)
        * (1 - smooth(y, options.topFade, options.top));
      lookup.set(key, vertices.length);
      vertices.push({ point: point.clone(), depth: point.z, weight, neighbors: new Set(), normal: new THREE.Vector3() });
    }
    indices.push(lookup.get(key));
  }
  const triangles = geometry.index?.array || Array.from({ length: positions.count }, (_, index) => index);
  for (let index = 0; index < triangles.length; index += 3) {
    const face = [0, 1, 2].map(offset => indices[triangles[index + offset]]);
    face.forEach((vertex, offset) => {
      vertices[vertex].neighbors.add(face[(offset + 1) % 3]);
      vertices[vertex].neighbors.add(face[(offset + 2) % 3]);
    });
  }
  for (let iteration = 0; iteration < options.iterations; iteration++) {
    const next = vertices.map(vertex => {
      if (!vertex.weight || !vertex.neighbors.size) return vertex.depth;
      let total = 0; vertex.neighbors.forEach(index => { total += vertices[index].depth; });
      return THREE.MathUtils.lerp(vertex.depth, total / vertex.neighbors.size, options.strength * vertex.weight);
    });
    vertices.forEach((vertex, index) => { vertex.depth = next[index]; });
  }
  vertices.forEach(vertex => { vertex.point.z = vertex.depth; });
  const edgeA = new THREE.Vector3(), edgeB = new THREE.Vector3();
  for (let index = 0; index < triangles.length; index += 3) {
    const face = [0, 1, 2].map(offset => vertices[indices[triangles[index + offset]]]);
    const normal = edgeA.subVectors(face[1].point, face[0].point).cross(edgeB.subVectors(face[2].point, face[0].point));
    face.forEach(vertex => vertex.normal.add(normal));
  }
  const localNormal = new THREE.Matrix3().setFromMatrix4(mesh.matrixWorld).transpose();
  const normals = geometry.attributes.normal;
  indices.forEach((vertexIndex, index) => {
    const vertex = vertices[vertexIndex];
    if (!vertex.weight) return;
    point.copy(vertex.point).applyMatrix4(inverse); positions.setXYZ(index, point.x, point.y, point.z);
    point.copy(vertex.normal).applyMatrix3(localNormal).normalize(); normals.setXYZ(index, point.x, point.y, point.z);
  });
  positions.needsUpdate = true; normals.needsUpdate = true;
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
}
