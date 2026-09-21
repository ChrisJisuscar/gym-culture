(() => {
  const fetchAsset = (url) => {
    const target = new URL(url, location.href);
    const privatePath = /^\/api\/customizations\/(?:generated\/|[0-9a-f-]+\/(?:assets|previews)\/)/.test(target.pathname);
    return target.origin === location.origin && privatePath ? window.GymCultureAuth.request(target.href) : fetch(url, { credentials: 'same-origin' });
  };
  const dataUrlToBlob = async (dataUrl) => {
    const response = await fetch(dataUrl);
    return response.blob();
  };

  const buildFormData = async ({ productId, variantId, state, previews, addToCart }) => {
    const configuration = JSON.parse(JSON.stringify(state));
    const assets = new Map();
    for (const design of configuration.designs) {
      if (design.type !== 'image') continue;
      for (const [sourceField, keyField] of [['source', 'assetKey'], ['originalSource', 'originalAssetKey']]) {
      const source = design[sourceField];
      if (!source?.dataUrl) continue;
      let assetKey = assets.get(source.dataUrl)?.key;
      if (!assetKey) {
        assetKey = crypto.randomUUID?.() || `asset-${Date.now()}-${assets.size}`;
        assets.set(source.dataUrl, { key: assetKey, source });
      }
      design[keyField] = assetKey;
      delete design[sourceField === 'source' ? 'assetId' : 'originalAssetId'];
      delete design[sourceField === 'source' ? 'assetUrl' : 'originalAssetUrl'];
      delete design[sourceField];
      }
    }
    const form = new FormData();
    form.append('product', productId);
    form.append('variant', variantId);
    form.append('configuration', JSON.stringify(configuration));
    form.append('preview_front', previews.front, 'preview-front.webp');
    form.append('preview_back', previews.back, 'preview-back.webp');
    form.append('add_to_cart', String(Boolean(addToCart)));
    for (const [dataUrl, { key, source }] of assets) {
      const blob = await dataUrlToBlob(dataUrl);
      const extension = source.mimeType === 'image/jpeg' ? 'jpg' : source.mimeType.split('/')[1];
      form.append(`asset_${key}`, blob, `design.${extension}`);
    }
    return form;
  };

  const requestJson = async (url, options = {}) => {
    if (document.querySelector('[data-customizer-mode="recommendation-admin"]')) return window.GymCultureBackoffice.requestJson(url, options);
    let response;
    try {
      response = await window.GymCultureAuth.request(url, options);
    } catch (error) {
      if (window.GymCultureAuth.isSessionError?.(error)) throw error;
      throw new Error('No se pudo conectar con el servidor. Intentá nuevamente.');
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const message = data.detail || Object.values(data).flat(Infinity).join(' ') || 'No se pudo guardar la personalización.';
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  };

  window.GymCultureCustomizationApi = {
    fetchAsset,
    buildFormData,
    create: (form) => requestJson('/api/customizations/', { method: 'POST', body: form }),
    update: (id, form) => requestJson(`/api/customizations/${id}/`, { method: 'PATCH', body: form }),
    get: (id) => requestJson(`/api/customizations/${id}/`),
    requestJson,
    // Copy public recommendation assets into the customer's own upload flow.
    // Recommendation UUIDs must never be submitted as customer-owned assets.
    editableCopy: async (state, { retainReferences = false } = {}) => {
      const configuration = JSON.parse(JSON.stringify(state));
      const cached = new Map();
      for (const design of configuration.designs) {
        if (design.type !== 'image') continue;
        for (const [urlKey, idKey, sourceKey] of [['assetUrl', 'assetId', 'source'], ['originalAssetUrl', 'originalAssetId', 'originalSource']]) {
          if (!design[urlKey]) continue;
          // Local copies keep history usable after a save replaces remote files.
          if (design[sourceKey]?.dataUrl) {
            if (!retainReferences) { delete design[idKey]; delete design[urlKey]; }
            continue;
          }
          if (!cached.has(design[urlKey])) {
            const response = await fetchAsset(design[urlKey]);
            if (!response.ok) throw new Error('No se pudo descargar una imagen del diseño.');
            const blob = await response.blob();
            if (!['image/png', 'image/jpeg', 'image/webp'].includes(blob.type) || blob.size > 10 * 1024 * 1024) throw new Error('Una imagen del diseño no es válida.');
            const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('No se pudo leer la imagen.')); reader.readAsDataURL(blob); });
            cached.set(design[urlKey], { dataUrl, mimeType: blob.type, size: blob.size, name: 'Diseño guardado' });
          }
          design[sourceKey] = { ...cached.get(design[urlKey]) };
          if (!retainReferences) { delete design[idKey]; delete design[urlKey]; }
        }
      }
      return configuration;
    },
  };
})();
