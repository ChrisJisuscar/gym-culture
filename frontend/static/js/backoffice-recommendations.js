window.GymCultureRecommendations = ({ api, escapeHtml: esc, feedback, fail }) => {
  const host = document.querySelector('#bo-recommendations'), filters = document.querySelector('#recommendation-filters');
  let items = [], cultures = [], saving = false, requestVersion = 0, drag = null;
  const ordered = culture => items.filter(item => item.culture === culture).sort((a, b) => a.sort_order - b.sort_order);
  const visible = culture => {
    const data = new FormData(filters), search = String(data.get('search') || '').toLocaleLowerCase();
    return ordered(culture).filter(item => (!data.get('garment_type') || item.garment_type === data.get('garment_type')) && (!data.get('active') || String(item.active) === data.get('active')) && item.name.toLocaleLowerCase().includes(search));
  };
  const render = (focusId = null) => {
    const cultureFilter = Number(new FormData(filters).get('culture'));
    const groups = cultures.filter(culture => !cultureFilter || culture.id === cultureFilter).map(culture => {
      const rows = visible(culture.id);
      if (!rows.length) return '';
      return `<section class="bo-culture-collection" data-collection="${culture.id}"><header><h2>${esc(culture.name)}</h2><span>${rows.length} diseños</span></header><ol class="bo-recommendation-list" aria-label="Recomendaciones ${esc(culture.name)}">${rows.map((item, index) => `<li class="bo-recommendation-row" data-recommendation-id="${item.id}" data-culture="${culture.id}">
        <button type="button" class="bo-drag-handle" aria-label="Arrastrar ${esc(item.name)}. También podés usar las flechas subir y bajar." title="Arrastrá para ordenar">⠿</button>
        <img class="bo-recommendation-image" src="${esc(item.preview_image_url || '')}" alt="" draggable="false">
        <div class="bo-recommendation-info"><a href="/backoffice/recommendations/${item.id}/edit/">${esc(item.name)}</a><span>${esc(item.garment_label)}</span>${item.featured ? '<small>DESTACADA</small>' : ''}</div>
        <span class="bo-status ${item.active ? 'status-delivered' : 'status-cancelled'}">${item.active ? 'Activa' : 'Inactiva'}</span>
        <div class="bo-order-controls"><button class="bo-button" data-move-recommendation="-1" aria-label="Subir ${esc(item.name)}" ${index === 0 ? 'disabled' : ''}>↑</button><button class="bo-button" data-move-recommendation="1" aria-label="Bajar ${esc(item.name)}" ${index === rows.length - 1 ? 'disabled' : ''}>↓</button></div>
        <div class="bo-action-row"><a class="bo-button" href="/backoffice/recommendations/${item.id}/edit/" data-edit-recommendation="${item.id}">EDITAR</a><button class="bo-button" data-toggle-recommendation="${item.id}" data-active="${item.active}">${item.active ? 'DESACTIVAR' : 'ACTIVAR'}</button><button class="bo-button bo-danger" data-delete-recommendation="${item.id}" aria-label="Eliminar ${esc(item.name)}">×</button></div>
      </li>`).join('')}</ol></section>`;
    });
    host.innerHTML = groups.join('') || '<div class="bo-empty">No hay recomendaciones para estos filtros.</div>';
    host.inert = saving;
    if (focusId) host.querySelector(`[data-recommendation-id="${focusId}"] .bo-drag-handle`)?.focus({ preventScroll: true });
  };
  const load = async () => {
    const version = ++requestVersion;
    const data = await api('/api/backoffice/recommendations/');
    if (version !== requestVersion) return;
    items = data.results; render();
  };
  const persistMove = async (id, targetId, after) => {
    if (saving || id === targetId) return;
    const item = items.find(item => item.id === id), target = items.find(item => item.id === targetId);
    if (!item || !target || target.culture !== item.culture) return;
    const full = ordered(item.culture).map(item => item.id);
    const subset = visible(item.culture).map(item => item.id).filter(value => value !== id);
    subset.splice(subset.indexOf(targetId) + (after ? 1 : 0), 0, id);
    const selected = new Set(subset); let next = 0;
    const updated = full.map(value => selected.has(value) ? subset[next++] : value);
    if (updated.every((value, index) => value === full[index])) return;
    saving = true; host.inert = true; host.setAttribute('aria-busy', 'true');
    feedback.textContent = 'Guardando el nuevo orden…'; feedback.classList.remove('is-error');
    try {
      const result = await api('/api/backoffice/recommendations/reorder/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ culture: item.culture, ordered_ids: updated, expected_order: full }) });
      result.positions.forEach(position => { items.find(item => item.id === position.id).sort_order = position.sort_order; });
      feedback.textContent = `Orden guardado en ${item.culture_name}.`;
    } catch (error) {
      try { await load(); }
      catch (reloadError) {
        fail(new Error(`${error.message} No se pudo actualizar el listado: ${reloadError.message}. Recargá la página antes de volver a ordenar.`));
        return;
      }
      fail(error);
    }
    finally { saving = false; host.removeAttribute('aria-busy'); render(id); }
  };
  const clearDrag = () => {
    if (!drag) return;
    if (drag.handle.hasPointerCapture(drag.pointerId)) drag.handle.releasePointerCapture(drag.pointerId);
    host.querySelectorAll('.is-dragging, .drop-before, .drop-after').forEach(row => row.classList.remove('is-dragging', 'drop-before', 'drop-after'));
    drag = null;
  };
  host.addEventListener('pointerdown', event => {
    const handle = event.target.closest('.bo-drag-handle');
    if (!handle || saving || event.button > 0 || drag) return;
    const row = handle.closest('[data-recommendation-id]');
    drag = { handle, pointerId: event.pointerId, id: Number(row.dataset.recommendationId), culture: row.dataset.culture, startY: event.clientY, moved: false };
    handle.setPointerCapture(event.pointerId); event.preventDefault();
  });
  host.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (Math.abs(event.clientY - drag.startY) < 5 && !drag.moved) return;
    drag.moved = true;
    host.querySelector(`[data-recommendation-id="${drag.id}"]`)?.classList.add('is-dragging');
    host.querySelectorAll('.drop-before, .drop-after').forEach(row => row.classList.remove('drop-before', 'drop-after'));
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-recommendation-id]');
    drag.targetId = null;
    if (target && target.dataset.culture === drag.culture && Number(target.dataset.recommendationId) !== drag.id) {
      drag.targetId = Number(target.dataset.recommendationId);
      const rect = target.getBoundingClientRect(); drag.after = event.clientY > rect.top + rect.height / 2;
      target.classList.add(drag.after ? 'drop-after' : 'drop-before');
    }
    // Native scroll gestures remain available outside the handle. During dragging,
    // pointer movement near the viewport edge advances long collections.
    if (event.clientY < 100) window.scrollBy(0, -24);
    if (event.clientY > innerHeight - 70) window.scrollBy(0, 24);
    event.preventDefault();
  });
  host.addEventListener('pointerup', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const move = { ...drag }; clearDrag();
    if (move.moved && move.targetId) persistMove(move.id, move.targetId, move.after);
  });
  host.addEventListener('pointercancel', clearDrag);
  host.addEventListener('lostpointercapture', () => { if (drag) clearDrag(); });
  window.addEventListener('blur', clearDrag);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') clearDrag(); });
  host.addEventListener('click', async event => {
    if (saving) return;
    const move = event.target.closest('[data-move-recommendation]');
    if (move) {
      const row = move.closest('[data-recommendation-id]'), rows = visible(Number(row.dataset.culture)), index = rows.findIndex(item => item.id === Number(row.dataset.recommendationId)), direction = Number(move.dataset.moveRecommendation);
      if (rows[index + direction]) persistMove(rows[index].id, rows[index + direction].id, direction > 0);
      return;
    }
    const toggle = event.target.closest('[data-toggle-recommendation]'), remove = event.target.closest('[data-delete-recommendation]');
    if (!toggle && !remove) return;
    if (remove && !confirm('¿Eliminar esta recomendación?')) return;
    saving = true; host.inert = true;
    try {
      const id = toggle?.dataset.toggleRecommendation || remove.dataset.deleteRecommendation;
      await api(`/api/backoffice/recommendations/${id}/`, toggle ? { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: toggle.dataset.active !== 'true' }) } : { method: 'DELETE' });
      await load(); feedback.textContent = toggle ? 'Estado actualizado.' : 'Recomendación eliminada.';
    } catch (error) { fail(error); }
    finally { saving = false; host.inert = false; }
  });
  filters.addEventListener('submit', event => { event.preventDefault(); if (!saving) render(); });
  filters.addEventListener('change', () => { if (!saving) render(); });
  document.querySelector('#new-recommendation').addEventListener('click', () => location.assign('/backoffice/recommendations/new/'));
  (async () => {
    cultures = await api('/api/backoffice/recommendations/cultures/');
    document.querySelector('#recommendation-culture-filter').innerHTML = `<option value="">Todas las culturas</option>${cultures.map(culture => `<option value="${culture.id}">${esc(culture.name)}</option>`).join('')}`;
    await load(); feedback.textContent = 'Arrastrá desde ⠿ para ordenar cada cultura. También podés usar las flechas.';
  })().catch(fail);
};
