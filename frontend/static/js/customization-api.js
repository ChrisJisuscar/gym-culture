(() => {
  const dataUrlToBlob = async (dataUrl) => {
    const response = await fetch(dataUrl);
    return response.blob();
  };

  const buildFormData = async ({ productId, variantId, state, previews, addToCart }) => {
    const configuration = JSON.parse(JSON.stringify(state));
    const assets = new Map();
    for (const design of configuration.designs) {
      if (design.type !== 'image' || !design.source?.dataUrl) continue;
      const source = design.source;
      let assetKey = assets.get(source.dataUrl)?.key;
      if (!assetKey) {
        assetKey = crypto.randomUUID?.() || `asset-${Date.now()}-${assets.size}`;
        assets.set(source.dataUrl, { key: assetKey, source });
      }
      design.assetKey = assetKey;
      delete design.source;
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
    const response = await window.GymCultureAuth.request(url, options);
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
    buildFormData,
    create: (form) => requestJson('/api/customizations/', { method: 'POST', body: form }),
    update: (id, form) => requestJson(`/api/customizations/${id}/`, { method: 'PATCH', body: form }),
    get: (id) => requestJson(`/api/customizations/${id}/`),
  };
})();
