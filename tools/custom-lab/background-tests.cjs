// Run background-fixtures.py and Django first. Creates/deletes one temporary customization.
const assert = require('node:assert/strict');
const sessions = require('./session-fixture.cjs');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const fixture = sessions.create(), token = fixture.customerAccess;
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  let createdId;
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(token => localStorage.setItem('gc_access_token', token), token);
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__lab = () => ({ designManager, renderer });\n  return {\n    init, dispose') });
    });
    await page.goto(`${base}/crear-mi-remera/`);
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    const state = () => page.evaluate(() => GymCulture3D.getCustomizationState());
    const upload = async key => {
      await page.evaluate(() => { __lab().designManager.designs.slice().forEach(design => { __lab().designManager.select(design.id); GymCulture3D.removeSelectedDesign(); }); });
      await page.locator('#design-upload').setInputFiles(`.venv/custom-lab-artifacts/background/${key}.${key === 'D' ? 'jpg' : key === 'H' ? 'webp' : 'png'}`);
      await page.waitForSelector('#customizer-3d-container.is-placing');
      const canvas = page.locator('#customizer-3d-container canvas'); const box = await canvas.boundingBox();
      await canvas.click({ position: { x: box.width / 2, y: box.height * .46 } });
      await page.waitForSelector('#remove-background:visible');
    };
    const preview = async () => {
      await page.locator('#remove-background').click();
      await page.waitForFunction(() => document.querySelector('#background-preview-dialog').open);
      await page.waitForFunction(() => ['background-before', 'background-after'].every(id => document.getElementById(id).complete && document.getElementById(id).naturalWidth));
    };
    const textureAlpha = (x, y) => page.evaluate(({ x, y }) => {
      const manager = __lab().designManager, image = manager.resources.get(manager.designs[0].id).texture.image;
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
      const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
      const alpha = context.getImageData(x, y, 1, 1).data[3]; canvas.width = canvas.height = 0; return alpha;
    }, { x, y });
    await upload('A');
    let lastBackgroundRequest = Date.now();
    await page.locator('#design-scale').fill('1.25'); await page.locator('#design-scale').dispatchEvent('input');
    await page.locator('#design-rotation').fill('17'); await page.locator('#design-rotation').dispatchEvent('input');
    const original = await state();
    await preview(); assert.deepEqual(await state(), original);
    assert.ok((await page.locator('#background-preview-dialog').boundingBox()).width >= 850);
    await page.locator('#cancel-background').click(); assert.deepEqual(await state(), original);
    await preview(); await page.locator('#apply-background').click();
    await page.waitForFunction(() => !document.querySelector('#background-preview-dialog').open);
    let derived = await state();
    assert.equal(derived.designs[0].originalSource.dataUrl, original.designs[0].source.dataUrl);
    assert.notEqual(derived.designs[0].source.dataUrl, original.designs[0].source.dataUrl);
    assert.equal(derived.designs[0].backgroundRemoved, true);
    assert.equal(await textureAlpha(0, 0), 0);
    assert.deepEqual(derived.designs[0].position, original.designs[0].position);
    assert.equal(derived.designs[0].rotation, 17); assert.equal(derived.designs[0].scale, 1.25);
    const saved = await page.evaluate(async () => {
      const state = GymCulture3D.getCustomizationState(), previews = await GymCulture3D.capturePreviews({ size: 640 });
      const form = await GymCultureCustomizationApi.buildFormData({ productId: state.garment.productId, variantId: state.garment.variantId, state, previews, addToCart: false });
      return GymCultureCustomizationApi.create(form);
    });
    createdId = saved.id;
    assert.equal(saved.assets.length, 2);
    await page.evaluate(async saved => {
      await GymCulture3D.loadCustomization(saved.configuration);
      __lab().designManager.select(saved.configuration.designs[0].id);
    }, saved);
    derived = await state();
    assert.equal(derived.designs[0].backgroundRemoved, true);
    assert.ok(derived.designs[0].originalAssetUrl);
    assert.equal(await textureAlpha(0, 0), 0);
    assert.equal(derived.designs[0].rotation, 17); assert.equal(derived.designs[0].scale, 1.25);
    const originalId = derived.designs[0].originalAssetId;
    await preview();
    assert.ok(await page.locator('#apply-background').isDisabled());
    assert.ok(await page.locator('#background-restore-original').isVisible());
    await page.locator('#background-restore-original').click();
    await page.waitForFunction(() => !GymCulture3D.getCustomizationState().designs[0].backgroundRemoved);
    assert.equal(await textureAlpha(0, 0), 255);
    const updated = await page.evaluate(async id => {
      const state = GymCulture3D.getCustomizationState(), previews = await GymCulture3D.capturePreviews({ size: 640 });
      return GymCultureCustomizationApi.update(id, await GymCultureCustomizationApi.buildFormData({ productId: state.garment.productId, variantId: state.garment.variantId, state, previews, addToCart: false }));
    }, createdId);
    assert.equal(updated.assets.length, 1); assert.equal(updated.configuration.designs[0].assetId, originalId);
    console.log('PASS preview does not mutate; Cancel; Apply; original/derived stored separately; PNG alpha + transforms restored; original recoverable after save');
    for (const key of ['B', 'D', 'G', 'H', 'I', 'J', 'K']) {
      await upload(key); await preview();
      if (key === 'G') {
        const image = await page.locator('#background-before').evaluate(img => ({ width: img.clientWidth, height: img.clientHeight, naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight }));
        assert.ok(image.width <= image.naturalWidth && image.height <= image.naturalHeight, 'Small sources are not enlarged');
      }
      if (key === 'B') await page.locator('#background-preview-dialog').screenshot({ path: 'tools/custom-lab/background-preview.png' });
      await page.locator('#apply-background').click();
      await page.waitForFunction(() => !document.querySelector('#background-preview-dialog').open);
      assert.equal(await textureAlpha(0, 0), 0);
      if (['B', 'D', 'G', 'H'].includes(key)) assert.equal(await textureAlpha(key === 'G' ? 32 : 192, key === 'G' ? 44 : 266), 255, 'Enclosed white circle stays opaque');
      lastBackgroundRequest = Date.now();
    }
    // Respect the real production endpoint's 10/min processing throttle.
    while (Date.now() - lastBackgroundRequest < 61000) await page.waitForTimeout(Math.min(30000, 61000 - (Date.now() - lastBackgroundRequest)));
    for (const key of ['C', 'E', 'F']) {
      await upload(key); const before = await state();
      await page.locator('#remove-background').click();
      await page.waitForFunction(() => document.querySelector('#remove-background').textContent === 'QUITAR FONDO' && !document.querySelector('#remove-background').disabled);
      assert.equal(await page.locator('#background-preview-dialog').evaluate(element => element.open), false);
      assert.deepEqual(await state(), before);
      const feedback = await page.locator('#design-feedback').textContent();
      assert.ok(feedback.includes(key === 'F' ? 'ya tiene transparencia' : 'No pudimos separar el fondo de este diseño con suficiente precisión'), `${key}: ${feedback}`);
      if (key === 'E') await page.locator('.config-panel').screenshot({ path: 'tools/custom-lab/background-rejected.png' });
    }
    assert.deepEqual(errors, []);
    console.log('PASS logo, enclosed white, JPEG, 64px, WebP, gray/color/noisy backgrounds; unsafe/transparent unchanged; no JS errors');
  } finally {
    if (createdId) {
      const context = await browser.newContext();
      const response = await context.request.delete(`${base}/api/customizations/${createdId}/`, { headers: { Authorization: `Bearer ${token}` } });
      assert.equal(response.status(), 204); await context.close();
    }
    await browser.close();
    sessions.remove(fixture);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
