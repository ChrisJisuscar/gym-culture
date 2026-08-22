document.addEventListener('DOMContentLoaded', () => {
  const authApi = window.GymCultureAuth;
  const cartItemsContainer = document.querySelector('#cart-items-container');
  const subtotalEl = document.querySelector('#cart-subtotal');
  const countEl = document.querySelector('#cart-item-count');
  const cartBadge = document.querySelector('#cart-count-badge');

  const formatMoney = (value) => `G ${new Intl.NumberFormat('es-PY', {
    maximumFractionDigits: 0,
  }).format(Number(value || 0))}`;

  const updateCartBadge = (count) => {
    if (cartBadge) {
      cartBadge.textContent = count || '0';
    }
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[character]));

  const loginDestination = () => `/login/?next=${encodeURIComponent(window.location.pathname + window.location.search + window.location.hash)}`;

  const renderEmptyState = (message = 'Entrá a GYM CULTURE para guardar tus prendas.', action = { href: loginDestination(), label: 'Iniciar sesión' }) => {
    if (!cartItemsContainer) return;
    cartItemsContainer.innerHTML = `
      <div class="cart-empty">
        <h3>Tu carrito está vacío</h3>
        <p>${escapeHtml(message)}</p>
        <a class="button button-accent" href="${action.href}">${escapeHtml(action.label)}</a>
      </div>
    `;
  };

  const renderCart = (cart) => {
    const items = cart?.items || [];
    updateCartBadge(cart?.item_count || 0);
    if (!cartItemsContainer) return;

    if (countEl) countEl.textContent = cart?.item_count || 0;
    if (subtotalEl) subtotalEl.textContent = formatMoney(cart?.subtotal || 0);

    if (!items.length) {
      renderEmptyState(
        'Entrá a la tienda para elegir tus prendas.',
        { href: '/', label: 'Ir a la tienda' }
      );
      return;
    }

    cartItemsContainer.innerHTML = items.map((item) => {
      const editHref = `/crear-mi-remera/?edit_cart_item=${encodeURIComponent(item.id)}`;
      const imageMarkup = item.is_customized && item.preview_front
        ? `<a class="cart-preview-link" href="${editHref}" aria-label="Editar diseño de ${escapeHtml(item.product_name)}"><img class="cart-preview-front" src="${escapeHtml(item.preview_front)}" alt="Preview de ${escapeHtml(item.product_name)} personalizada">${item.preview_back ? `<img class="cart-preview-back" src="${escapeHtml(item.preview_back)}" alt="Preview trasera de ${escapeHtml(item.product_name)} personalizada" hidden>` : ''}</a>`
        : (
          item.product_image
            ? `<img src="${escapeHtml(item.product_image)}" alt="${escapeHtml(item.product_name)}">`
            : '<span>GC</span>'
        );
      return `
      <article class="cart-item" data-item-id="${item.id}">
        <div class="cart-item-image">
          ${imageMarkup}
        </div>
        <div class="cart-item-body">
          <div class="cart-item-header">
            <div>
              <h3>${escapeHtml(item.product_name)}</h3>
              ${item.is_customized ? '<span class="customized-label">PERSONALIZADA</span>' : ''}
              <p>${item.variant_size ? 'Talle ' + escapeHtml(item.variant_size) : 'Sin variante'} / ${item.variant_color ? escapeHtml(item.variant_color) : 'Sin color'}</p>
            </div>
            <button class="cart-remove" type="button" data-remove-item="${item.id}">Eliminar</button>
          </div>
          <div class="cart-item-meta">
            <div class="quantity-control-group">
              <span class="quantity-label">Cantidad</span>
              <div class="qty-controls">
              <button type="button" data-qty-change="decrement" data-item-id="${item.id}" ${Number(item.quantity) <= 1 ? 'disabled' : ''}>-</button>
              <span>${item.quantity}</span>
              <button type="button" data-qty-change="increment" data-item-id="${item.id}">+</button>
              </div>
            </div>
            <div class="cart-prices"><span>${formatMoney(item.product_price)} c/u</span><strong>${formatMoney(Number(item.product_price) * Number(item.quantity))}</strong>${item.is_customized ? `<div class="cart-item-actions"><a class="cart-edit" href="${editHref}">Editar diseño</a>${item.preview_back ? `<button class="cart-edit" type="button" data-preview-toggle="${item.id}">Ver espalda</button>` : ''}</div>` : ''}</div>
          </div>
        </div>
      </article>
    `;
    }).join('');
  };

  const loadCart = async () => {
    if (!authApi || !authApi.request) {
      renderEmptyState();
      return;
    }

    if (!localStorage.getItem('gc_access_token') && !localStorage.getItem('gc_refresh_token')) {
      updateCartBadge(0);
      renderEmptyState('Necesitás iniciar sesión para ver tu carrito.');
      return;
    }

    try {
      const response = await authApi.request('/api/cart/', { method: 'GET' });
      if (response.status === 401) {
        updateCartBadge(0);
        renderEmptyState('Necesitás iniciar sesión para ver tu carrito.');
        return;
      }
      if (!response.ok) {
        throw new Error('No se pudo cargar el carrito.');
      }
      const cart = await response.json();
      renderCart(cart);
    } catch (error) {
      console.error(error);
      renderEmptyState('No pudimos cargar tu carrito. Intentá de nuevo.');
    }
  };

  document.addEventListener('gymculture:cart-changed', loadCart);

  const changeQuantity = async (itemId, finalQuantity) => {
    if (!authApi || !authApi.request) return;
    const response = await authApi.request(`/api/cart/items/${itemId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity: finalQuantity })
    });
    if (response.ok) {
      loadCart();
    }
  };

  const removeItem = async (itemId) => {
    if (!authApi || !authApi.request) return;
    const response = await authApi.request(`/api/cart/items/${itemId}/`, {
      method: 'DELETE'
    });
    if (response.ok) {
      loadCart();
    }
  };

  document.addEventListener('click', async (event) => {
    const removeButton = event.target.closest('[data-remove-item]');
    if (removeButton) {
      await removeItem(Number(removeButton.dataset.removeItem));
      return;
    }

    const qtyButton = event.target.closest('[data-qty-change]');
    if (qtyButton) {
      const itemId = Number(qtyButton.dataset.itemId);
      const delta = qtyButton.dataset.qtyChange === 'increment' ? 1 : -1;
      const container = qtyButton.closest('.cart-item');
      const currentValue = Number(container?.querySelector('.qty-controls span')?.textContent || 0);
      const finalQuantity = currentValue + delta;
      if (!Number.isInteger(currentValue) || finalQuantity < 1) {
        return;
      }
      await changeQuantity(itemId, finalQuantity);
      return;
    }

    const previewToggle = event.target.closest('[data-preview-toggle]');
    if (previewToggle) {
      const item = previewToggle.closest('.cart-item');
      const front = item?.querySelector('.cart-preview-front');
      const back = item?.querySelector('.cart-preview-back');
      const showingBack = !back?.hidden;
      if (front && back) {
        front.hidden = !showingBack;
        back.hidden = showingBack;
        previewToggle.textContent = showingBack ? 'Ver espalda' : 'Ver frente';
      }
    }
  });

  loadCart();
});
