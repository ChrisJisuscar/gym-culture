const page = document.querySelector('[data-customizer-mode="recommendation-admin"]');
if (page) {
  const form = document.querySelector('#recommendation-editor-meta');
  const button = document.querySelector('#save-recommendation');
  const feedback = document.querySelector('#recommendation-editor-feedback');
  const api = window.GymCultureCustomizationApi;
  let id = page.dataset.recommendationId, authorized = false, saving = false, dirty = false;
  const tell = (message, error = false) => { feedback.textContent = message; feedback.classList.toggle('is-error', error); };
  const sync = () => { button.disabled = !authorized || saving || !window.GymCulture3D?.isReady(); };
  document.addEventListener('gymculture:3d-busy', sync);
  document.addEventListener('gymculture:3d-ready', sync);
  form.addEventListener('input', () => { dirty = true; });
  document.addEventListener('gymculture:design-selection', () => { if (authorized) dirty = true; });
  document.querySelector('.customizer-layout').addEventListener('input', () => { dirty = true; });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  const initialize = async () => {
    try {
      await GymCulture3D.whenReady();
      if (!GymCulture3D.isReady()) throw new Error('El editor 3D no pudo iniciar.');
      if (id) {
        const item = await api.requestJson(`/api/backoffice/recommendations/${id}/`);
        for (const key of ['name', 'culture']) form.elements[key].value = item[key];
        for (const key of ['active', 'featured']) form.elements[key].checked = item[key];
        if (item.customization_state?.version === 1) {
          await GymCulture3D.loadCustomization(await api.editableCopy(item.customization_state, { retainReferences: true }), { strict: true });
        } else {
          await GymCulture3D.applyDesignAsset({ assetUrl: item.design_asset_url, garmentType: item.garment_type, position: item.default_position, rotation: item.default_rotation, scale: item.default_scale, name: item.name, baseColor: item.base_color, baseColorHex: item.base_color_hex });
        }
        if (item.preview_image_url) { const preview = document.querySelector('#recommendation-saved-preview'); preview.src = item.preview_image_url; preview.hidden = false; }
      }
      authorized = true; dirty = false;
      tell('Editá la prenda en el Custom Lab. La vista previa se genera automáticamente al guardar.');
    } catch (error) { tell(error.message, true); }
    sync();
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!authorized || saving || !GymCulture3D.isReady() || !form.reportValidity()) return;
    saving = true; sync(); tell('Generando vista previa y guardando recomendación…');
    document.querySelector('.customizer-layout').inert = true;
    document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: true }));
    try {
      const state = GymCulture3D.getCustomizationState();
      const previews = await GymCulture3D.capturePreviews({ size: 640, quality: .82 });
      const data = await api.buildFormData({ state, previews });
      for (const key of ['product', 'variant', 'add_to_cart', 'preview_back']) data.delete(key);
      data.set('customization_state', data.get('configuration')); data.delete('configuration');
      data.set('preview_image', previews.front, 'recommendation.webp'); data.delete('preview_front');
      for (const key of ['name', 'culture']) data.set(key, form.elements[key].value);
      for (const key of ['active', 'featured']) data.set(key, String(form.elements[key].checked));
      data.set('garment_type', state.garment.type);
      const item = await api.requestJson(id ? `/api/backoffice/recommendations/${id}/` : '/api/backoffice/recommendations/', { method: id ? 'PATCH' : 'POST', body: data });
      id = item.id; page.dataset.recommendationId = id;
      history.replaceState(null, '', `/backoffice/recommendations/${id}/edit/`);
      const preview = document.querySelector('#recommendation-saved-preview'); preview.src = item.preview_image_url; preview.hidden = false;
      dirty = false;
      tell('Recomendación guardada. La vista previa y todos los elementos quedaron actualizados.');
    } catch (error) { tell(error.message, true); }
    finally {
      saving = false; document.querySelector('.customizer-layout').inert = false;
      document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: false })); sync();
    }
  });
  initialize();
}
