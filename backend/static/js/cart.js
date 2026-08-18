document.addEventListener('DOMContentLoaded', () => {
  const authApi = window.GymCultureAuth;
  const cartItemsContainer = document.querySelector('#cart-items-container');
  const subtotalEl = document.querySelector('#cart-subtotal');
  const countEl = document.querySelector('#cart-item-count');
  const cartBadge = document.querySelector('#cart-count-badge');

  const formatMoney = (value) => new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(Number(value || 0));

  const renderEmptyState = () => {
    if (!cartItemsContainer) return;
    cartItemsContainer.innerHTML = `
      <div class="cart-empty">
        <h3>Tu carrito está vacío</h3>
        <p>Entrá a GYM CULTURE para guardar tus prendas.</p>
        <a class="button button-accent" href="/">Ir a la tienda</a>
      </div>
    `;
  };

  const updateCartBadge = (count) => {
    if (cartBadge) {
      cartBadge.textContent = count || '0';
    }
  };

  const renderCart = (cart) => {
    if (!cartItemsContainer) return;

    const items = cart?.items || [];
    updateCartBadge(cart?.item_count || 0);
    if (countEl) countEl.textContent = cart?.item_count || 0;
    if (subtotalEl) subtotalEl.textContent = formatMoney(cart?.subtotal || 0);

    if (!items.length) {
      renderEmptyState();
      return;
    }

    cartItemsContainer.innerHTML = items.map((item) => `
      <article class="cart-item" data-item-id="${item.id}">
        <div class="cart-item-image">
          <span>GC</span>
        </div>
        <div class="cart-item-body">
          <div class="cart-item-header">
            <div>
              <h3>${item.product_name}</h3>
              <p>${item.variant_size ? 'Talle ' + item.variant_size : 'Sin variante'} / ${item.variant_color ? item.variant_color : 'Sin color'}</p>
            </div>
            <button class="cart-remove" type="button" data-remove-item="${item.id}">Eliminar</button>
          </div>
          <div class="cart-item-meta">
            <div class="qty-controls">
              <button type="button" data-qty-change="decrement" data-item-id="${item.id}">-</button>
              <span>${item.quantity}</span>
              <button type="button" data-qty-change="increment" data-item-id="${item.id}">+</button>
            </div>
            <strong>${formatMoney(Number(item.product_price) * Number(item.quantity))}</strong>
          </div>
        </div>
      </article>
    `).join('');
  };

  const loadCart = async () => {
    if (!authApi || !authApi.request) {
      renderEmptyState();
      return;
    }

    try {
      const response = await authApi.request('/api/cart/', { method: 'GET' });
      if (response.status === 401) {
        renderEmptyState();
        return;
      }
      if (!response.ok) {
        throw new Error('No se pudo cargar el carrito.');
      }
      const cart = await response.json();
      renderCart(cart);
    } catch (error) {
      renderEmptyState();
    }
  };

  const changeQuantity = async (itemId, delta) => {
    if (!authApi || !authApi.request) return;
    const response = await authApi.request(`/api/cart/items/${itemId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity: delta })
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
      const currentValue = Number(container?.querySelector('span')?.textContent || 0);
      if (currentValue + delta <= 0) {
        await removeItem(itemId);
        return;
      }
      await changeQuantity(itemId, currentValue + delta);
    }
  });

  if (cartItemsContainer) {
    loadCart();
  }
});
