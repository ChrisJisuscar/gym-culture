export const GARMENTS = Object.freeze({
  tshirt: Object.freeze({ label: 'Remera', modelUrl: '/static/models/tshirt.glb', enabled: true }),
  oversized: Object.freeze({ label: 'Oversize', modelUrl: '/static/models/oversized.glb', enabled: true,
    printSurface: Object.freeze({ innerWidth: .18, outerWidth: .28, bottom: -.49, bottomFade: -.36, topFade: .28, top: .4, iterations: 60, strength: .55 }),
  }),
  hoodie: Object.freeze({ label: 'Hoodie', enabled: true, modelUrl: '/static/models/hoodie.glb', hoodMeshes: { down: 'Hood_off', up: 'Hood_on' } }),
});

export const getGarment = (type) => Object.hasOwn(GARMENTS, type) ? GARMENTS[type] : null;
