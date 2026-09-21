const assert = require('node:assert/strict');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const sessions = require('./session-fixture.cjs');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';

(async () => {
  const fixture = sessions.create();
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.addInitScript(token => localStorage.setItem('gc_access_token', token), fixture.customerAccess);
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__lab = () => ({ camera, controls, garmentMeshes, designManager });\n  return {\n    init, dispose') });
    });
    const ready = () => page.waitForFunction(() => window.GymCultureHistory && window.GymCultureEditorConfig && GymCulture3D.canEdit());
    const state = () => page.evaluate(() => GymCulture3D.getCustomizationState());
    const settle = () => page.waitForFunction(() => GymCulture3D.canEdit() && !GymCultureHistory.busy);
    const undo = async () => { await page.locator('#undo-design').click(); await settle(); };
    const redo = async () => { await page.locator('#redo-design').click(); await settle(); };
    const place = async () => {
      await page.waitForSelector('#customizer-3d-container.is-placing');
      const canvas = page.locator('#customizer-3d-container canvas'), box = await canvas.boundingBox();
      await canvas.click({ position: { x: box.width * .5, y: box.height * .46 } });
    };
    const selectLayer = id => page.locator(`[data-layer-id="${id}"] [data-layer-action="select"]`).click();
    const selected = () => page.evaluate(() => GymCulture3D.getSelectedDesign());
    const range = async (id, value) => page.locator(id).evaluate((element, value) => { element.value = value; element.dispatchEvent(new Event('input', { bubbles: true })); element.dispatchEvent(new Event('change', { bubbles: true })); }, String(value));
    const api = (url, options) => page.evaluate(async ({ url, options }) => GymCultureCustomizationApi.requestJson(url, options), { url, options });
    await page.goto(`${base}/crear-mi-remera/`); await ready();
    await page.locator('#new-text').fill('GYM CULTURE'); await page.locator('#add-3d-text').click(); await place();
    const first = (await state()).designs[0]; assert.ok(first);
    await undo(); assert.equal((await state()).designs.length, 0);
    await redo(); assert.equal((await selected()).id, first.id);
    await page.locator('[data-transform="duplicate"]').click();
    const second = await selected(); assert.notEqual(second.id, first.id); assert.notDeepEqual(second.position, first.position);
    await undo(); assert.equal((await state()).designs.length, 1); await redo();
    await selectLayer(second.id);
    await page.locator('[data-transform="flipX"]').click(); assert.equal((await selected()).flipX, true);
    await undo(); assert.equal((await selected()).flipX, false); await redo();
    await page.locator('[data-transform="flipY"]').click(); assert.equal((await selected()).flipY, true);
    await range('#design-scale', 1.2); assert.equal((await selected()).scale, 1.2);
    await undo(); assert.equal((await selected()).scale, 1); await redo();
    await range('#design-rotation', 25); assert.equal((await selected()).rotation, 25);
    await undo(); assert.equal((await selected()).rotation, 0); await redo();
    await page.locator('#selected-text').fill('FUERZA'); await page.locator('#selected-text').press('Tab');
    assert.equal((await selected()).text, 'FUERZA'); await undo(); assert.equal((await selected()).text, 'GYM CULTURE'); await redo();
    await page.locator('[data-align]').selectOption('center');
    const centered = await selected(); assert.ok(Math.abs(centered.position.x) < .00001);
    await undo(); assert.notDeepEqual((await selected()).position, centered.position); await redo();
    await page.locator(`[data-layer-id="${second.id}"] [data-layer-action="visibility"]`).click();
    assert.equal((await selected()).visibility, false);
    assert.equal(await page.evaluate(id => __lab().designManager.resources.get(id).mesh.visible, second.id), false);
    await undo(); assert.equal((await selected()).visibility, true); await redo();
    await page.locator('[data-transform="back"]').click();
    assert.equal((await state()).designs[0].id, second.id);
    assert.equal(await page.evaluate(id => __lab().designManager.resources.get(id).mesh.renderOrder, second.id), 2);
    await page.locator(`[data-layer-id="${second.id}"] [data-layer-action="visibility"]`).click();
    await selectLayer(first.id); await page.locator('#delete-design').click();
    assert.equal((await state()).designs.length, 1);
    await page.locator('#undo-design').focus(); await page.keyboard.press('Control+z'); await settle();
    assert.equal((await state()).designs.length, 2);
    await page.keyboard.press('Control+Shift+z'); await settle(); assert.equal((await state()).designs.length, 1);
    await page.keyboard.press('Control+z'); await settle(); await page.keyboard.press('Control+y'); await settle();
    assert.equal((await state()).designs.length, 1);
    console.log('PASS editor: text, undo/redo + shortcuts, duplicate, both flips, scale, rotation, alignment, real layer ordering/visibility and deletion');

    // Technical logo fixture, including a disconnected white interior.
    const png = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1800;
      const context = canvas.getContext('2d'); context.fillStyle = 'white'; context.fillRect(0, 0, 1800, 1800);
      context.fillStyle = 'black'; context.fillRect(430, 380, 940, 1040);
      context.fillStyle = 'white'; context.fillRect(780, 730, 240, 340);
      return canvas.toDataURL().split(',')[1];
    });
    await page.locator('#design-upload').setInputFiles({ name: 'quality-logo.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') }); await place();
    const imageId = (await selected()).id;
    const qualityBefore = await page.locator('#print-quality').getAttribute('title');
    assert.equal(await page.locator('#print-quality').getAttribute('data-level'), 'high');
    await range('#design-scale', 1.5); assert.equal(await page.locator('#print-quality').getAttribute('data-level'), 'medium');
    await range('#design-scale', 2.5); assert.equal(await page.locator('#print-quality').getAttribute('data-level'), 'low');
    assert.notEqual(await page.locator('#print-quality').getAttribute('title'), qualityBefore);
    await range('#design-scale', 1);
    await page.locator('#remove-background').click();
    await page.waitForSelector('#background-preview-dialog[open]', { timeout: 30000 });
    await page.locator('#apply-background').click(); await settle();
    const processed = await selected(); assert.equal(processed.id, imageId); assert.ok(processed.originalSource);
    await undo(); assert.equal(Boolean((await selected()).backgroundRemoved), false);
    await redo(); assert.equal((await selected()).backgroundRemoved, true);
    assert.equal(await page.evaluate(async () => {
      const state = GymCulture3D.getCustomizationState();
      const image = state.designs.find(design => design.type === 'image');
      image.assetUrl = '/missing-remote-file.png'; image.assetId = 'stale-id';
      const copied = await GymCultureCustomizationApi.editableCopy(state);
      const result = copied.designs.find(design => design.id === image.id);
      return result.source.dataUrl === image.source.dataUrl && !result.assetId && !result.assetUrl;
    }), true, 'Locally preserved assets remain usable after remote files are replaced');
    await page.locator('#restore-original').click(); await settle(); assert.equal((await selected()).backgroundRemoved, false);
    await undo(); assert.equal((await selected()).backgroundRemoved, true);
    console.log('PASS effective print quality changes with scale; background processing, apply, original restoration and undo/redo preserve logical identity');

    // One actual pointer gesture with many move events must produce one action.
    await page.locator('#customizer-3d-container').scrollIntoViewIfNeeded();
    const drag = await page.evaluate(async () => {
      const THREE = await import('/static/vendor/three/three.module.min.js');
      const point = new THREE.Vector3().copy(GymCulture3D.getSelectedDesign().position).project(__lab().camera);
      const rect = document.querySelector('#customizer-3d-container canvas').getBoundingClientRect();
      return { x: rect.x + (point.x + 1) * rect.width / 2, y: rect.y + (1 - point.y) * rect.height / 2, index: GymCultureHistory.index, position: GymCulture3D.getSelectedDesign().position };
    });
    await page.mouse.move(drag.x, drag.y); await page.mouse.down(); await page.mouse.move(drag.x + 35, drag.y + 12, { steps: 14 }); await page.mouse.up();
    assert.notDeepEqual((await selected()).position, drag.position);
    assert.equal(await page.evaluate(() => GymCultureHistory.index), drag.index + 1);
    await undo(); assert.deepEqual((await selected()).position, drag.position); await redo();
    await page.locator('[data-transform="flipX"]').click();
    await page.locator(`[data-layer-id="${second.id}"] [data-layer-action="visibility"]`).click();
    const savedState = await state();
    await page.locator('.customizer-layout').screenshot({ path: 'tools/custom-lab/workspace-desktop.png' });
    await page.locator('#save-design').click(); await page.locator('#saved-design-name').fill('Mi diseño de prueba');
    await page.locator('#save-design-dialog [type="submit"]').click(); await page.waitForURL('**/?saved=*');
    const savedId = new URL(page.url()).searchParams.get('saved');
    const draft = await api(`/api/saved-designs/${savedId}/`);
    assert.equal(draft.name, 'Mi diseño de prueba'); assert.equal(draft.customization_state.designs.length, 2);
    assert.equal(draft.customization_state.designs.find(design => design.id === imageId).flipX, true);
    assert.equal(draft.customization_state.designs.find(design => design.id === second.id).visibility, false);
    await page.goto(`${base}/mis-disenos/`); await page.waitForSelector('.saved-design-card img[src^="blob:"]');
    await page.locator('[data-saved-action="duplicate"]').click(); await page.waitForFunction(() => document.querySelectorAll('.saved-design-card').length === 2);
    await page.waitForFunction(() => !document.querySelector('#saved-design-list').inert && [...document.querySelectorAll('.saved-design-card img')].every(image => image.complete && image.naturalWidth));
    const copyId = await page.locator(`.saved-design-card:not([data-saved-id="${savedId}"])`).getAttribute('data-saved-id');
    await page.screenshot({ path: 'tools/custom-lab/saved-designs-desktop.png', fullPage: true });
    await page.locator(`[data-saved-id="${copyId}"] [data-saved-action="delete"]`).click();
    await page.locator('[data-cancel-delete]').click(); assert.equal(await page.locator('.saved-design-card').count(), 2);
    await page.locator(`[data-saved-id="${copyId}"] [data-saved-action="delete"]`).click();
    await page.locator('[data-confirm-delete]').click(); await page.waitForFunction(() => document.querySelectorAll('.saved-design-card').length === 1);
    await page.locator('.saved-design-card a').click(); await ready();
    await page.waitForFunction(id => GymCulture3D.getCustomizationState().designs.some(design => design.id === id), imageId);
    const restored = await state();
    for (const expected of savedState.designs) {
      const actual = restored.designs.find(design => design.id === expected.id);
      for (const key of ['position', 'normal', 'width', 'height', 'scale', 'rotation', 'flipX', 'flipY', 'visibility', 'layerOrder', 'backgroundRemoved']) assert.deepEqual(actual[key], expected[key], `Restored ${key}`);
    }
    assert.deepEqual(restored.garment, savedState.garment);
    await selectLayer(imageId); assert.equal((await selected()).source.dataUrl, processed.source.dataUrl);
    await page.locator('#save-design').click(); await page.locator('#saved-design-name').fill('Diseño actualizado');
    await page.locator('#save-design-dialog [type="submit"]').click(); await page.waitForSelector('#save-design-dialog:not([open])', { state: 'attached' });
    assert.equal((await api('/api/saved-designs/')).count, 1);
    const cartResponse = page.waitForResponse(response => /\/api\/customizations\/$/.test(response.url()) && response.request().method() === 'POST');
    await page.locator('#add-cart').click(); const commercial = await (await cartResponse).json();
    assert.ok(commercial.id, JSON.stringify(commercial));
    await api(`/api/saved-designs/${savedId}/`, { method: 'DELETE' });
    assert.equal((await api(`/api/customizations/${commercial.id}/`)).configuration.designs.length, 2);
    console.log('PASS private drafts: real save/edit/list/preview, independent duplication, confirmed deletion, complete restoration and independent cart copy');

    await page.locator('#generate-ai').click(); assert.equal(await page.locator('#ai-generation-dialog [type="submit"]').isDisabled(), true);
    await page.locator('[data-close-ai]').click();
    // The provider is disabled in this installation. Exercise its UI contract using a controlled image response.
    await page.route('**/api/customizations/generate-image/', route => route.fulfill({ json: { url: '/api/customizations/generated/00000000-0000-0000-0000-000000000001/' } }));
    await page.route('**/api/customizations/generated/*/', route => route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') }));
    await page.evaluate(() => { GymCultureEditorConfig.generation.enabled = true; });
    await page.locator('#generate-ai').click(); await page.locator('#generation-prompt').fill('Tigre violeta');
    await page.locator('#ai-generation-dialog [type="submit"]').click(); await page.locator('[data-use-generated]').click(); await place();
    assert.equal((await selected()).type, 'image'); assert.ok((await selected()).source.dataUrl.startsWith('data:image/png'));
    assert.equal(await page.locator('#remove-background').isVisible(), true);
    console.log('PASS optional AI: disabled state and controlled provider result enters the normal upload/background-removal pipeline');
    for (const garment of ['oversized', 'hoodie', 'tshirt']) {
      const previous = await state();
      const index = await page.evaluate(() => GymCultureHistory.index);
      await page.locator(`[data-garment="${garment}"]`).click(); await settle();
      await page.waitForFunction(type => GymCulture3D.getCustomizationState().garment.type === type, garment);
      if (previous.garment.type !== garment) {
        assert.equal(await page.evaluate(() => GymCultureHistory.index), index + 1, 'One action for garment and variant changes');
        await undo(); assert.deepEqual((await state()).garment, previous.garment); await redo();
      }
      if (!(await state()).designs.length) { await page.locator('#add-3d-text').click(); await place(); }
      else await selectLayer((await state()).designs.at(-1).id);
      await page.locator('[data-align]').selectOption('center');
      assert.ok(Math.abs((await selected()).position.x) < .00001, `Aligned ${garment}`);
      if (garment === 'hoodie') {
        await page.locator('[data-hood-state="down"]').click();
        assert.equal((await state()).garment.hoodState, 'down');
        await page.locator('[data-hood-state="up"]').click();
        await undo(); assert.equal((await state()).garment.hoodState, 'down'); await redo();
        assert.equal((await state()).garment.hoodState, 'up');
      }
    }
    console.log('PASS garment/hood history and alignment on tshirt, oversized and hoodie');
    const beforeColor = (await state()).garment.color;
    const color = page.locator('.color-option:not(.is-selected):not([hidden])').first();
    if (await color.count()) { await color.click(); await undo(); assert.equal((await state()).garment.color, beforeColor); await redo(); }
    const beforeSize = (await state()).garment.size;
    const size = page.locator('.size-option:not(.is-selected):not([hidden])').first();
    if (await size.count()) { await size.click(); await undo(); assert.equal((await state()).garment.size, beforeSize); await redo(); }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#selection-panel').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: 'tools/custom-lab/workspace-mobile.png' });
    assert.deepEqual(errors, []);
    console.log('PASS desktop/mobile workspace, no overflow or JavaScript errors');
  } finally { await browser.close(); sessions.remove(fixture); }
})().catch(error => { console.error(error); process.exitCode = 1; });
