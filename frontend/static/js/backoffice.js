document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-backoffice-view]');
  if (!root) return;
  const auth = window.GymCultureAuth;
  const feedback = document.querySelector('#bo-feedback');
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const money = (value) => `G ${new Intl.NumberFormat('es-PY', { maximumFractionDigits: 0 }).format(Number(value || 0))}`;
  const date = (value) => new Intl.DateTimeFormat('es-PY', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  const labels = { PENDING: 'Pendiente', CONFIRMED: 'Confirmado', PREPARING: 'En preparación', SHIPPED: 'Enviado', DELIVERED: 'Entregado', CANCELLED: 'Cancelado' };
  const navSection = { 'product-detail': 'products', 'customer-detail': 'customers' }[root.dataset.backofficeView] || root.dataset.backofficeView;
  document.querySelector(`[data-nav-section="${navSection}"]`)?.classList.add('is-active');
  const api = async (url, options = {}) => {
    const response = await auth.request(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(response.status === 403 ? 'No tenés permisos para acceder al backoffice.' : (data.detail || Object.values(data).flat(Infinity).join(' ') || 'No se pudo cargar la información.'));
      error.status = response.status;
      throw error;
    }
    return data;
  };
  const fail = (error) => {
    feedback.textContent = error.message;
    feedback.classList.add('is-error');
    if (error.status === 401) window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
  };
  const status = (value) => `<span class="bo-status status-${value.toLowerCase()}">${escapeHtml(labels[value] || value)}</span>`;
  const rows = (orders) => orders.length ? `<div class="bo-table-wrap"><table class="bo-table"><thead><tr><th>Pedido</th><th>Cliente</th><th>Fecha</th><th>Items</th><th>Total</th><th>Estado</th></tr></thead><tbody>${orders.map((order) => `<tr><td><a href="/backoffice/orders/${order.id}/">${escapeHtml(order.order_number)}</a></td><td>${escapeHtml(order.customer_name || '—')}<small>${escapeHtml(order.customer_email || '')}</small></td><td>${date(order.created_at)}</td><td>${order.item_count}</td><td>${money(order.total)}</td><td>${status(order.status)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">No hay pedidos para mostrar.</div>';

  const loadDashboard = async () => {
    try {
      const data = await api('/api/backoffice/dashboard/');
      feedback.textContent = '';
      document.querySelector('#bo-metrics').innerHTML = [['Pendientes', data.counts.pending], ['Confirmados', data.counts.confirmed], ['En preparación', data.counts.preparing], ['Enviados', data.counts.shipped]].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${value}</strong></article>`).join('');
      document.querySelector('#bo-recent').innerHTML = rows(data.recent_orders);
    } catch (error) { fail(error); }
  };

  const loadOrders = async (url = '/api/backoffice/orders/') => {
    try {
      const data = await api(url);
      feedback.textContent = `${data.count} pedido${data.count === 1 ? '' : 's'}`;
      document.querySelector('#bo-orders').innerHTML = rows(data.results);
      document.querySelector('#bo-pagination').innerHTML = `${data.previous ? `<button data-page="${escapeHtml(data.previous)}">← Anterior</button>` : ''}${data.next ? `<button data-page="${escapeHtml(data.next)}">Siguiente →</button>` : ''}`;
    } catch (error) { fail(error); }
  };

  const designMarkup = (design) => design.type === 'text'
    ? `<li><strong>Texto: “${escapeHtml(design.text)}”</strong><span>${escapeHtml(design.fontFamily)} · ${escapeHtml(design.color)} · ${Number(design.rotation || 0)}°</span></li>`
    : `<li><strong>Diseño gráfico</strong><span>Rotación ${Number(design.rotation || 0)}° · Escala ${Number(design.scale || 1).toFixed(2)}</span></li>`;
  const itemDetail = (item) => {
    const custom = item.customization;
    const previews = custom ? `<div class="bo-previews">${custom.preview_front_url ? `<figure><img src="${escapeHtml(custom.preview_front_url)}" alt="Preview frontal"><figcaption>Frente</figcaption></figure>` : ''}${custom.preview_back_url ? `<figure><img src="${escapeHtml(custom.preview_back_url)}" alt="Preview trasero"><figcaption>Espalda</figcaption></figure>` : ''}</div>` : '';
    const designs = custom?.designs?.length ? `<h4>Configuración</h4><ul class="bo-designs">${custom.designs.map(designMarkup).join('')}</ul>` : '';
    const assets = item.production_assets?.length ? `<h4>Archivos originales</h4><div class="bo-assets">${item.production_assets.map((asset) => `<article><div><strong>${escapeHtml(asset.original_name)}</strong><span>${escapeHtml(asset.mime_type)} · ${asset.width} × ${asset.height} · ${(Number(asset.file_size) / 1048576).toFixed(2)} MB</span></div><button class="bo-button" type="button" data-asset-download="${escapeHtml(asset.download_url)}" data-filename="${escapeHtml(asset.original_name)}">Descargar</button></article>`).join('')}</div>` : '';
    return `<section class="bo-panel bo-order-item"><header><div><h3>${escapeHtml(item.product_name)}</h3>${item.is_customized ? '<em>PERSONALIZADO</em>' : ''}<p>${escapeHtml(item.color || '—')} / ${escapeHtml(item.size || '—')} · ${item.quantity} u.</p></div><strong>${money(item.subtotal)}</strong></header>${previews}${designs}${assets}</section>`;
  };
  const renderDetail = (order) => {
    const transitionOptions = order.allowed_transitions.map((value) => `<option value="${value}">${escapeHtml(labels[value])}</option>`).join('');
    return `<section class="bo-summary-grid"><article class="bo-panel"><small>PEDIDO</small><h2>${escapeHtml(order.order_number)}</h2><p>${date(order.created_at)}</p>${status(order.status)}${transitionOptions ? `<form id="status-form"><select name="status">${transitionOptions}</select><button class="bo-button" type="submit">CAMBIAR ESTADO</button></form>` : '<p>Estado final.</p>'}</article><article class="bo-panel"><small>CLIENTE</small><h3>${escapeHtml(order.customer.first_name)} ${escapeHtml(order.customer.last_name)}</h3><p>${escapeHtml(order.customer.email)}<br>${escapeHtml(order.customer.phone)}</p></article><article class="bo-panel"><small>ENTREGA</small><p>${escapeHtml(order.shipping.address)}<br>${escapeHtml(order.shipping.city)}, ${escapeHtml(order.shipping.department)}<br>${escapeHtml(order.shipping.reference || '')}</p></article><article class="bo-panel"><small>TOTAL</small><h2>${money(order.total)}</h2><p>Pago: ${escapeHtml(order.payment_status_display)}</p></article></section><div class="bo-items">${order.items.map(itemDetail).join('')}</div><section class="bo-panel"><h3>Historial de estados</h3><ol class="bo-history">${order.status_history.length ? order.status_history.map((entry) => `<li><span>${escapeHtml(entry.old_status)} → ${escapeHtml(entry.new_status)}</span><small>${escapeHtml(entry.changed_by)} · ${date(entry.created_at)}</small></li>`).join('') : '<li>Sin cambios registrados.</li>'}</ol></section>`;
  };

  const loadDetail = async () => {
    try {
      const order = await api(`/api/backoffice/orders/${root.dataset.orderId}/`);
      feedback.textContent = '';
      document.querySelector('#bo-order-detail').innerHTML = renderDetail(order);
    } catch (error) { fail(error); }
  };

  const loadProduction = async () => {
    try {
      const orders = await api('/api/backoffice/production/');
      feedback.textContent = '';
      const cards = orders.flatMap((order) => order.items.filter((item) => item.is_customized).map((item) => `<article class="production-card"><header><div><small>${escapeHtml(order.order_number)}</small><h2>${escapeHtml(item.product_name)}</h2></div>${status(order.status)}</header><p>${escapeHtml(item.color)} / ${escapeHtml(item.size)} · Cantidad ${item.quantity}</p><div class="production-previews">${item.customization.preview_front_url ? `<img src="${escapeHtml(item.customization.preview_front_url)}" alt="Frente">` : ''}${item.customization.preview_back_url ? `<img src="${escapeHtml(item.customization.preview_back_url)}" alt="Espalda">` : ''}</div><a class="bo-button" href="/backoffice/orders/${order.id}/">ABRIR PEDIDO</a></article>`));
      document.querySelector('#bo-production').innerHTML = cards.length ? cards.join('') : '<div class="bo-empty">No hay prendas personalizadas pendientes de producción.</div>';
    } catch (error) { fail(error); }
  };

  const categories = async (select, includeAll = false) => {
    const data = await api('/api/backoffice/categories/');
    select.innerHTML = `${includeAll ? '<option value="">Todas las categorías</option>' : '<option value="">Seleccionar categoría</option>'}${data.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}${category.active ? '' : ' (inactiva)'}</option>`).join('')}`;
    return data;
  };
  const productRows = (products) => products.length ? `<div class="bo-table-wrap"><table class="bo-table product-table"><thead><tr><th>Imagen</th><th>Producto</th><th>Categoría</th><th>Precio</th><th>Variantes</th><th>Stock total</th><th>Estado</th></tr></thead><tbody>${products.map((product) => `<tr><td>${product.main_image ? `<img class="bo-thumb" src="${escapeHtml(product.main_image)}" alt="">` : '<span class="bo-thumb bo-thumb-empty">GC</span>'}</td><td><a href="/backoffice/products/${product.id}/">${escapeHtml(product.name)}</a></td><td>${escapeHtml(product.category.name)}</td><td>${money(product.price)}</td><td>${product.variant_count}</td><td>${product.total_stock}</td><td>${product.active ? '<span class="bo-status status-delivered">Activo</span>' : '<span class="bo-status status-cancelled">Inactivo</span>'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">No hay productos para mostrar.</div>';
  const loadProducts = async (url = '/api/backoffice/products/') => {
    try {
      const data = await api(url);
      feedback.textContent = `${data.count} producto${data.count === 1 ? '' : 's'}`;
      document.querySelector('#bo-products').innerHTML = productRows(data.results);
      document.querySelector('#bo-pagination').innerHTML = `${data.previous ? `<button data-product-page="${escapeHtml(data.previous)}">← Anterior</button>` : ''}${data.next ? `<button data-product-page="${escapeHtml(data.next)}">Siguiente →</button>` : ''}`;
    } catch (error) { fail(error); }
  };

  const variantRow = (variant = {}) => `<div class="variant-row" data-variant-id="${variant.id || ''}"><input data-field="size" value="${escapeHtml(variant.size || '')}" placeholder="Talla" maxlength="10" required><input data-field="color" value="${escapeHtml(variant.color || '')}" placeholder="Color" maxlength="50" required><input data-field="stock" value="${Number(variant.stock || 0)}" type="number" min="0" placeholder="Stock" required><label><input data-field="active" type="checkbox" ${variant.active !== false ? 'checked' : ''}> Activa</label>${variant.id ? '' : '<button class="bo-button" type="button" data-remove-variant>QUITAR</button>'}</div>`;
  const loadProductEditor = async () => {
    const form = document.querySelector('#product-form');
    const categorySelect = document.querySelector('#product-category');
    try {
      await categories(categorySelect);
      if (root.dataset.productId) {
        const product = await api(`/api/backoffice/products/${root.dataset.productId}/`);
        document.querySelector('#product-page-title').textContent = product.name;
        form.elements.name.value = product.name;
        form.elements.description.value = product.description;
        form.elements.price.value = product.price;
        form.elements.category.value = product.category.id;
        form.elements.active.checked = product.active;
        document.querySelector('#variant-editor').innerHTML = product.variants.map(variantRow).join('');
        document.querySelector('#product-images').innerHTML = product.images.length ? product.images.map((image) => `<figure><img src="${escapeHtml(image.image)}" alt="Imagen de producto"><figcaption>${image.is_main ? 'Principal' : 'Galería'} <button type="button" data-delete-image="${image.id}">Eliminar</button></figcaption></figure>`).join('') : '<p class="bo-hint">Todavía no hay imágenes.</p>';
      } else {
        document.querySelector('#product-page-title').textContent = 'Nuevo producto';
        document.querySelector('#variant-editor').innerHTML = variantRow();
      }
      feedback.textContent = '';
    } catch (error) { fail(error); }
  };
  const collectVariants = () => [...document.querySelectorAll('.variant-row')].map((row) => ({
    id: row.dataset.variantId || null,
    size: row.querySelector('[data-field="size"]').value,
    color: row.querySelector('[data-field="color"]').value,
    stock: Number(row.querySelector('[data-field="stock"]').value),
    active: row.querySelector('[data-field="active"]').checked,
  }));

  const stockRows = (items) => items.length ? `<div class="bo-table-wrap"><table class="bo-table"><thead><tr><th>Producto</th><th>Color</th><th>Talla</th><th>Stock</th><th>Estado</th><th></th></tr></thead><tbody>${items.map((item) => `<tr><td>${escapeHtml(item.product_name)}</td><td>${escapeHtml(item.color)}</td><td>${escapeHtml(item.size)}</td><td><strong>${item.stock}</strong></td><td><span class="stock-state stock-${item.stock_status.toLowerCase()}">${item.stock_status === 'OUT' ? 'Sin stock' : item.stock_status === 'LOW' ? 'Bajo' : 'Normal'}</span></td><td><button class="bo-button" type="button" data-adjust-stock="${item.id}" data-variant-name="${escapeHtml(`${item.product_name} / ${item.color} / ${item.size}`)}">AJUSTAR</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">No hay variantes para mostrar.</div>';
  const loadStock = async (url = '/api/backoffice/stock/') => {
    try {
      const data = await api(url);
      feedback.textContent = `${data.count} variante${data.count === 1 ? '' : 's'}`;
      document.querySelector('#bo-stock').innerHTML = stockRows(data.results);
      document.querySelector('#bo-pagination').innerHTML = `${data.previous ? `<button data-stock-page="${escapeHtml(data.previous)}">← Anterior</button>` : ''}${data.next ? `<button data-stock-page="${escapeHtml(data.next)}">Siguiente →</button>` : ''}`;
    } catch (error) { fail(error); }
  };
  const loadStockHistory = async () => {
    try {
      const data = await api('/api/backoffice/stock/history/?page_size=20');
      document.querySelector('#stock-history').innerHTML = data.results.length ? `<div class="bo-table-wrap"><table class="bo-table"><thead><tr><th>Fecha</th><th>Producto</th><th>Tipo</th><th>Cambio</th><th>Motivo</th><th>Usuario</th></tr></thead><tbody>${data.results.map((movement) => `<tr><td>${date(movement.created_at)}</td><td>${escapeHtml(movement.product_name)}<small>${escapeHtml(movement.color)} / ${escapeHtml(movement.size)}</small></td><td>${escapeHtml(movement.movement_type)}</td><td>${movement.previous_stock} → ${movement.new_stock}</td><td>${escapeHtml(movement.reason)}</td><td>${escapeHtml(movement.performed_by)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">Todavía no hay movimientos.</div>';
    } catch (error) { fail(error); }
  };

  const customerRows = (customers) => customers.length ? `<div class="bo-table-wrap"><table class="bo-table"><thead><tr><th>Cliente</th><th>Email</th><th>Registro</th><th>Pedidos</th><th>Último pedido</th><th>Estado</th></tr></thead><tbody>${customers.map((customer) => `<tr><td><a href="/backoffice/customers/${customer.id}/">${escapeHtml(`${customer.first_name} ${customer.last_name}`.trim() || customer.username)}</a></td><td>${escapeHtml(customer.email)}</td><td>${date(customer.date_joined)}</td><td>${customer.order_count}</td><td>${customer.last_order_at ? date(customer.last_order_at) : '—'}</td><td>${customer.is_active ? '<span class="bo-status status-delivered">Activo</span>' : '<span class="bo-status status-cancelled">Inactivo</span>'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">No hay clientes para mostrar.</div>';
  const loadCustomers = async (url = '/api/backoffice/customers/') => {
    try {
      const data = await api(url);
      feedback.textContent = `${data.count} cliente${data.count === 1 ? '' : 's'}`;
      document.querySelector('#bo-customers').innerHTML = customerRows(data.results);
      document.querySelector('#bo-pagination').innerHTML = `${data.previous ? `<button data-customer-page="${escapeHtml(data.previous)}">← Anterior</button>` : ''}${data.next ? `<button data-customer-page="${escapeHtml(data.next)}">Siguiente →</button>` : ''}`;
    } catch (error) { fail(error); }
  };
  const loadCustomerDetail = async () => {
    try {
      const customer = await api(`/api/backoffice/customers/${root.dataset.customerId}/`);
      feedback.textContent = '';
      document.querySelector('#bo-customer-detail').innerHTML = `<section class="bo-summary-grid customer-summary"><article class="bo-panel"><small>CLIENTE</small><h2>${escapeHtml(`${customer.first_name} ${customer.last_name}`.trim() || customer.username)}</h2><p>${escapeHtml(customer.email)}</p></article><article class="bo-panel"><small>ESTADO</small><h2>${customer.is_active ? 'Activo' : 'Inactivo'}</h2><p>Desde ${date(customer.date_joined)}</p></article><article class="bo-panel"><small>PEDIDOS</small><h2>${customer.order_count}</h2><p>Último: ${customer.last_order_at ? date(customer.last_order_at) : '—'}</p></article><article class="bo-panel"><small>TOTAL COMPRADO</small><h2>${money(customer.total_spent)}</h2><p>Excluye pedidos cancelados</p></article></section><section class="bo-panel"><h2>Historial de pedidos</h2>${customer.orders.length ? `<div class="bo-table-wrap"><table class="bo-table"><thead><tr><th>Pedido</th><th>Fecha</th><th>Items</th><th>Total</th><th>Estado</th></tr></thead><tbody>${customer.orders.map((order) => `<tr><td><a href="/backoffice/orders/${order.id}/">${escapeHtml(order.order_number)}</a></td><td>${date(order.created_at)}</td><td>${order.item_count}</td><td>${money(order.total)}</td><td>${status(order.status)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="bo-empty">Este cliente todavía no tiene pedidos.</div>'}</section>`;
    } catch (error) { fail(error); }
  };

  document.addEventListener('submit', async (event) => {
    if (event.target.id === 'bo-filters') {
      event.preventDefault();
      const params = new URLSearchParams(new FormData(event.target));
      [...params.keys()].forEach((key) => { if (!params.get(key)) params.delete(key); });
      loadOrders(`/api/backoffice/orders/?${params}`);
    }
    if (event.target.id === 'status-form') {
      event.preventDefault();
      try {
        await api(`/api/backoffice/orders/${root.dataset.orderId}/status/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
        loadDetail();
      } catch (error) { fail(error); }
    }
    if (event.target.id === 'product-filters' || event.target.id === 'stock-filters' || event.target.id === 'customer-filters') {
      event.preventDefault();
      const params = new URLSearchParams(new FormData(event.target));
      [...params.keys()].forEach((key) => { if (!params.get(key)) params.delete(key); });
      if (event.target.id === 'product-filters') loadProducts(`/api/backoffice/products/?${params}`);
      if (event.target.id === 'stock-filters') loadStock(`/api/backoffice/stock/?${params}`);
      if (event.target.id === 'customer-filters') loadCustomers(`/api/backoffice/customers/?${params}`);
    }
    if (event.target.id === 'product-form') {
      event.preventDefault();
      const button = document.querySelector('#save-product');
      button.disabled = true;
      button.textContent = 'GUARDANDO…';
      try {
        const form = new FormData(event.target);
        form.set('active', String(event.target.elements.active.checked));
        form.set('variants', JSON.stringify(collectVariants()));
        const product = await api(root.dataset.productId ? `/api/backoffice/products/${root.dataset.productId}/` : '/api/backoffice/products/', { method: root.dataset.productId ? 'PATCH' : 'POST', body: form });
        feedback.textContent = 'Producto guardado correctamente.';
        feedback.classList.remove('is-error');
        if (!root.dataset.productId) window.location.assign(`/backoffice/products/${product.id}/`);
        else loadProductEditor();
      } catch (error) { fail(error); }
      finally { button.disabled = false; button.textContent = 'GUARDAR PRODUCTO'; }
    }
    if (event.target.id === 'stock-adjust-form') {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(event.target));
      const variantId = payload.variant_id; delete payload.variant_id;
      payload.quantity = Number(payload.quantity);
      try {
        await api(`/api/backoffice/stock/${variantId}/adjust/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        document.querySelector('#stock-dialog').close();
        feedback.textContent = 'Stock actualizado y movimiento registrado.';
        feedback.classList.remove('is-error');
        loadStock(); loadStockHistory();
      } catch (error) { fail(error); }
    }
  });
  document.addEventListener('click', async (event) => {
    const page = event.target.closest('[data-page]');
    if (page) loadOrders(page.dataset.page);
    const download = event.target.closest('[data-asset-download]');
    if (download) {
      try {
        const response = await auth.request(download.dataset.assetDownload);
        if (!response.ok) throw new Error('No se pudo descargar el archivo.');
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url; link.download = download.dataset.filename; link.click();
        URL.revokeObjectURL(url);
      } catch (error) { fail(error); }
    }
    if (event.target.closest('[data-product-page]')) loadProducts(event.target.closest('[data-product-page]').dataset.productPage);
    if (event.target.closest('[data-stock-page]')) loadStock(event.target.closest('[data-stock-page]').dataset.stockPage);
    if (event.target.closest('[data-customer-page]')) loadCustomers(event.target.closest('[data-customer-page]').dataset.customerPage);
    if (event.target.closest('#add-variant')) document.querySelector('#variant-editor').insertAdjacentHTML('beforeend', variantRow());
    if (event.target.closest('[data-remove-variant]')) event.target.closest('.variant-row').remove();
    const imageDelete = event.target.closest('[data-delete-image]');
    if (imageDelete) {
      try { await api(`/api/backoffice/products/${root.dataset.productId}/images/${imageDelete.dataset.deleteImage}/`, { method: 'DELETE' }); loadProductEditor(); }
      catch (error) { fail(error); }
    }
    if (event.target.closest('#create-category')) {
      const name = document.querySelector('#new-category-name').value.trim();
      if (!name) return;
      try { const created = await api('/api/backoffice/categories/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description: '', active: true }) }); await categories(document.querySelector('#product-category')); document.querySelector('#product-category').value = created.id; }
      catch (error) { fail(error); }
    }
    const adjust = event.target.closest('[data-adjust-stock]');
    if (adjust) {
      const dialog = document.querySelector('#stock-dialog');
      dialog.querySelector('[name="variant_id"]').value = adjust.dataset.adjustStock;
      document.querySelector('#stock-dialog-title').textContent = adjust.dataset.variantName;
      dialog.showModal();
    }
    if (event.target.closest('#refresh-history')) loadStockHistory();
  });

  if (root.dataset.backofficeView === 'dashboard') loadDashboard();
  if (root.dataset.backofficeView === 'orders') loadOrders();
  if (root.dataset.backofficeView === 'detail') loadDetail();
  if (root.dataset.backofficeView === 'production') loadProduction();
  if (root.dataset.backofficeView === 'products') { categories(document.querySelector('#product-category-filter'), true).catch(fail); loadProducts(); }
  if (root.dataset.backofficeView === 'product-detail') loadProductEditor();
  if (root.dataset.backofficeView === 'stock') { loadStock(); loadStockHistory(); }
  if (root.dataset.backofficeView === 'customers') loadCustomers();
  if (root.dataset.backofficeView === 'customer-detail') loadCustomerDetail();
});
