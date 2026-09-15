(() => {
  const dialog = document.querySelector('#background-preview-dialog');
  if (!dialog) return;
  const controls = dialog.querySelectorAll('[data-background-view]');
  const setView = view => {
    dialog.classList.toggle('is-native', view === 'native');
    controls.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.backgroundView === view)));
    dialog.querySelectorAll('.transparency-grid').forEach(panel => { panel.scrollLeft = panel.scrollTop = 0; });
  };
  controls.forEach(button => button.addEventListener('click', () => setView(button.dataset.backgroundView)));
  dialog.addEventListener('close', () => setView('fit'));
  dialog.querySelectorAll('.transparency-grid').forEach(panel => {
    let drag = null;
    panel.addEventListener('pointerdown', event => {
      if (!dialog.classList.contains('is-native') || event.pointerType !== 'mouse' || event.button !== 0) return;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: panel.scrollLeft, top: panel.scrollTop };
      panel.setPointerCapture(event.pointerId); event.preventDefault();
    });
    panel.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      panel.scrollLeft = drag.left + drag.x - event.clientX;
      panel.scrollTop = drag.top + drag.y - event.clientY;
    });
    const release = () => { drag = null; };
    panel.addEventListener('pointerup', release);
    panel.addEventListener('pointercancel', release);
    panel.addEventListener('lostpointercapture', release);
    dialog.addEventListener('close', release);
  });
})();
