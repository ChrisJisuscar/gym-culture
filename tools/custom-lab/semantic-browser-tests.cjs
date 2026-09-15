// Uses a public rembg fixture and real local inference. No saved customer data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } }), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/crear-mi-remera/`);
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    await page.locator('#design-upload').setInputFiles('.venv/custom-lab-artifacts/semantic/anime-girl-2.jpg');
    await page.waitForSelector('#customizer-3d-container.is-placing');
    const canvas = page.locator('#customizer-3d-container canvas'), box = await canvas.boundingBox();
    await canvas.click({ position: { x: box.width / 2, y: box.height * .46 } });
    const original = await page.evaluate(() => GymCulture3D.getCustomizationState());
    const started = Date.now();
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/remove-background/'), { timeout: 240000 });
    await page.locator('#remove-background').click();
    assert.equal(await page.locator('#remove-background').textContent(), 'PROCESANDO...');
    // A browser input remains usable during ONNX inference on the server.
    await page.locator('#new-text').fill('UI RESPONSIVE');
    const response = await responsePromise;
    assert.equal(response.status(), 200, await response.text());
    assert.equal(response.headers()['x-background-strategy'], 'semantic');
    await page.waitForFunction(() => document.querySelector('#background-preview-dialog').open);
    await page.waitForFunction(() => document.querySelector('#background-after').complete);
    assert.deepEqual(await page.evaluate(() => GymCulture3D.getCustomizationState()), original);
    const dialog = page.locator('#background-preview-dialog');
    assert.ok((await dialog.boundingBox()).width >= 850);
    await dialog.screenshot({ path: 'tools/custom-lab/semantic-preview-desktop.png' });
    await page.locator('[data-background-view="native"]').click();
    assert.equal(await dialog.evaluate(element => element.classList.contains('is-native')), true);
    await page.locator('[data-background-view="fit"]').click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok((await dialog.boundingBox()).width <= 390);
    await dialog.screenshot({ path: 'tools/custom-lab/semantic-preview-mobile.png' });
    await page.locator('#apply-background').click();
    await page.waitForFunction(() => !document.querySelector('#background-preview-dialog').open);
    const processed = await page.evaluate(() => GymCulture3D.getCustomizationState());
    assert.equal(processed.designs[0].id, original.designs[0].id);
    assert.ok(processed.designs[0].backgroundRemoved);
    await page.locator('#remove-background').click();
    await page.locator('#background-restore-original').click();
    await page.waitForFunction(() => !GymCulture3D.getCustomizationState().designs[0].backgroundRemoved);
    const restored = await page.evaluate(() => GymCulture3D.getCustomizationState());
    assert.equal(restored.designs[0].source.dataUrl, original.designs[0].source.dataUrl);
    assert.deepEqual(restored.designs[0].position, original.designs[0].position);
    assert.deepEqual(errors, []);
    fs.writeFileSync('.venv/custom-lab-artifacts/semantic/browser.json', JSON.stringify({ requestSeconds: (Date.now() - started) / 1000, errors, strategy: 'semantic' }));
    console.log('PASS real semantic endpoint, responsive UI, desktop/mobile comparison, native inspection, confirm/restore and no JS errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
