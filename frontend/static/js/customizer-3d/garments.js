export const GARMENTS = Object.freeze({
  tshirt: Object.freeze({ label: 'Remera', modelUrl: '/static/models/tshirt.glb', enabled: true }),
  oversized: Object.freeze({ label: 'Oversize', modelUrl: '/static/models/oversized.glb', enabled: true }),
  hoodie: Object.freeze({ label: 'Hoodie', enabled: true, modelUrl: '/static/models/hoodie.glb', hoodMeshes: { down: 'Hood_off', up: 'Hood_on' } }),
});

export const getGarment = (type) => Object.hasOwn(GARMENTS, type) ? GARMENTS[type] : null;
