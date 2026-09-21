import { HistoryManager } from './customizer-3d/history-manager.js';
import { estimatePrintQuality } from './customizer-3d/print-quality.js';

const root = document.querySelector('.customizer-layout');
if (root) initialize().catch(error => { document.querySelector('#design-feedback').textContent = error.message; });

async function initialize() {
  if (!window.GymCulture3D) await new Promise(resolve => document.addEventListener('gymculture:3d-ready', resolve, { once: true }));
  const editor = window.GymCulture3D;
  await editor.whenReady();
  const undo = document.querySelector('#undo-design'), redo = document.querySelector('#redo-design');
  const list = document.querySelector('#layer-list'), quality = document.querySelector('#print-quality');
  const feedback = document.querySelector('#design-feedback');
  const showError = error => { feedback.textContent = error.message; feedback.classList.add('is-error'); };
  const history = new HistoryManager({ restore: async state => {
    const selectedId = editor.getSelectedDesign()?.id;
    await editor.loadCustomization(state, { strict: true });
    editor.selectDesign(state.designs.find(design => design.id === selectedId)?.id || state.designs.at(-1)?.id);
  }, onChange: () => refresh() });
  let gesture = null, queued = false, mergeKey = '', layerSignature = '', profile;

  function refresh() {
    const locked = history.busy || !editor.canEdit();
    undo.disabled = locked || !history.canUndo(); redo.disabled = locked || !history.canRedo();
    root.querySelectorAll('[data-transform], [data-align]').forEach(button => { button.disabled = locked; });
    const layers = editor.getLayers(), selected = editor.getSelectedDesign();
    list.inert = locked;
    const signature = JSON.stringify([layers, selected?.id]);
    if (signature !== layerSignature) {
      layerSignature = signature;
      list.replaceChildren(...[...layers].reverse().map((layer, index) => {
        const row = document.createElement('li'); row.dataset.layerId = layer.id; row.classList.toggle('is-selected', selected?.id === layer.id);
        const button = (label, action, text, disabled = false) => {
          const element = document.createElement('button'); element.type = 'button'; element.dataset.layerAction = action;
          element.textContent = text; element.setAttribute('aria-label', label); element.disabled = disabled; return element;
        };
        const select = button(`Seleccionar ${layer.label}`, 'select', layer.label);
        select.className = 'layer-name'; select.setAttribute('aria-pressed', String(selected?.id === layer.id));
        row.append(select, button(layer.visibility ? 'Ocultar capa' : 'Mostrar capa', 'visibility', layer.visibility ? '◉' : '○'), button('Subir capa', 'up', '↑', index === 0), button('Bajar capa', 'down', '↓', index === layers.length - 1), button('Eliminar capa', 'delete', '×'));
        return row;
      }));
      document.querySelector('#layers-empty').hidden = layers.length > 0;
    }
    const estimate = estimatePrintQuality(selected, window.GymCultureCustomizer.state.garmentType, profile);
    quality.hidden = !estimate;
    if (estimate) {
      const labels = { high: ['Alta', 'Calidad adecuada para impresión.'], medium: ['Media', 'Puede perder algo de definición al imprimir.'], low: ['Baja', 'La imagen puede verse pixelada. Recomendamos una imagen de mayor resolución.'] };
      const [label, message] = labels[estimate.level];
      quality.dataset.level = estimate.level;
      quality.querySelector('strong').textContent = `● Calidad ${label}`;
      quality.querySelector('span').textContent = message;
      quality.title = `${selected.imageWidth} × ${selected.imageHeight} px · ${estimate.dpi} PPI estimados · ${estimate.widthCm} × ${estimate.heightCm} cm aprox. La medida real depende de la prenda y la talla.`;
    }
  }
  function schedule(event) {
    if (event?.type === 'input') mergeKey = `${editor.getSelectedDesign()?.id}:${event.target.id}`;
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      if (!gesture && !history.busy && editor.canEdit()) history.push(editor.getCustomizationState(), { mergeKey });
      mergeKey = ''; refresh();
    });
  }
  async function replay(direction) {
    if (!editor.canEdit() || gesture) return;
    try { await history[direction](); } catch (error) { showError(error); }
  }
  undo.addEventListener('click', () => replay('undo'));
  redo.addEventListener('click', () => replay('redo'));
  document.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || document.querySelector('dialog[open]')) return;
    if (event.target.closest('textarea, select, [contenteditable="true"], input:not([type="range"]):not([type="color"])')) return;
    const key = event.key.toLowerCase();
    if (key !== 'z' && key !== 'y') return;
    event.preventDefault(); replay(key === 'y' || event.shiftKey ? 'redo' : 'undo');
  });
  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('#customizer-3d-container canvas, .config-panel input[type="range"]')) return;
    if (!history.busy && editor.canEdit()) { history.push(editor.getCustomizationState()); gesture = event.pointerId; }
  }, true);
  const finishGesture = event => {
    if (gesture == null || (event.pointerId != null && event.pointerId !== gesture)) return;
    gesture = null; schedule();
  };
  window.addEventListener('pointerup', finishGesture, true);
  window.addEventListener('pointercancel', finishGesture, true);
  window.addEventListener('blur', finishGesture);
  for (const name of ['gymculture:design-selection', 'gymculture:3d-busy', 'gymculture:customization-loaded', 'gymculture:editor-change', 'gymculture:editor-saving']) document.addEventListener(name, schedule);
  root.addEventListener('input', schedule); root.addEventListener('change', schedule); root.addEventListener('click', schedule);
  root.addEventListener('click', event => {
    const transform = event.target.closest('[data-transform]');
    if (!transform) return;
    try {
      const action = transform.dataset.transform;
      if (action === 'front' || action === 'back') editor.changeLayer(editor.getSelectedDesign()?.id, action);
      else editor.transformSelected(action);
    } catch (error) { showError(error); }
  });
  document.querySelector('[data-align]').addEventListener('change', event => {
    if (!event.target.value) return;
    try { editor.transformSelected(event.target.value); } catch (error) { showError(error); }
    event.target.value = '';
  });
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-layer-action]'), id = button?.closest('[data-layer-id]')?.dataset.layerId;
    if (!id || history.busy || !editor.canEdit()) return;
    try {
      if (button.dataset.layerAction === 'select') editor.selectDesign(id);
      else if (button.dataset.layerAction === 'delete') { editor.selectDesign(id); editor.removeSelectedDesign(); }
      else editor.changeLayer(id, button.dataset.layerAction);
    } catch (error) { showError(error); }
  });
  window.GymCultureHistory = history;
  history.clear(editor.getCustomizationState());
  try {
    const response = await fetch('/api/customizations/editor-config/');
    if (!response.ok) throw new Error('No se pudo cargar la configuración de impresión.');
    const config = await response.json(); profile = config.printQuality;
    window.GymCultureEditorConfig = config; refresh();
    document.dispatchEvent(new CustomEvent('gymculture:editor-config', { detail: config }));
  } catch (error) { showError(error); }
}
