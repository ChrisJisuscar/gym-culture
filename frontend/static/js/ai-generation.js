const openButton = document.querySelector('#generate-ai');
if (openButton) {
  const dialog = document.querySelector('#ai-generation-dialog'), form = dialog.querySelector('form');
  const feedback = dialog.querySelector('[role="status"]'), result = dialog.querySelector('.ai-result');
  const use = dialog.querySelector('[data-use-generated]'), preview = dialog.querySelector('img');
  let file, previewUrl, processing = false;
  const configure = config => {
    const enabled = Boolean(config?.generation.enabled);
    form.querySelector('[type="submit"]').disabled = !enabled || processing;
    if (!enabled) feedback.textContent = 'La generación con IA todavía no está habilitada. Podés subir tu propio diseño.';
  };
  const release = () => { if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null; file = null; preview.removeAttribute('src'); result.hidden = true; };
  document.addEventListener('gymculture:editor-config', event => configure(event.detail));
  openButton.addEventListener('click', () => { configure(window.GymCultureEditorConfig); dialog.showModal(); });
  dialog.querySelector('[data-close-ai]').addEventListener('click', () => { if (!processing) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (processing) event.preventDefault(); });
  dialog.addEventListener('close', release); window.addEventListener('pagehide', release);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (processing || !form.reportValidity()) return;
    if (!localStorage.getItem('gc_access_token') && !localStorage.getItem('gc_refresh_token')) { window.GymCultureAuth.redirectToLogin(); return; }
    processing = true; release(); configure(window.GymCultureEditorConfig); feedback.textContent = 'Generando tu idea…';
    try {
      const data = new FormData(form);
      const generated = await GymCultureCustomizationApi.requestJson('/api/customizations/generate-image/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: data.get('prompt'), culture: data.get('culture'), format: data.get('format'), transparent: data.get('transparent') === 'on' }),
      });
      const response = await GymCultureCustomizationApi.fetchAsset(generated.url);
      if (!response.ok) throw new Error('No se pudo recuperar la imagen generada.');
      const blob = await response.blob();
      file = new File([blob], 'Diseño IA.png', { type: blob.type });
      previewUrl = URL.createObjectURL(blob); preview.src = previewUrl; result.hidden = false;
      feedback.textContent = 'Podés usarlo como cualquier imagen y quitarle el fondo desde sus controles.';
    } catch (error) { feedback.textContent = error.message; }
    finally { processing = false; configure(window.GymCultureEditorConfig); }
  });
  use.addEventListener('click', async () => {
    if (!file || !GymCulture3D.canEdit()) return;
    use.disabled = true;
    try {
      await GymCulture3D.prepareImage(file);
      dialog.close();
      document.querySelector('#design-feedback').textContent = 'Tocá la prenda para colocar el diseño generado.';
    } catch (error) { feedback.textContent = error.message; }
    finally { use.disabled = false; }
  });
}
