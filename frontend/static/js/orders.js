document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-order-view]');
  if (!root) return;
  const auth = window.GymCultureAuth;
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
  const api = async (url, options = {}) => {
    const response = await auth.request(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.detail || Object.values(data).flat(Infinity).join(' ') || 'No se pudo completar la operación.';
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  };
  const itemMarkup = (item) => {
    const custom = item.customization;
    const previews = custom ? `<div class="order-previews">${custom.preview_front_url ? `<figure><img src="${escapeHtml(custom.preview_front_url)}" alt="Vista frontal"><figcaption>Frente</figcaption></figure>` : ''}${custom.preview_back_url ? `<figure><img src="${escapeHtml(custom.preview_back_url)}" alt="Vista trasera"><figcaption>Espalda</figcaption></figure>` : ''}</div>` : '';
    return `<article class="order-line"><div><h3>${escapeHtml(item.product_name)}</h3>${item.is_customized ? '<span class="customized-label">PERSONALIZADO</span>' : ''}<p>${escapeHtml(item.color || 'Sin color')} / ${escapeHtml(item.size || 'Sin talla')} · Cantidad ${item.quantity}</p></div><strong>${money(item.subtotal)}</strong>${previews}</article>`;
  };
  const detailMarkup = (order) => `<section class="order-card order-detail-card"><div class="order-number-row"><div><small>NÚMERO</small><h2>${escapeHtml(order.order_number)}</h2></div><span class="status-pill status-${order.status.toLowerCase()}">${escapeHtml(order.status_display)}</span></div><p class="order-date">${date(order.created_at)}</p><div class="order-lines">${order.items.map(itemMarkup).join('')}</div><dl class="checkout-totals"><div><dt>Subtotal</dt><dd>${money(order.subtotal)}</dd></div><div><dt>Envío</dt><dd>${money(order.shipping_cost)}</dd></div><div class="total"><dt>Total</dt><dd>${money(order.total)}</dd></div></dl><p class="payment-note">Pago: ${escapeHtml(order.payment_status_display)}</p></section>`;

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
      document.querySelector('#checkout-items').innerHTML = cart.items.map((item) => `<article><div><strong>${escapeHtml(item.product_name)}</strong><small>${escapeHtml(item.variant_color || '')} / ${escapeHtml(item.variant_size || '')} · ${item.quantity} u.</small>${item.is_customized ? '<em>PERSONALIZADO</em>' : ''}</div><b>${money(item.subtotal)}</b></article>`).join('');
      document.querySelector('#checkout-subtotal').textContent = money(cart.subtotal);
      document.querySelector('#checkout-total').textContent = money(cart.subtotal);
      form.elements.first_name.value = profile.first_name || profile.username || '';
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
      container.innerHTML = orders.length ? orders.map((order) => `<a class="order-list-row" href="/mis-pedidos/${order.id}/"><div><small>${date(order.created_at)}</small><h2>${escapeHtml(order.order_number)}</h2></div><span>${order.item_count} item${order.item_count === 1 ? '' : 's'}</span><b>${money(order.total)}</b><em class="status-pill status-${order.status.toLowerCase()}">${escapeHtml(order.status_display)}</em></a>`).join('') : '<div class="order-card empty-order"><h2>Todavía no tenés pedidos</h2><p>Cuando confirmes una compra aparecerá acá.</p><a class="button button-accent" href="/">IR A LA TIENDA</a></div>';
    } catch (error) { container.innerHTML = `<p class="order-feedback is-error">${escapeHtml(error.message)}</p>`; }
  };

  const loadDetail = async (url) => {
    const container = document.querySelector('#order-content');
    try { container.innerHTML = detailMarkup(await api(url)); }
    catch (error) { container.innerHTML = `<p class="order-feedback is-error">${escapeHtml(error.message)}</p>`; }
  };

  if (root.dataset.orderView === 'checkout') loadCheckout();
  if (root.dataset.orderView === 'list') loadList();
  if (root.dataset.orderView === 'detail') loadDetail(`/api/orders/${root.dataset.orderId}/`);
  if (root.dataset.orderView === 'confirmation') loadDetail(`/api/orders/by-number/${encodeURIComponent(root.dataset.orderNumber)}/`);
});
