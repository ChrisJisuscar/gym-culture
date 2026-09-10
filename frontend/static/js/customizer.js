const customizerRoot = document.querySelector('.customizer-layout');

if (customizerRoot) {
  const products = JSON.parse(document.querySelector('#customizer-products').textContent);
  const selectedProduct = () => products.find((product) => product.id === customizerState.productId && product.garment_type === customizerState.garmentType)
    || products.find((product) => product.garment_type === customizerState.garmentType);
  const currentVariants = () => (selectedProduct()?.variants || []).filter((variant) => variant.active !== false);
  const customizerState = {
    garmentType: 'tshirt',
    hoodState: 'down',
    productId: null,
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
  let viewerBusy = false;
  let saving = false;
  let restoreFailed = false;
  let removingBackground = false;
  const backgroundButton = document.querySelector('#remove-background');
  const garmentOptions = document.querySelectorAll('[data-garment]');
  let customizationId = new URLSearchParams(window.location.search).get('customization');

  // Configuración central de colores (solo label/hex/orden visual). La fuente de verdad
  // para "existe o no" una combinación sigue siendo ProductVariant del backend.
  const CLOTH_HEX = new Map(Object.entries({
    negro: '#111015', blanco: '#ebe9e4', gris: '#7a7780', azul: '#244a8f', rojo: '#9f233d', verde: '#276749',
  }));
  const normalizeColor = (name) => ({black:'negro',white:'blanco',gray:'gris',grey:'gris',blue:'azul',red:'rojo',green:'verde'}[String(name || '').trim().toLowerCase()] || String(name || '').trim().toLowerCase());
  const normalizeSize = (size) => ({XXL:'2XL',XXXL:'3XL'}[String(size || '').trim().toUpperCase()] || String(size || '').trim().toUpperCase());
  const colorHex = (name) => CLOTH_HEX.get(normalizeColor(name)) || '#777777';
  const resolveSelectedVariant = (product, color, size) => {
    const colorKey = normalizeColor(color);
    return (product?.variants || []).find(
      (variant) => variant.active !== false && normalizeSize(variant.size) === normalizeSize(size) && normalizeColor(variant.color) === colorKey,
    ) || null;
  };

  // Only real active variants supply choices. Stock never participates in resolution.
  const catalogVariants = products.flatMap((product) => product.variants).filter((variant) => variant.active !== false);
  const paletteColors = new Map(catalogVariants.map((variant) => [normalizeColor(variant.color), variant.color]));
  for (const [selector, field] of [['.color-option', 'color'], ['.size-option', 'size']]) {
    const template = document.querySelector(selector);
    const container = template.parentElement;
    const originals = [...container.querySelectorAll(selector)];
    const unique = new Map();
    if (field === 'color') {
      for (const value of paletteColors.values()) unique.set(String(value).toLowerCase(), value);
    } else {
      for (const variant of catalogVariants) {
        if (variant[field] == null) continue;
        const key = String(variant[field]).toLowerCase();
        if (!unique.has(key)) unique.set(key, variant[field]);
      }
    }
    const values = [...unique.values()];
    if (!values.length) continue;
    container.replaceChildren(...values.map((value) => {
      const original = originals.find((button) => String(button.dataset[field] ?? '').toLowerCase() === String(value).toLowerCase());
      const button = (original || template).cloneNode(true);
      button.dataset[field] = value;
      button.classList.remove('is-selected');
      button.setAttribute('aria-checked', 'false');
      if (field === 'size') button.textContent = value;
      else {
        button.dataset.hex = original?.dataset.hex || colorHex(value);
        button.style.setProperty('--swatch', button.dataset.hex);
        button.setAttribute('aria-label', value);
        button.title = value;
      }
      return button;
    }));
  }

  const stockHint = document.querySelector('#stock-hint');

  const updateAvailability = () => {
    const product = selectedProduct();
    customizerState.productId = product?.id ?? null;
    const variants = currentVariants();
    const hasVariants = variants.length > 0;
    document.querySelectorAll('.color-option').forEach((button) => {
      const exists = variants.some((variant) => normalizeColor(variant.color) === normalizeColor(button.dataset.color));
      button.hidden = !exists;
      button.classList.toggle('is-selected', normalizeColor(button.dataset.color) === normalizeColor(customizerState.garmentColor));
      button.setAttribute('aria-checked', String(button.classList.contains('is-selected')));
      button.disabled = viewerBusy || saving || !exists;
      button.classList.toggle('is-unavailable', hasVariants && !exists);
      button.setAttribute('aria-disabled', String(hasVariants && !exists));
    });
    document.querySelectorAll('.size-option').forEach((button) => {
      const exists = variants.some((variant) => normalizeSize(variant.size) === normalizeSize(button.dataset.size));
      button.classList.toggle('is-selected', button.dataset.size === customizerState.size);
      button.setAttribute('aria-checked', String(button.classList.contains('is-selected')));
      button.hidden = !exists;
      button.disabled = viewerBusy || saving || !exists;
      button.classList.toggle('is-unavailable', hasVariants && !exists);
      button.setAttribute('aria-disabled', String(hasVariants && !exists));
    });
    customizerState.selectedVariant = resolveSelectedVariant(product, customizerState.garmentColor, customizerState.size);
    if (!customizerState.selectedVariant) {
      stockNote.textContent = hasVariants
        ? 'Esta combinación de color y talle no está configurada todavía. Elegí otra.'
        : 'Esta prenda todavía no tiene variantes configuradas en el catálogo.';
      stockNote.classList.add('is-warning');
      if (stockHint) stockHint.hidden = true;
    } else {
      const stock = customizerState.selectedVariant.stock;
      stockNote.textContent = stock ? 'Disponible' : 'Sin stock inmediato';
      stockNote.classList.toggle('is-warning', !stock);
      if (stockHint) {
        stockHint.hidden = stock > 0;
        stockHint.textContent = 'Podés personalizar y realizar tu pedido igualmente. La prenda será preparada cuando se reponga esta variante.';
      }
    }
    cartButton.disabled = viewerBusy || saving || restoreFailed || !customizerState.selectedVariant || !product;
  };

  const syncGarmentControls = () => {
    garmentOptions.forEach((button) => {
      const enabled = window.GymCulture3D?.garments[button.dataset.garment]?.enabled ?? false;
      button.disabled = !enabled || viewerBusy || saving;
      const active = button.dataset.garment === customizerState.garmentType;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const note = document.querySelector('#garment-note');
    note.hidden = Boolean(selectedProduct());
    note.textContent = 'Esta prenda no tiene un producto activo en el catálogo.';
    cartButton.disabled = viewerBusy || saving;
    document.querySelectorAll('.config-panel input, .config-panel select, .config-panel button, .product-options button, .hood-controls button').forEach((input) => {
      input.disabled = viewerBusy || saving;
    });
    document.querySelector('#hood-controls').hidden = customizerState.garmentType !== 'hoodie';
    document.querySelectorAll('[data-hood-state]').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.hoodState === customizerState.hoodState);
      button.setAttribute('aria-pressed', String(button.dataset.hoodState === customizerState.hoodState));
    });
    updateAvailability();
    updateSummary();
  };

  // Tras cambiar de prenda (o al arrancar), asegura que color/talla pertenezcan al producto
  // activo de ESE garment. Prefiere conservar la selección actual si sigue existiendo y
  // reencauza a la primera variante real del producto cuando no. El stock nunca participa.
  const alignSelectionToProduct = () => {
    const product = selectedProduct();
    const variants = currentVariants();
    if (!product || !variants.length) return;
    let size = customizerState.size;
    if (!variants.some((variant) => variant.size === size)) size = variants[0].size;
    const candidate = variants.find(
      (variant) => variant.size === size && normalizeColor(variant.color) === normalizeColor(customizerState.garmentColor),
    ) || variants.find((variant) => variant.size === size) || variants[0];
    customizerState.size = size;
    customizerState.garmentColor = candidate.color;
    customizerState.garmentColorHex = colorHex(candidate.color);
    updateAvailability();
    updateSummary();
    window.GymCulture3D?.setColor(customizerState.garmentColorHex);
  };

  document.querySelectorAll('[data-hood-state]').forEach((button) => button.addEventListener('click', () => {
    window.GymCulture3D.setHoodState(button.dataset.hoodState);
    syncGarmentControls();
  }));

  garmentOptions.forEach((button) => button.addEventListener('click', async () => {
    if (button.disabled) return;
    await window.GymCulture3D.setGarmentType(button.dataset.garment);
    syncGarmentControls();
    alignSelectionToProduct();
  }));
  document.addEventListener('gymculture:3d-busy', (event) => {
    viewerBusy = event.detail;
    syncGarmentControls();
  });
  document.addEventListener('gymculture:garment-changed', () => {
    syncGarmentControls();
    showDesignFeedback('PNG, JPG o WebP · máximo 10 MB');
  });

  const updateSummary = () => {
    document.querySelector('#selected-color').textContent = customizerState.garmentColor;
    document.querySelector('#summary-color').textContent = customizerState.garmentColor;
    document.querySelector('#summary-size').textContent = customizerState.size;
    document.querySelector('#summary-product').textContent = selectedProduct()?.name || 'No disponible';
    document.querySelector('#base-price').textContent = selectedProduct() ? money(Number(selectedProduct().price)) : '-';
    document.querySelector('#total-price').textContent = selectedProduct() ? money(Number(selectedProduct().price)) : '-';
  };

  const showDesignFeedback = (message, isError = false) => {
    designFeedback.textContent = message;
    designFeedback.classList.toggle('is-error', isError);
  };

  const renderSelection = (design) => {
    selectedDesign = design;
    backgroundButton.hidden = design?.type !== 'image';
    backgroundButton.disabled = removingBackground;
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

  backgroundButton.addEventListener('click', async () => {
    if (removingBackground) return;
    removingBackground = true;
    backgroundButton.disabled = true;
    backgroundButton.textContent = 'PROCESANDO...';
    showDesignFeedback('Identificando el diseño para quitar el fondo…');
    try {
      await window.GymCulture3D.removeBackground();
      showDesignFeedback('Imagen procesada. Revisá el resultado antes de guardar.');
    } catch (error) {
      console.error('[GYM CULTURE] image_processing_error', error);
      showDesignFeedback(error.message || 'No pudimos procesar esta imagen. Intentá nuevamente.', true);
    } finally {
      removingBackground = false;
      backgroundButton.disabled = false;
      backgroundButton.textContent = 'QUITAR FONDO';
    }
  });

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
    updateAvailability();
    updateSummary();
    renderSelection(null);
  };

  document.addEventListener('gymculture:customization-loaded', () => { syncControlsFromState(); syncGarmentControls(); });

  document.querySelectorAll('.color-option').forEach((button) => button.addEventListener('click', () => {
    customizerState.garmentColor = button.dataset.color;
    customizerState.garmentColorHex = button.dataset.hex;
    document.querySelectorAll('.color-option').forEach((option) => {
      const selected = option === button;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-checked', String(selected));
    });
    updateAvailability();
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
    updateAvailability();
    updateSummary();
  }));

  const loginDestination = () => `/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  cartButton.addEventListener('click', async () => {
    if (viewerBusy || saving || restoreFailed || !customizerState.selectedVariant) return;
    if (!localStorage.getItem('gc_access_token') && !localStorage.getItem('gc_refresh_token')) {
      cartNote.textContent = 'Necesitás iniciar sesión para agregar este producto.';
      window.location.assign(loginDestination());
      return;
    }
    const productId = customizerState.productId;
    if (!productId) {
      cartNote.textContent = 'El Custom Lab necesita un producto base activo.';
      return;
    }
    if (!customizerState.selectedVariant) {
      cartNote.textContent = 'Esta combinación de color y talle no está configurada todavía. Elegí otra.';
      return;
    }
    saving = true;
    syncGarmentControls();
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
      saving = false;
      syncGarmentControls();
      cartButton.textContent = customizationId ? 'GUARDAR CAMBIOS' : 'AGREGAR AL CARRITO';
    }
  });

  updateAvailability();
  updateSummary();
  if (!customizationId) alignSelectionToProduct();
  window.GymCultureCustomizer = {
    state: customizerState,
    resolveSelectedVariant,
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
      if (!products.some((product) => product.id === saved.product && product.garment_type === saved.configuration.garment.type)) {
        throw new Error('El producto de esta personalizacion ya no esta disponible.');
      }
      if (!window.GymCulture3D?.isReady()) {
        if (!window.GymCulture3D) {
          await new Promise((resolve) => document.addEventListener('gymculture:3d-busy', resolve, { once: true }));
        }
        await window.GymCulture3D.whenReady();
        if (!window.GymCulture3D.isReady()) throw new Error('No se pudo iniciar el visor para restaurar la personalización.');
      }
      customizerState.productId = saved.product;
      await window.GymCulture3D.loadCustomization({ ...saved.configuration, garment: { ...saved.configuration.garment, productId: saved.product } });
      cartButton.textContent = 'GUARDAR CAMBIOS';
      document.querySelector('.customizer-intro > p:last-child').textContent = 'Editá tu personalización guardada.';
    } catch (error) {
      restoreFailed = true;
      updateAvailability();
      cartNote.textContent = error.status === 404 ? 'No encontramos esa personalización.' : error.message;
    }
  };
  loadExistingCustomization();
}
