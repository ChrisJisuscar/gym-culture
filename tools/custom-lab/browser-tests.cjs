// Start Django on 127.0.0.1:8765. All writes to HTTP APIs are intercepted.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true, args: ['--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    const errors = [];
    const modelRequests = [];
    let failOversize = false;
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => { if (request.url().endsWith('.glb')) modelRequests.push(request.url()); });
    // Observe private objects only in the test response, without shipping debug APIs.
    await page.route('**/js/customizer-3d.js', async (route) => {
      const response = await route.fetch();
      const source = (await response.text()).replaceAll('\r\n', '\n');
      await route.fulfill({ response, body: source.replace('  return {\n    init, dispose',
        '  window.__lab = () => ({ scene, camera, renderer, controls, garment, garmentSize, garmentMaterials, designManager });\n  return {\n    init, dispose') });
    });
    await page.route('**/oversized.glb', (route) => failOversize
      ? route.fulfill({ status: 503, body: 'Intentional test failure' }) : route.continue());
    await page.addInitScript(() => {
      const request = window.requestAnimationFrame.bind(window);
      const cancel = window.cancelAnimationFrame.bind(window);
      window.__labFrames = new Set();
      window.requestAnimationFrame = (callback) => {
        const id = request((time) => { window.__labFrames.delete(id); callback(time); });
        if (callback.name === 'render' && callback.toString().includes('controls')) window.__labFrames.add(id);
        return id;
      };
      window.cancelAnimationFrame = (id) => { window.__labFrames.delete(id); cancel(id); };
    });
    const ready = () => page.waitForFunction(() => window.GymCulture3D?.isReady());
    const state = () => page.evaluate(() => GymCulture3D.getCustomizationState());
    const select = async (type) => {
      await page.locator(`[data-garment="${type}"]`).click();
      await ready();
      assert.equal((await state()).garment.type, type);
    };
    const verifyEngine = async () => {
      assert.deepEqual(await page.evaluate(() => {
        const lab = __lab();
        return {
          scene: lab.scene === __engine.scene, renderer: lab.renderer === __engine.renderer,
          controls: lab.controls === __engine.controls, camera: lab.camera === __engine.camera,
          canvases: document.querySelectorAll('#customizer-3d-container canvas').length,
          loops: __labFrames.size,
        };
      }), { scene: true, renderer: true, controls: true, camera: true, canvases: 1, loops: 1 });
    };
    const previews = async (label) => {
      const result = await page.evaluate(async () => {
        const lab = __lab();
        const position = lab.camera.position.toArray();
        const { front, back } = await GymCulture3D.capturePreviews();
        const images = [];
        for (const blob of [front, back]) {
          const bitmap = await createImageBitmap(blob);
          const canvas = document.createElement('canvas');
          canvas.width = bitmap.width; canvas.height = bitmap.height;
          const context = canvas.getContext('2d'); context.drawImage(bitmap, 0, 0);
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          let left = 1024, right = 0, top = 1024, bottom = 0, count = 0;
          for (let y = 0; y < 1024; y++) for (let x = 0; x < 1024; x++) {
            const i = (y * 1024 + x) * 4;
            if (Math.abs(pixels[i] - pixels[0]) + Math.abs(pixels[i + 1] - pixels[1]) + Math.abs(pixels[i + 2] - pixels[2]) > 50) {
              count++; left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
            }
          }
          images.push({ width: bitmap.width, height: bitmap.height, count, left, right, top, bottom,
            data: await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.readAsDataURL(blob); }) });
          bitmap.close();
        }
        return { images, cameraPreserved: position.every((value, index) => Math.abs(value - lab.camera.position.toArray()[index]) < 1e-8) };
      });
      assert.equal(result.cameraPreserved, true);
      for (const [i, image] of result.images.entries()) {
        assert.equal(image.width, 1024); assert.equal(image.height, 1024);
        assert.ok(image.count > 20000, 'Preview contains a garment');
        assert.ok(image.left > 10 && image.right < 1014 && image.top > 10 && image.bottom < 1014, 'Garment is not cropped');
        await fs.writeFile(`.venv/custom-lab-tools/${label}-${i ? 'back' : 'front'}.webp`, Buffer.from(image.data, 'base64'));
      }
      assert.notEqual(result.images[0].data, result.images[1].data);
      await verifyEngine();
    };
    const placeText = async () => {
      await page.locator('#add-3d-text').click();
      const canvas = page.locator('.customizer-3d-canvas');
      const box = await canvas.boundingBox();
      await canvas.click({ position: { x: box.width * .5, y: box.height * .46 } });
      assert.equal((await state()).designs.length, 1);
    };

    const catalog = ['tshirt', 'oversized'].map((type, index) => ({
      id: 901 + index, name: type, garment_type: type, price: '89000',
      variants: ['Negro', 'Rojo', 'Blanco'].map((color, offset) => ({id: 910 + index * 10 + offset, color, size:'XL', stock:10}))
    }));
    await page.route('**/crear-mi-remera/', async route => {
      const response = await route.fetch();
      const body = (await response.text()).replace(/(<script id="customizer-products" type="application\/json">)[\s\S]*?(<\/script>)/, '$1' + JSON.stringify(catalog) + '$2');
      await route.fulfill({response, body});
    });
    await page.goto(`${process.env.LAB_URL || 'http://127.0.0.1:8765'}/crear-mi-remera/`);
    await ready();
    assert.equal(modelRequests.length, 1);
    assert.ok(modelRequests[0].endsWith('/tshirt.glb'));
    await page.evaluate(() => { window.__engine = __lab(); });
    await verifyEngine();
    assert.equal(await page.locator('[data-garment="hoodie"]').isDisabled(), false);
    assert.equal(await page.evaluate(() => GymCulture3D.setGarmentType('unknown')), false);
    assert.equal(modelRequests.length, 1);
    console.log('PASS lazy loading, disabled Hoodie, single engine');

    await page.locator('[data-color="Rojo"]').click();
    await page.evaluate(() => {
      window.__disposed = { geometry: false, material: false };
      __lab().garment.traverse((object) => {
        object.geometry?.addEventListener('dispose', () => { __disposed.geometry = true; });
      });
      __lab().garmentMaterials[0].addEventListener('dispose', () => { __disposed.material = true; });
    });
    await select('oversized');
    assert.deepEqual(await page.evaluate(() => __disposed), { geometry: true, material: true });
    assert.equal((await state()).garment.colorHex, '#9f233d');
    assert.equal((await state()).garment.variantId, 921);
    assert.equal(await page.locator('#add-cart').isDisabled(), false);
    assert.deepEqual(await page.evaluate(() => {
      const material = __lab().garmentMaterials[0];
      return [material.type, material.metalness, material.roughness, material.map, material.normalMap, material.roughnessMap, material.color.getHexString()];
    }), ['MeshStandardMaterial', 0, .88, null, null, null, '9f233d']);
    await verifyEngine();
    await page.locator('[data-color="Blanco"]').click();
    await previews('oversized');

    // Real mouse orbit, wheel zoom, and viewport resize for both models.
    const orbitAndResize = async () => {
      const canvas = page.locator('.customizer-3d-canvas');
      await canvas.scrollIntoViewIfNeeded();
      const box = await canvas.boundingBox();
      const before = await page.evaluate(() => __lab().camera.position.toArray());
      await page.mouse.move(box.x + box.width * .65, box.y + box.height * .5);
      await page.mouse.down(); await page.mouse.move(box.x + box.width * .35, box.y + box.height * .5, { steps: 12 }); await page.mouse.up();
      await page.waitForFunction((previous) => Math.abs(__lab().camera.position.x - previous[0]) > .01, before);
      const distance = await page.evaluate(() => __lab().camera.position.length());
      await page.mouse.wheel(0, 100);
      await page.waitForFunction((previous) => Math.abs(__lab().camera.position.length() - previous) > .001, distance);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForFunction(() => Math.abs(__lab().camera.aspect - document.querySelector('#customizer-3d-container').clientWidth / document.querySelector('#customizer-3d-container').clientHeight) < .001);
      await previews(`${(await state()).garment.type}-mobile`);
      await page.setViewportSize({ width: 1600, height: 1100 });
      await page.waitForFunction(() => __lab().camera.aspect > 1);
    };
    await orbitAndResize();
    await placeText();
    const oversizeSaved = await state();
    page.once('dialog', (dialog) => { assert.equal(dialog.message(), 'Cambiar de prenda eliminará los diseños actuales.'); dialog.dismiss(); });
    await page.locator('[data-garment="tshirt"]').click();
    assert.equal((await state()).garment.type, 'oversized');
    assert.equal((await state()).designs.length, 1);
    page.once('dialog', (dialog) => dialog.accept());
    await select('tshirt');
    assert.equal((await state()).designs.length, 0);
    assert.equal(await page.evaluate(() => __lab().designManager.resources.size), 0);
    await previews('tshirt');
    await orbitAndResize();
    await placeText();
    const tshirtSaved = await state();
    console.log('PASS switching, color/material, disposal, confirmation, orbit/zoom, resize, square previews');

    failOversize = true;
    page.once('dialog', (dialog) => dialog.accept());
    await page.locator('[data-garment="oversized"]').click();
    await ready();
    assert.equal((await state()).garment.type, 'tshirt');
    assert.equal((await state()).designs.length, 1);
    failOversize = false;
    await page.evaluate((configuration) => GymCulture3D.loadCustomization(configuration), oversizeSaved);
    assert.equal((await state()).garment.type, 'oversized');
    assert.equal(await page.evaluate(() => __lab().designManager.meshes().length), 1);
    await previews('oversized-text');
    await page.evaluate((configuration) => GymCulture3D.loadCustomization(configuration), tshirtSaved);
    assert.deepEqual(await state(), tshirtSaved);
    await previews('tshirt-text');
    console.log('PASS failed-load rollback and persistence for both garments');

    // Upload and restore an image using an asset URL, as returned by the API.
    const imageData = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
      const context = canvas.getContext('2d'); context.fillStyle = '#a855f7'; context.fillRect(0, 0, 128, 128);
      return canvas.toDataURL();
    });
    await page.locator('#design-upload').setInputFiles({ name: 'design.png', mimeType: 'image/png', buffer: Buffer.from(imageData.split(',')[1], 'base64') });
    await page.waitForFunction(() => Boolean(__lab().designManager.pending));
    let imageDialog = false;
    page.once('dialog', async (dialog) => { imageDialog = true; await dialog.dismiss(); });
    await page.locator('[data-garment="oversized"]').click();
    assert.equal(imageDialog, true);
    const canvas = page.locator('.customizer-3d-canvas');
    const box = await canvas.boundingBox();
    await canvas.click({ position: { x: box.width * .5, y: box.height * .65 } });
    const imageSaved = await state();
    assert.equal(imageSaved.designs.length, 2);
    const design = imageSaved.designs.find((item) => item.type === 'image');
    design.assetUrl = imageData; delete design.source;
    await page.evaluate((configuration) => GymCulture3D.loadCustomization(configuration), imageSaved);
    assert.equal(await page.evaluate(() => __lab().designManager.meshes().length), 2);
    await previews('tshirt-image');

    // Exercise the existing cart path without writing to the development database.
    await page.evaluate(() => {
      localStorage.setItem('gc_access_token', 'browser-test-token');
      window.__cartRequest = null;
      GymCultureAuth.request = async (url, options) => {
        if (options?.method === 'POST') window.__cartRequest = { url, options };
        return new Response(JSON.stringify({ id: 1 }), { status: 201, headers: { 'Content-Type': 'application/json' } });
      };
    });
    const emptyState = { ...tshirtSaved, designs: [] };
    await page.evaluate((configuration) => GymCulture3D.loadCustomization(configuration), emptyState);
    await page.locator('[data-color="Negro"]').click();
    await page.locator('#add-cart').click();
    await page.waitForFunction(() => Boolean(window.__cartRequest));
    assert.equal(await page.evaluate(() => __cartRequest.url), '/api/cart/items/');
    const cartPayload = await page.evaluate(() => JSON.parse(__cartRequest.options.body));
    assert.equal(cartPayload.variant, (await state()).garment.variantId);
    assert.equal(cartPayload.quantity, 1);
    for (const type of ['oversized', 'tshirt', 'oversized', 'tshirt']) await select(type);
    await page.waitForFunction(() => __lab().renderer.info.memory.geometries === 1);
    assert.equal(await page.evaluate(() => __lab().renderer.info.memory.textures), 0);
    await verifyEngine();
    let releaseLoad;
    let loadingStarted;
    const loading = new Promise((resolve) => { loadingStarted = resolve; });
    await page.route('**/oversized.glb', async (route) => {
      await new Promise((resolve) => { releaseLoad = resolve; loadingStarted(); });
      await route.continue();
    });
    await page.evaluate(() => { window.__pendingChange = GymCulture3D.setGarmentType('oversized'); });
    await loading;
    await page.evaluate(() => GymCulture3D.dispose());
    releaseLoad();
    assert.equal(await page.evaluate(() => __pendingChange), false);
    assert.equal(await page.evaluate(() => __labFrames.size), 0);
    assert.equal(await page.locator('#customizer-3d-container canvas').count(), 0);
    assert.equal(await page.evaluate(() => __lab().garment), null);
    assert.deepEqual(errors, []);
    console.log('PASS images, cart request, repeated switches, disposal during loading; no JavaScript page errors');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
