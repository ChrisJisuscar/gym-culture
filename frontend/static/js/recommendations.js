import { RecommendationOrbit } from './showroom-orbit.js';
import './customizer-3d.js';

const root = document.querySelector('#recommendations-showroom');
if (root) {
  const stage = root.querySelector('#showroom-stage');
  const host = root.querySelector('#recommendation-viewer');
  const track = root.querySelector('#showroom-track');
  const empty = root.querySelector('#showroom-empty');
  const feedback = root.querySelector('#showroom-feedback');
  const retry = root.querySelector('#showroom-retry');
  const cta = root.querySelector('#use-recommendation');
  const summary = root.querySelector('#recommendation-summary');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const labels = { tshirt: 'Remera Clásica', oversized: 'Remera Oversize', hoodie: 'Hoodie' };
  let items = [], active = null, request, listVersion = 0, selectionVersion = 0, orbit;
  let culture = root.dataset.activeCulture, garment = '', inView = false, applying = false, previewReady = false;
  const tell = (message, error = false) => { feedback.textContent = message; feedback.hidden = !message; feedback.classList.toggle('is-error', error); };
  const select = async (id) => {
    const item = items.find(item => item.id === id);
    if (!item) return;
    const version = ++selectionVersion;
    active = item; previewReady = false; cta.disabled = true;
    host.classList.add('is-loading');
    root.querySelector('#recommendation-title').textContent = item.name;
    root.querySelector('#recommendation-details').textContent = `${item.culture_name} / ${labels[item.garment_type]}`;
    root.querySelector('#recommendation-central-preview').src = item.preview_url || item.preview_image_url;
    orbit?.setItems(items, id);
    if (!inView) { host.classList.remove('is-loading'); return; }
    try {
      await GymCulture3D.whenReady();
      const loaded = await GymCulture3D.configurePreview(item, host);
      if (version !== selectionVersion || !loaded) return;
      previewReady = true;
      if (inView) GymCulture3D.activatePreview(host);
      tell(''); cta.disabled = false;
    } catch (error) {
      if (version === selectionVersion) { tell(error.message || 'No se pudo cargar el modelo. Volvé a intentarlo.', true); retry.hidden = false; }
    } finally { if (version === selectionVersion) host.classList.remove('is-loading'); }
  };
  const reload = async () => {
    request?.abort(); request = new AbortController();
    const version = ++listVersion; selectionVersion++;
    garment = GymCultureCustomizer.state.garmentType;
    root.querySelector('[data-showroom-garment]').textContent = labels[garment];
    root.querySelector('[data-showroom-culture]').textContent = document.querySelector('.culture-chip.is-active .culture-chip-name')?.textContent || '';
    root.setAttribute('aria-busy', 'true'); retry.hidden = true; cta.disabled = true;
    tell('Preparando tu selección…');
    try {
      const response = await fetch(`/api/design-recommendations/?${new URLSearchParams({ culture, garment })}`, { signal: request.signal });
      if (!response.ok) throw new Error('No pudimos cargar las recomendaciones.');
      const data = await response.json();
      if (version !== listVersion) return;
      items = culture ? data.results : []; active = null;
      stage.hidden = !items.length; summary.hidden = !items.length; empty.hidden = !!items.length;
      root.querySelector('#showroom-count').textContent = `${String(items.length).padStart(2, '0')} DISEÑOS`;
      root.querySelector('.showroom-navigation').hidden = items.length < 2;
      if (items.length) { await select(items[0].id); }
      else { orbit?.setItems([], null); GymCulture3D.clearPreview(); tell(''); }
    } catch (error) {
      if (error.name === 'AbortError' || version !== listVersion) return;
      GymCulture3D.clearPreview(); stage.hidden = true; summary.hidden = true; retry.hidden = false; tell(error.message, true);
    } finally { if (version === listVersion) root.setAttribute('aria-busy', 'false'); }
  };
  orbit = new RecommendationOrbit(stage, track, select);
  const navigate = direction => {
    if (items.length < 2) return;
    const index = items.findIndex(item => item.id === active?.id);
    select(items[(index + direction + items.length) % items.length].id);
  };
  const observer = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    if (applying) return;
    if (inView && active) {
      if (previewReady) GymCulture3D.activatePreview(host);
      else select(active.id);
    } else if (!inView) GymCulture3D.activateEditor();
  }, { threshold: .15 });
  observer.observe(host);
  host.addEventListener('pointerdown', () => { if (previewReady) GymCulture3D.activatePreview(host); });
  cta.addEventListener('click', async () => {
    if (!active || applying) return;
    applying = true; cta.disabled = true;
    try {
      let configuration;
      if (active.customization_state?.version === 1) configuration = await GymCultureCustomizationApi.editableCopy(active.customization_state);
      GymCulture3D.activateEditor();
      if (configuration) await GymCulture3D.loadCustomization(configuration);
      else await GymCulture3D.applyDesignAsset({ assetUrl: active.design_asset_url, garmentType: active.garment_type, position: active.default_position, scale: active.default_scale, rotation: active.default_rotation, name: active.name, baseColor: active.base_color, baseColorHex: active.base_color_hex });
      document.querySelector('.customizer-layout').scrollIntoView({ behavior: reduced.matches ? 'instant' : 'smooth', block: 'start' });
      document.querySelector('#add-3d-text').focus({ preventScroll: true });
      tell(`“${active.name}” está en tu Custom Lab. Todos sus elementos son editables.`);
    } catch (error) { tell(error.message, true); }
    finally { applying = false; cta.disabled = !previewReady; }
  });
  document.querySelectorAll('.culture-chip').forEach(chip => chip.addEventListener('click', () => {
    if (culture === chip.dataset.culture) return;
    culture = chip.dataset.culture; root.dataset.activeCulture = culture;
    document.querySelectorAll('.culture-chip').forEach(button => { const current = button === chip; button.classList.toggle('is-active', current); button.setAttribute('aria-pressed', String(current)); });
    const url = new URL(location.href); url.searchParams.set('culture', culture); history.replaceState(null, '', url);
    reload();
  }));
  document.addEventListener('gymculture:garment-changed', () => { if (garment !== GymCultureCustomizer.state.garmentType) reload(); });
  retry.addEventListener('click', () => { retry.hidden = true; if (active && items.length && !stage.hidden) select(active.id); else reload(); });
  root.querySelector('[data-showroom-prev]').addEventListener('click', () => navigate(-1));
  root.querySelector('[data-showroom-next]').addEventListener('click', () => navigate(1));
  track.addEventListener('keydown', event => { if (['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); orbit.nudge(event.key === 'ArrowLeft' ? -1 : 1); } });
  root.querySelector('[data-showroom-edit]').addEventListener('click', () => { GymCulture3D.activateEditor(); document.querySelector('.customizer-layout').scrollIntoView({ behavior: 'smooth' }); });
  window.addEventListener('pagehide', event => { if (!event.persisted) { request?.abort(); observer.disconnect(); orbit.dispose(); GymCulture3D.clearPreview(); } });
  reload();
}
