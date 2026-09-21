const api = window.GymCultureCustomizationApi;
const authenticated = () => Boolean(localStorage.getItem('gc_access_token') || localStorage.getItem('gc_refresh_token'));
const login = () => window.GymCultureAuth.redirectToLogin();
const announce = (element, message, error = false) => { element.textContent = message; element.classList.toggle('is-error', error); };

if (document.querySelector('#save-design')) initializeEditor().catch(error => announce(document.querySelector('#saved-design-feedback'), error.message, true));
if (document.querySelector('#saved-design-list')) initializeLibrary().catch(error => announce(document.querySelector('#saved-design-status'), error.message, true));

async function initializeEditor() {
  const button = document.querySelector('#save-design'), note = document.querySelector('#saved-design-feedback');
  const dialog = document.querySelector('#save-design-dialog'), form = dialog.querySelector('form');
  let id = new URLSearchParams(location.search).get('saved'), name = '', saving = false, failed = false;
  const sync = () => { button.disabled = saving || failed || !window.GymCulture3D?.canEdit() || !window.GymCultureCustomizer?.state.selectedVariant; };
  document.addEventListener('gymculture:3d-busy', sync);
  document.addEventListener('gymculture:design-selection', sync);
  document.addEventListener('gymculture:editor-change', sync);
  document.addEventListener('gymculture:editor-saving', sync);
  document.querySelector('.customizer-layout').addEventListener('click', sync);
  button.addEventListener('click', () => {
    if (!authenticated()) { login(); return; }
    form.elements.name.value = name || 'Mi diseño'; dialog.showModal(); form.elements.name.focus();
  });
  dialog.querySelector('[data-cancel-save]').addEventListener('click', () => { if (!saving) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving || !form.reportValidity() || !GymCulture3D.canEdit()) return;
    saving = true; sync();
    form.querySelectorAll('button').forEach(element => { element.disabled = true; });
    document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: true }));
    const feedback = dialog.querySelector('[role="status"]'); announce(feedback, 'Guardando tu diseño…');
    try {
      const state = await api.editableCopy(GymCulture3D.getCustomizationState());
      const previews = await GymCulture3D.capturePreviews();
      const data = await api.buildFormData({ state, previews, productId: state.garment.productId, variantId: state.garment.variantId, addToCart: false });
      data.set('name', form.elements.name.value.trim());
      const saved = await api.requestJson(id ? `/api/saved-designs/${id}/` : '/api/saved-designs/', { method: id ? 'PATCH' : 'POST', body: data });
      id = saved.id; name = saved.name;
      const url = new URL(location.href); url.searchParams.delete('customization'); url.searchParams.set('saved', id); history.replaceState(null, '', url);
      document.dispatchEvent(new CustomEvent('gymculture:saved-design-bound'));
      dialog.close(); announce(note, `“${name}” guardado en Mis Diseños.`);
    } catch (error) { announce(feedback, error.message, true); }
    finally {
      saving = false; form.querySelectorAll('button').forEach(element => { element.disabled = false; });
      document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: false })); sync();
    }
  });
  if (!window.GymCulture3D) await new Promise(resolve => document.addEventListener('gymculture:3d-ready', resolve, { once: true }));
  await GymCulture3D.whenReady();
  if (id) {
    if (!authenticated()) { login(); return; }
    saving = true; sync(); document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: true }));
    try {
      const saved = await api.requestJson(`/api/saved-designs/${id}/`);
      await GymCulture3D.loadCustomization(await api.editableCopy(saved.customization_state), { strict: true });
      name = saved.name;
      window.GymCultureHistory?.clear(GymCulture3D.getCustomizationState());
      announce(note, `Editando “${name}”.`);
    } catch (error) {
      failed = true; announce(note, error.message, true);
      document.dispatchEvent(new CustomEvent('gymculture:saved-design-failed'));
    } finally { saving = false; document.dispatchEvent(new CustomEvent('gymculture:editor-saving', { detail: false })); }
  }
  sync();
}

async function initializeLibrary() {
  const host = document.querySelector('#saved-design-list'), note = document.querySelector('#saved-design-status');
  const dialog = document.querySelector('#delete-saved-dialog');
  if (!authenticated()) { login(); return; }
  let page = '/api/saved-designs/', selected, loading = false;
  const objectUrls = new Set();
  const release = () => { objectUrls.forEach(url => URL.revokeObjectURL(url)); objectUrls.clear(); };
  window.addEventListener('pagehide', release);
  async function load(url = page) {
    if (loading) return;
    loading = true; host.inert = true; announce(note, 'Cargando tus diseños…');
    try {
      const data = await api.requestJson(url); page = url; release(); host.replaceChildren();
      for (const item of data.results) {
        const card = document.createElement('article'); card.className = 'saved-design-card'; card.dataset.savedId = item.id;
        const image = document.createElement('img'); image.alt = item.name;
        const heading = document.createElement('h2'); heading.textContent = item.name;
        const details = document.createElement('p'); details.textContent = `${{ tshirt: 'Remera Clásica', oversized: 'Remera Oversize', hoodie: 'Hoodie' }[item.garment_type]} · ${new Date(item.updated_at).toLocaleDateString('es-PY')}`;
        const actions = document.createElement('div'); actions.className = 'saved-design-actions';
        const edit = document.createElement('a'); edit.className = 'button button-accent'; edit.href = `/crear-mi-remera/?saved=${item.id}`; edit.textContent = 'EDITAR';
        actions.append(edit);
        for (const [action, label] of [['duplicate', 'DUPLICAR'], ['delete', 'ELIMINAR']]) {
          const button = document.createElement('button'); button.className = 'button button-outline'; button.type = 'button'; button.dataset.savedAction = action; button.textContent = label; actions.append(button);
        }
        card.append(image, heading, details, actions); host.append(card);
        try {
          const response = await api.fetchAsset(item.preview_image);
          if (!response.ok) throw new Error('Preview no disponible');
          const url = URL.createObjectURL(await response.blob()); objectUrls.add(url); image.src = url;
        } catch { image.alt = `Vista previa no disponible: ${item.name}`; }
      }
      for (const direction of ['previous', 'next']) {
        const button = document.querySelector(`[data-saved-page="${direction}"]`); button.disabled = !data[direction]; button.dataset.url = data[direction] || '';
      }
      announce(note, data.count ? `${data.count} diseños guardados.` : 'Todavía no guardaste diseños. Creá el primero en Custom Lab.');
    } catch (error) { announce(note, error.message, true); }
    finally { loading = false; host.inert = false; }
  }
  document.querySelectorAll('[data-saved-page]').forEach(button => button.addEventListener('click', () => load(button.dataset.url)));
  host.addEventListener('click', async event => {
    const button = event.target.closest('[data-saved-action]');
    if (!button || loading) return;
    const id = button.closest('[data-saved-id]').dataset.savedId;
    if (button.dataset.savedAction === 'delete') { selected = id; dialog.showModal(); return; }
    button.disabled = true;
    try { await api.requestJson(`/api/saved-designs/${id}/duplicate/`, { method: 'POST' }); await load('/api/saved-designs/'); }
    catch (error) { announce(note, error.message, true); button.disabled = false; }
  });
  dialog.querySelector('[data-cancel-delete]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-confirm-delete]').addEventListener('click', async event => {
    event.target.disabled = true;
    try { await api.requestJson(`/api/saved-designs/${selected}/`, { method: 'DELETE' }); dialog.close(); await load('/api/saved-designs/'); }
    catch (error) { dialog.querySelector('[role="status"]').textContent = error.message; }
    finally { event.target.disabled = false; }
  });
  await load();
}
