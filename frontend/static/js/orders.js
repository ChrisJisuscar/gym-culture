document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-order-view]');
  if (!root) return;
  const auth = window.GymCultureAuth;
  const debug = root.dataset.debug === 'true';
  const hasSession = localStorage.getItem('gc_access_token') || localStorage.getItem('gc_refresh_token');
  if (!hasSession) {
    window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
    return;
  }

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[character]));
  const money = (value) => `G ${new Intl.NumberFormat('es-PY', { maximumFractionDigits: 0 }).format(Number(value || 0))}`;
  const date = (value) => new Intl.DateTimeFormat('es-PY', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  const fieldErrors = (value) => {
    if (Array.isArray(value)) return value.flatMap(fieldErrors);
    if (value && typeof value === 'object') return Object.values(value).flatMap(fieldErrors);
    return value == null ? [] : [String(value)];
  };
  const parseResponse = async (response) => {
    const body = await response.text();
    if (!body) return {};
    try { return JSON.parse(body); }
    catch {
      if (debug && response.status >= 500) console.error('Checkout API response', response.status, body.slice(0, 2000));
      return {};
    }
  };
  const api = async (url, options = {}) => {
    let response;
    try {
      response = await auth.request(url, options);
    } catch (error) {
      if (auth.isSessionError?.(error)) {
        setTimeout(() => auth.redirectToLogin(), 900);
        throw error;
      }
      throw new Error('No se pudo conectar con el servidor. Intentá nuevamente.');
    }
    const data = await parseResponse(response);
    if (!response.ok) {
      const validationMessage = fieldErrors(data).join(' ');
      const messages = {
        401: 'Tu sesión expiró. Inicia sesión nuevamente para continuar.',
        403: 'No tienes permisos para realizar esta operación.',
        409: validationMessage || 'La operación entra en conflicto con un intento anterior.',
      };
      const message = messages[response.status]
        || (response.status >= 500
          ? 'Ocurrió un error interno. Intentá nuevamente.'
          : data.detail || validationMessage || `No se pudo completar la operación (${response.status}).`);
      if (debug && response.status >= 500) console.error('Checkout API error', { url, status: response.status, data });
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  };
  const itemMarkup = (item) => {
    const custom = item.customization;
    const previews = custom ? `<div class="order-previews">${custom.preview_front_url ? `<figure><img src="${escapeHtml(custom.preview_front_url)}" alt="Vista frontal"><figcaption>Frente</figcaption></figure>` : ''}${custom.preview_back_url ? `<figure><img src="${escapeHtml(custom.preview_back_url)}" alt="Vista trasera"><figcaption>Espalda</figcaption></figure>` : ''}</div>` : '';
    return `<article class="order-line"><div><h3>${escapeHtml(item.product_name)}</h3>${availabilityMarkup(item)}${item.is_customized ? '<span class="customized-label">PERSONALIZADO</span>' : ''}<p>${escapeHtml(item.color || 'Sin color')} / ${escapeHtml(item.size || 'Sin talla')} · Cantidad ${item.quantity}</p></div><strong>${money(item.subtotal)}</strong>${previews}</article>`;
  };
  const paymentsMarkup = (order) => {
    const attempts = order.payments?.map((payment) => `<li><strong>${escapeHtml(payment.status_display)}</strong><span>${money(payment.amount)} ${escapeHtml(payment.currency)} · ${escapeHtml(payment.provider)}${payment.payment_method ? ` · ${escapeHtml(payment.payment_method)}` : ''}</span>${payment.can_simulate && ['PENDING', 'PROCESSING'].includes(payment.status) ? `<div class="mock-payment-actions"><button type="button" data-mock-payment="${payment.id}" data-outcome="approved">Simular aprobación</button><button type="button" data-mock-payment="${payment.id}" data-outcome="rejected">Simular rechazo</button><button type="button" data-mock-payment="${payment.id}" data-outcome="pending">Mantener pendiente</button></div>` : ''}</li>`).join('');
    return `<section class="payment-summary"><h3>Pago</h3><p>Estado: <strong>${escapeHtml(order.payment_status_display)}</strong></p>${attempts ? `<ul>${attempts}</ul>` : '<p>No hay intentos de pago.</p>'}</section>`;
  };
  const availabilityMarkup = (item) => item.availability === "AWAITING_STOCK" ? '<p class="stock-warning">PENDIENTE DE STOCK. La disponibilidad se gestionara antes de produccion.</p>' : "";
  const detailMarkup = (order) => `<section class="order-card order-detail-card"><div class="order-number-row"><div><small>NÚMERO</small><h2>${escapeHtml(order.order_number)}</h2></div><span class="status-pill status-${order.status.toLowerCase()}">${escapeHtml(order.status_display)}</span></div><p class="order-date">${date(order.created_at)}</p><div class="order-lines">${order.items.map(itemMarkup).join('')}</div><dl class="checkout-totals"><div><dt>Subtotal</dt><dd>${money(order.subtotal)}</dd></div><div><dt>Envío</dt><dd>${money(order.shipping_cost)}</dd></div><div class="total"><dt>Total</dt><dd>${money(order.total)}</dd></div></dl>${availabilityMarkup(order)}${paymentsMarkup(order)}</section>`;

  const loadCheckout = async () => {
    const form = document.querySelector('#checkout-form');
    const feedback = document.querySelector('#checkout-feedback');
    try {
      const [cart, profile] = await Promise.all([api('/api/cart/'), api('/api/auth/me/')]);
      if (!cart.items.length) {
        document.querySelector('#checkout-items').innerHTML = '<p>Tu carrito está vacío.</p>';
        document.querySelector('#confirm-order').disabled = true;
        return;
      }
      document.querySelector('#checkout-items').innerHTML = cart.items.map((item) => `<article><div><strong>${escapeHtml(item.product_name)}</strong><small>${escapeHtml(item.variant_color || '')} / ${escapeHtml(item.variant_size || '')} · ${item.quantity} u.</small>${availabilityMarkup(item)}${item.is_customized ? '<em>PERSONALIZADO</em>' : ''}</div><b>${money(item.subtotal)}</b></article>`).join('');
      document.querySelector('#checkout-subtotal').textContent = money(cart.subtotal);
      document.querySelector('#checkout-total').textContent = money(cart.subtotal);
      form.elements.first_name.value = profile.first_name || '';
      form.elements.last_name.value = profile.last_name || '';
      form.elements.email.value = profile.email || '';
    } catch (error) {
      feedback.textContent = error.message;
      feedback.classList.add('is-error');
      return;
    }
    let key = sessionStorage.getItem('gc_checkout_key');
    if (!key) {
      key = crypto.randomUUID?.() || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (token) => {
        const random = Math.floor(Math.random() * 16);
        return (token === 'x' ? random : (random & 3) | 8).toString(16);
      });
      sessionStorage.setItem('gc_checkout_key', key);
    }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = document.querySelector('#confirm-order');
      button.disabled = true;
      button.textContent = 'CONFIRMANDO…';
      feedback.textContent = '';
      feedback.classList.remove('is-error');
      try {
        const payload = Object.fromEntries(new FormData(form).entries());
        payload.idempotency_key = key;
        const order = await api('/api/orders/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!order.id || !order.order_number || (payload.payment_provider && !order.payment?.id)) {
          throw new Error('El servidor no devolvió la confirmación completa del pedido. Intentá nuevamente.');
        }
        sessionStorage.removeItem('gc_checkout_key');
        window.location.assign(`/pedido/${encodeURIComponent(order.order_number)}/confirmacion/`);
      } catch (error) {
        feedback.textContent = error.message;
        feedback.classList.add('is-error');
        button.disabled = false;
        button.textContent = 'CONFIRMAR PEDIDO';
      }
    });
  };

  const loadList = async () => {
    const container = document.querySelector('#orders-list');
    try {
      const orders = await api('/api/orders/');
      container.innerHTML = orders.length ? orders.map((order) => `<a class="order-list-row" href="/mis-pedidos/${order.id}/"><div><small>${date(order.created_at)}</small><h2>${escapeHtml(order.order_number)}</h2><small>Pago: ${escapeHtml(order.payment_status_display)}</small></div><span>${order.item_count} item${order.item_count === 1 ? '' : 's'}</span><b>${money(order.total)}</b><em class="status-pill status-${order.status.toLowerCase()}">${escapeHtml(order.status_display)}</em></a>`).join('') : '<div class="order-card empty-order"><h2>Todavía no tenés pedidos</h2><p>Cuando confirmes una compra aparecerá acá.</p><a class="button button-accent" href="/">IR A LA TIENDA</a></div>';
    } catch (error) { container.innerHTML = `<p class="order-feedback is-error">${escapeHtml(error.message)}</p>`; }
  };

  const loadDetail = async (url) => {
    const container = document.querySelector('#order-content');
    try { container.innerHTML = detailMarkup(await api(url)); }
    catch (error) { container.innerHTML = `<p class="order-feedback is-error">${escapeHtml(error.message)}</p>`; }
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-mock-payment]');
    if (!button) return;
    button.disabled = true;
    try {
      await api(`/api/payments/${button.dataset.mockPayment}/mock/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outcome: button.dataset.outcome }),
      });
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      window.alert(error.message);
    }
  });

  if (root.dataset.orderView === 'checkout') loadCheckout();
  if (root.dataset.orderView === 'list') loadList();
  if (root.dataset.orderView === 'detail') loadDetail(`/api/orders/${root.dataset.orderId}/`);
  if (root.dataset.orderView === 'confirmation') loadDetail(`/api/orders/by-number/${encodeURIComponent(root.dataset.orderNumber)}/`);
});
