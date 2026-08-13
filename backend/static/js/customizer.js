const root = document.querySelector('.customizer-layout');

if (root) {
  const variants = JSON.parse(document.querySelector('#product-variants').textContent);
  const basePrice = Number(root.dataset.price) || 89000;
  const state = {
    product: root.dataset.productId || null,
    variant: { color: 'Negro', size: 'XL' },
    side: 'front',
    front: { elements: [] },
    back: { elements: [] },
    selectedId: null,
  };
  const shirt = document.querySelector('#shirt');
  const shirtImage = document.querySelector('#shirt-image');
  const safeArea = document.querySelector('#safe-area');
  const controls = document.querySelector('#element-controls');
  const empty = document.querySelector('#editor-empty');
  const history = [];
  const future = [];
  const recoloredImages = new Map();
  let dragging = null;

  const activeElements = () => state[state.side].elements;
  const selected = () => activeElements().find((item) => item.id === state.selectedId);
  const money = (value) => `Gs. ${Math.round(value).toLocaleString('es-PY')}`;
  const snapshot = () => JSON.stringify({ front: state.front, back: state.back, side: state.side, variant: state.variant });
  const getShirtImageForSide = (side = state.side) => root.dataset[`${side}Image`] || root.dataset.frontImage;

  const save = () => {
    history.push(snapshot());
    if (history.length > 30) history.shift();
    future.length = 0;
    updateUndo();
  };

  const updateUndo = () => {
    document.querySelector('#undo').disabled = !history.length;
    document.querySelector('#redo').disabled = !future.length;
  };

  const updateSummary = () => {
    const element = selected() || activeElements()[0];
    document.querySelector('#selected-color').textContent = state.variant.color;
    document.querySelector('#summary-color').textContent = state.variant.color;
    document.querySelector('#summary-size').textContent = state.variant.size;
    document.querySelector('#summary-side').textContent = state.side === 'front' ? 'Frente' : 'Espalda';
    document.querySelector('#summary-design').textContent = element ? (element.type === 'text' ? element.content : 'Imagen personalizada') : 'Sin diseño';
    const print = state.front.elements.length + state.back.elements.length ? 10000 : 0;
    document.querySelector('#base-price').textContent = money(basePrice);
    document.querySelector('#design-price').textContent = money(print);
    document.querySelector('#total-price').textContent = money(basePrice + print);
    empty.hidden = Boolean(activeElements().length);
  };

  const updateSideButtons = () => {
    document.querySelectorAll('.side-switch button').forEach((button) => {
      const isActive = button.dataset.side === state.side;
      button.classList.toggle('is-selected', isActive);
      button.setAttribute('aria-selected', String(isActive));
    });
  };

  const updateColorButtons = () => {
    document.querySelectorAll('.color-option').forEach((button) => {
      const isActive = button.dataset.color === state.variant.color;
      button.classList.toggle('is-selected', isActive);
      button.setAttribute('aria-checked', String(isActive));
    });
  };

  const clamp = (item) => {
    item.width = Math.max(12, Math.min(90, item.width));
    item.height = Math.max(8, Math.min(72, item.height));
    item.x = Math.max(item.width / 2, Math.min(100 - item.width / 2, item.x));
    item.y = Math.max(item.height / 2, Math.min(100 - item.height / 2, item.y));
  };

  const render = () => {
    safeArea.querySelectorAll('.design-element').forEach((node) => node.remove());
    activeElements().forEach((item) => {
      const node = document.createElement(item.type === 'image' ? 'img' : 'div');
      node.className = `design-element ${item.type === 'text' ? 'text-element' : ''}${item.id === state.selectedId ? ' is-selected' : ''}`;
      node.dataset.id = item.id;
      node.style.left = `${item.x}%`;
      node.style.top = `${item.y}%`;
      node.style.width = `${item.width}%`;
      node.style.height = `${item.height}%`;
      node.style.transform = `translate(-50%,-50%) rotate(${item.rotation}deg)`;
      if (item.type === 'image') {
        node.src = item.content;
        node.alt = 'Diseño subido';
      } else {
        node.textContent = item.content;
        node.style.fontFamily = item.font;
        node.style.fontWeight = item.bold ? '800' : '500';
        node.style.fontSize = `${Math.max(11, item.height * 1.35)}px`;
      }
      node.addEventListener('pointerdown', startDrag);
      safeArea.append(node);
    });
    controls.hidden = !selected();
    updateSummary();
  };

  const recolorShirtImage = (source, color) => new Promise((resolve, reject) => {
    if (color === 'Negro') {
      resolve(source);
      return;
    }
    const targetColors = {
      Blanco: [235, 233, 228], Gris: [122, 119, 128], Violeta: [124, 58, 237],
      'Azul oscuro': [24, 34, 56], Rojo: [159, 35, 61], 'Verde oscuro': [25, 56, 46],
    };
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
      const [red, green, blue] = targetColors[color];
      for (let index = 0; index < pixels.data.length; index += 4) {
        const luminance = (pixels.data[index] * .2126) + (pixels.data[index + 1] * .7152) + (pixels.data[index + 2] * .0722);
        if (luminance < 138) {
          const fabricLightness = .18 + (luminance / 138) * .82;
          pixels.data[index] = red * fabricLightness;
          pixels.data[index + 1] = green * fabricLightness;
          pixels.data[index + 2] = blue * fabricLightness;
        }
      }
      context.putImageData(pixels, 0, 0);
      resolve(canvas.toDataURL('image/webp', .94));
    };
    image.onerror = reject;
    image.src = source;
  });

  const updateShirtImage = async () => {
    const source = getShirtImageForSide();
    const cacheKey = `${source}|${state.variant.color}`;
    const requestedSide = state.side;
    const requestedColor = state.variant.color;
    shirt.dataset.side = requestedSide;
    shirtImage.alt = `Remera oversize ${requestedColor.toLowerCase()}, vista ${requestedSide === 'front' ? 'frontal' : 'trasera'}`;
    try {
      if (!recoloredImages.has(cacheKey)) recoloredImages.set(cacheKey, recolorShirtImage(source, requestedColor));
      const renderedImage = await recoloredImages.get(cacheKey);
      if (state.side === requestedSide && state.variant.color === requestedColor) shirtImage.src = renderedImage;
    } catch {
      if (state.side === requestedSide && state.variant.color === requestedColor) shirtImage.src = source;
    }
  };

  const updateStock = () => {
    if (!variants.length) return;
    document.querySelectorAll('.size-option').forEach((button) => {
      const available = variants.some((variant) => variant.size === button.dataset.size && variant.stock > 0 && (!variant.color || variant.color.toLowerCase() === state.variant.color.toLowerCase()));
      button.disabled = !available;
    });
  };

  const setSide = (side, recordHistory = true) => {
    if (side === state.side) return;
    if (recordHistory) save();
    state.side = side;
    state.selectedId = null;
    updateSideButtons();
    updateShirtImage();
    render();
  };

  const setColor = (color, recordHistory = true) => {
    if (color === state.variant.color) return;
    if (recordHistory) save();
    state.variant.color = color;
    updateColorButtons();
    updateStock();
    updateShirtImage();
    updateSummary();
  };

  const add = (item) => {
    save();
    activeElements().push({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), x: 50, y: 50, width: 40, height: 25, rotation: 0, ...item });
    state.selectedId = activeElements().at(-1).id;
    render();
  };

  const startDrag = (event) => {
    const item = activeElements().find((entry) => entry.id === event.currentTarget.dataset.id);
    if (!item) return;
    save();
    state.selectedId = item.id;
    dragging = { item, startX: event.clientX, startY: event.clientY, x: item.x, y: item.y };
    event.currentTarget.setPointerCapture(event.pointerId);
    render();
  };

  safeArea.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    const rect = safeArea.getBoundingClientRect();
    dragging.item.x = dragging.x + ((event.clientX - dragging.startX) / rect.width) * 100;
    dragging.item.y = dragging.y + ((event.clientY - dragging.startY) / rect.height) * 100;
    clamp(dragging.item);
    render();
  });
  safeArea.addEventListener('pointerup', () => { dragging = null; });

  document.querySelectorAll('.color-option').forEach((button) => button.addEventListener('click', () => setColor(button.dataset.color)));
  document.querySelectorAll('.size-option').forEach((button) => button.addEventListener('click', () => {
    if (button.disabled || button.dataset.size === state.variant.size) return;
    save();
    state.variant.size = button.dataset.size;
    document.querySelectorAll('.size-option').forEach((item) => item.classList.toggle('is-selected', item === button));
    updateSummary();
  }));
  document.querySelectorAll('.side-switch button').forEach((button) => button.addEventListener('click', () => setSide(button.dataset.side)));

  document.querySelector('#image-upload').addEventListener('change', (event) => {
    const file = event.target.files[0];
    const message = document.querySelector('#upload-message');
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      message.textContent = 'Usá PNG, JPG, JPEG o WEBP.';
      message.className = 'editor-message is-error';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const image = new Image();
      image.onload = () => {
        message.className = 'editor-message';
        message.textContent = image.width < 900 || image.height < 900 ? 'Calidad insuficiente. La imagen podría verse pixelada al imprimir.' : 'Imagen agregada correctamente.';
        add({ type: 'image', content: reader.result, width: 42, height: 42 });
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

  const textControls = document.querySelector('#text-controls');
  document.querySelector('#add-text').addEventListener('click', () => {
    add({ type: 'text', content: 'GYM CULTURE', width: 55, height: 18, font: 'Outfit', bold: true });
    textControls.hidden = false;
  });
  document.querySelector('#text-content').addEventListener('input', (event) => {
    const item = selected();
    if (item?.type === 'text') {
      item.content = event.target.value || ' ';
      render();
    }
  });
  document.querySelectorAll('[data-font]').forEach((button) => button.addEventListener('click', () => {
    const item = selected();
    if (item?.type === 'text') { item.font = button.dataset.font; render(); }
  }));
  document.querySelector('#text-bold').addEventListener('click', () => {
    const item = selected();
    if (item?.type === 'text') { item.bold = !item.bold; render(); }
  });
  document.querySelectorAll('.preset').forEach((button) => button.addEventListener('click', () => {
    add({ type: 'text', content: button.dataset.preset.replace('\\n', '\n'), width: 56, height: 26, font: 'Outfit', bold: true });
    textControls.hidden = false;
  }));

  controls.addEventListener('click', (event) => {
    const item = selected();
    const action = event.target.dataset.action;
    if (!item || !action) return;
    save();
    if (action === 'delete') { state[state.side].elements = activeElements().filter((entry) => entry.id !== item.id); state.selectedId = null; }
    if (action === 'rotate-left') item.rotation -= 15;
    if (action === 'rotate-right') item.rotation += 15;
    if (action === 'grow') { item.width *= 1.12; item.height *= 1.12; }
    if (action === 'shrink') { item.width *= .88; item.height *= .88; }
    clamp(item);
    render();
  });

  const restoreSnapshot = (nextState) => {
    Object.assign(state, nextState, { selectedId: null });
    updateSideButtons();
    updateColorButtons();
    updateStock();
    updateShirtImage();
    render();
  };
  document.querySelector('#undo').addEventListener('click', () => {
    if (!history.length) return;
    future.push(snapshot());
    restoreSnapshot(JSON.parse(history.pop()));
    updateUndo();
  });
  document.querySelector('#redo').addEventListener('click', () => {
    if (!future.length) return;
    history.push(snapshot());
    restoreSnapshot(JSON.parse(future.pop()));
    updateUndo();
  });

  const dialog = document.querySelector('#preview-dialog');
  document.querySelector('#preview-button').addEventListener('click', () => {
    const preview = document.querySelector('#preview-content');
    const clone = shirt.cloneNode(true);
    clone.className = 'preview-shirt';
    clone.querySelector('.safe-area')?.classList.add('is-preview');
    clone.querySelectorAll('.design-element').forEach((node) => node.classList.remove('is-selected'));
    preview.replaceChildren(clone);
    dialog.showModal();
  });
  document.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  document.querySelector('#add-cart').addEventListener('click', () => {
    document.querySelector('#cart-note').textContent = 'Tu configuración está lista para conectar al carrito en la próxima etapa.';
  });

  updateStock();
  updateSideButtons();
  updateColorButtons();
  updateShirtImage();
  render();
}
