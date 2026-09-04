const customizerRoot = document.querySelector('.customizer-layout');

if (customizerRoot) {
  const variantsElement = document.querySelector('#product-variants');
  const variants = variantsElement ? JSON.parse(variantsElement.textContent) : [];
  const basePrice = Number(customizerRoot.dataset.price) || 89000;
  const customizerState = {
    garmentType: 'tshirt',
    garmentColor: 'Negro',
    garmentColorHex: '#111015',
    size: 'XL',
    selectedVariant: null,
    designs: [],
  };
  const money = (value) => `Gs. ${Math.round(value).toLocaleString('es-PY')}`;
  const cartButton = document.querySelector('#add-cart');
  const cartNote = document.querySelector('#cart-note');
  const stockNote = document.querySelector('#stock-note');
  const designFeedback = document.querySelector('#design-feedback');
  const selectionPanel = document.querySelector('#selection-panel');
  let selectedDesign = null;
  let customizationId = new URLSearchParams(window.location.search).get('customization');
  const matchesColor = (variant) => !variant.color || variant.color.toLowerCase() === customizerState.garmentColor.toLowerCase();

  const updateStock = () => {
    document.querySelectorAll('.size-option').forEach((button) => {
      const available = !variants.length || variants.some((variant) => variant.size === button.dataset.size && variant.stock > 0 && matchesColor(variant));
      button.classList.toggle('is-out-of-stock', !available);
      button.setAttribute('aria-disabled', String(!available));
    });
    customizerState.selectedVariant = variants.find((variant) => variant.size === customizerState.size && matchesColor(variant)) || null;
    const unavailable = variants.length && (!customizerState.selectedVariant || customizerState.selectedVariant.stock < 1);
    stockNote.textContent = unavailable ? 'No hay stock para esta combinación de color y talla.' : 'Talla disponible para continuar.';
    stockNote.classList.toggle('is-error', unavailable);
  };

  const updateSummary = () => {
    document.querySelector('#selected-color').textContent = customizerState.garmentColor;
    document.querySelector('#summary-color').textContent = customizerState.garmentColor;
    document.querySelector('#summary-size').textContent = customizerState.size;
    document.querySelector('#base-price').textContent = money(basePrice);
    document.querySelector('#total-price').textContent = money(basePrice);
  };

  const showDesignFeedback = (message, isError = false) => {
    designFeedback.textContent = message;
    designFeedback.classList.toggle('is-error', isError);
  };

  const renderSelection = (design) => {
    selectedDesign = design;
    selectionPanel.hidden = !design;
    const designCount = customizerState.designs.length;
    document.querySelector('#summary-design').textContent = designCount ? `${designCount} elemento${designCount === 1 ? '' : 's'}` : 'Lisa';
    if (!design) return;
    document.querySelector('#selection-title').textContent = design.type === 'text' ? 'TEXTO SELECCIONADO' : 'DISEÑO SELECCIONADO';
    document.querySelector('#design-scale').value = design.scale;
    document.querySelector('#scale-value').value = `${Math.round(design.scale * 100)}%`;
    document.querySelector('#design-rotation').value = design.rotation;
    document.querySelector('#rotation-value').value = `${Math.round(design.rotation)}°`;
    const textProperties = document.querySelector('#text-properties');
    textProperties.hidden = design.type !== 'text';
    if (design.type === 'text') {
      document.querySelector('#selected-text').value = design.text;
      document.querySelector('#text-font').value = design.fontFamily;
      document.querySelector('#text-color').value = design.color;
    }
  };

  document.addEventListener('gymculture:design-selection', (event) => renderSelection(event.detail));

  document.querySelector('#design-upload').addEventListener('change', async (event) => {
    const [file] = event.target.files;
    if (!file) return;
    showDesignFeedback('Validando imagen…');
    try {
      await window.GymCulture3D.prepareImage(file);
      showDesignFeedback('Hacé clic sobre la prenda para colocar tu diseño.');
    } catch (error) {
      showDesignFeedback(error.message || 'No se pudo preparar la imagen.', true);
    } finally {
      event.target.value = '';
    }
  });

  document.querySelector('#add-3d-text').addEventListener('click', () => {
    const input = document.querySelector('#new-text');
    const text = input.value.trim();
    if (!text) {
      showDesignFeedback('Escribí un texto antes de agregarlo.', true);
      return;
    }
    try {
      window.GymCulture3D.prepareText({ text, fontFamily: 'Outfit', color: '#ffffff' });
      showDesignFeedback('Hacé clic sobre la prenda para colocar el texto.');
    } catch (error) {
      showDesignFeedback(error.message, true);
    }
  });

  const updateSelected = (changes) => {
    if (!selectedDesign) return;
    try {
      window.GymCulture3D.updateSelectedDesign(changes);
    } catch (error) {
      showDesignFeedback(error.message, true);
    }
  };
  document.querySelector('#design-scale').addEventListener('input', (event) => {
    const scale = Number(event.target.value);
    document.querySelector('#scale-value').value = `${Math.round(scale * 100)}%`;
    updateSelected({ scale });
  });
  document.querySelector('#design-rotation').addEventListener('input', (event) => {
    const rotation = Number(event.target.value);
    document.querySelector('#rotation-value').value = `${rotation}°`;
    updateSelected({ rotation });
  });
  document.querySelector('#selected-text').addEventListener('input', (event) => updateSelected({ text: event.target.value.slice(0, 50) }));
  document.querySelector('#text-font').addEventListener('change', (event) => updateSelected({ fontFamily: event.target.value }));
  document.querySelector('#text-color').addEventListener('input', (event) => updateSelected({ color: event.target.value }));
  document.querySelector('#reposition-design').addEventListener('click', () => window.GymCulture3D.rearmSelectedDesign());
  document.querySelector('#delete-design').addEventListener('click', () => window.GymCulture3D.removeSelectedDesign());

  const syncControlsFromState = () => {
    document.querySelectorAll('.color-option').forEach((option) => {
      const selected = option.dataset.color.toLowerCase() === customizerState.garmentColor.toLowerCase();
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-checked', String(selected));
    });
    document.querySelectorAll('.size-option').forEach((option) => {
      const selected = option.dataset.size === customizerState.size;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-checked', String(selected));
    });
    updateStock();
    updateSummary();
    renderSelection(null);
  };

  document.addEventListener('gymculture:customization-loaded', syncControlsFromState);

  document.querySelectorAll('.color-option').forEach((button) => button.addEventListener('click', () => {
    customizerState.garmentColor = button.dataset.color;
    customizerState.garmentColorHex = button.dataset.hex;
    document.querySelectorAll('.color-option').forEach((option) => {
      const selected = option === button;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-checked', String(selected));
    });
    updateStock();
    updateSummary();
    window.GymCulture3D?.setColor(customizerState.garmentColorHex);
  }));

  document.querySelectorAll('.size-option').forEach((button) => button.addEventListener('click', () => {
    customizerState.size = button.dataset.size;
    document.querySelectorAll('.size-option').forEach((option) => {
      const selected = option === button;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-checked', String(selected));
    });
    updateStock();
    updateSummary();
  }));

  const loginDestination = () => `/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  cartButton.addEventListener('click', async () => {
    if (!localStorage.getItem('gc_access_token') && !localStorage.getItem('gc_refresh_token')) {
      cartNote.textContent = 'Necesitás iniciar sesión para agregar este producto.';
      window.location.assign(loginDestination());
      return;
    }
    const productId = Number(customizerRoot.dataset.productId);
    if (!productId) {
      cartNote.textContent = 'El Custom Lab necesita un producto base activo.';
      return;
    }
    if (variants.length && (!customizerState.selectedVariant || customizerState.selectedVariant.stock < 1)) {
      cartNote.textContent = 'Seleccioná una variante con stock antes de continuar.';
      return;
    }
    cartButton.disabled = true;
    cartButton.textContent = customizationId ? 'GUARDANDO...' : (customizerState.designs.length ? 'GUARDANDO PERSONALIZACIÓN...' : 'AGREGANDO...');
    cartNote.textContent = '';
    try {
      if (customizerState.designs.length || customizationId) {
        const isNewCustomization = !customizationId;
        const state = window.GymCulture3D.getCustomizationState();
        const previews = await window.GymCulture3D.capturePreviews();
        const form = await window.GymCultureCustomizationApi.buildFormData({
          productId,
          variantId: customizerState.selectedVariant.id,
          state,
          previews,
          addToCart: !customizationId,
        });
        const saved = customizationId
          ? await window.GymCultureCustomizationApi.update(customizationId, form)
          : await window.GymCultureCustomizationApi.create(form);
        customizationId = saved.id;
        cartNote.textContent = isNewCustomization ? 'Producto personalizado agregado.' : 'Personalización guardada correctamente.';
        cartButton.textContent = 'GUARDAR CAMBIOS';
      } else {
        const response = await window.GymCultureAuth.request('/api/cart/items/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product: productId, variant: customizerState.selectedVariant?.id ?? null, quantity: 1 }),
        });
        if (response.status === 401) {
          window.location.assign(loginDestination());
          return;
        }
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          cartNote.textContent = data.detail || Object.values(data).flat().join(' ') || 'No pudimos agregar el producto.';
          return;
        }
        cartNote.textContent = 'Producto agregado al carrito.';
      }
      document.dispatchEvent(new CustomEvent('gymculture:cart-changed'));
    } catch (error) {
      console.error('[GYM CULTURE] Error al agregar al carrito.', error);
      cartNote.textContent = error.message || 'No pudimos conectar con el carrito. Intentá de nuevo.';
    } finally {
      cartButton.disabled = false;
      cartButton.textContent = customizationId ? 'GUARDAR CAMBIOS' : 'AGREGAR AL CARRITO';
    }
  });

  updateStock();
  updateSummary();
  window.GymCultureCustomizer = {
    state: customizerState,
    getCustomizationState: () => window.GymCulture3D?.getCustomizationState(),
  };

  const loadExistingCustomization = async () => {
    if (!customizationId) return;
    if (!localStorage.getItem('gc_access_token') && !localStorage.getItem('gc_refresh_token')) {
      window.location.assign(loginDestination());
      return;
    }
    try {
      const saved = await window.GymCultureCustomizationApi.get(customizationId);
      if (!window.GymCulture3D?.isReady()) {
        await new Promise((resolve) => document.addEventListener('gymculture:3d-ready', resolve, { once: true }));
      }
      await window.GymCulture3D.loadCustomization(saved.configuration);
      cartButton.textContent = 'GUARDAR CAMBIOS';
      document.querySelector('.customizer-intro > p:last-child').textContent = 'Editá tu personalización guardada.';
    } catch (error) {
      cartNote.textContent = error.status === 404 ? 'No encontramos esa personalización.' : error.message;
    }
  };
  loadExistingCustomization();
}
