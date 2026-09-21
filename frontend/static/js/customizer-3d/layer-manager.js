export function normalizeLayers(designs) {
  const order = new Map(designs.map((design, index) => [design.id, design.layerOrder ?? index]));
  designs.sort((a, b) => order.get(a.id) - order.get(b.id));
  designs.forEach((design, index) => {
    Object.assign(design, { layerOrder: index, visibility: design.visibility !== false, flipX: !!design.flipX, flipY: !!design.flipY });
  });
}

export function syncLayers(manager) {
  normalizeLayers(manager.designs);
  manager.designs.forEach(design => {
    const resource = manager.resources.get(design.id);
    if (!resource?.mesh) return;
    resource.mesh.renderOrder = 2 + design.layerOrder;
    resource.mesh.visible = design.visibility && resource.sourceMesh.visible;
  });
}

export function changeLayer(manager, id, action) {
  normalizeLayers(manager.designs);
  const index = manager.designs.findIndex(design => design.id === id);
  if (index < 0) return;
  const design = manager.designs[index];
  if (action === 'visibility') design.visibility = !design.visibility;
  else {
    const destination = { up: index + 1, down: index - 1, front: manager.designs.length - 1, back: 0 }[action];
    if (destination == null || destination < 0 || destination >= manager.designs.length) return;
    manager.designs.splice(index, 1); manager.designs.splice(destination, 0, design);
    manager.designs.forEach((item, order) => { item.layerOrder = order; });
  }
  syncLayers(manager); manager.notify();
}
