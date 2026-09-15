const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } }), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__lab = () => ({ camera, controls, garmentMeshes, garmentSize, garmentRadius, designManager, renderer });\n  return {\n    init, dispose') });
    });
    await page.goto(`${base}/crear-mi-remera/`);
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    const textFits = await page.evaluate(async () => {
      const { createTextTexture, TEXT_FONTS } = await import('/static/js/customizer-3d/text-texture.js');
      return TEXT_FONTS.every(fontFamily => ['GYM CULTURE', 'W'.repeat(50)].every(text => {
        const { texture } = createTextTexture({ text, fontFamily });
        const canvas = texture.image, width = canvas.width, pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        let left = canvas.width, right = 0;
        for (let index = 3; index < pixels.length; index += 4) if (pixels[index] > 0) { const x = ((index - 3) / 4) % canvas.width; left = Math.min(left, x); right = Math.max(right, x); }
        texture.dispose(); canvas.width = canvas.height = 0;
        return left >= 40 && right <= width - 40;
      }));
    });
    assert.ok(textFits, 'Text textures preserve glyphs and horizontal padding at maximum length');
    assert.equal(await page.evaluate(() => document.querySelector('.customizer-layout').compareDocumentPosition(document.querySelector('#culturas')) & Node.DOCUMENT_POSITION_FOLLOWING), 4);
    assert.equal(await page.evaluate(() => document.querySelector('#culturas').compareDocumentPosition(document.querySelector('#recommendations-showroom')) & Node.DOCUMENT_POSITION_FOLLOWING), 4);
    assert.equal(await page.locator('[data-showroom-motion]').count(), 0);
    await page.locator('[data-garment="oversized"]').click();
    await page.waitForFunction(() => GymCulture3D.isReady() && GymCultureCustomizer.state.garmentType === 'oversized');
    await page.evaluate(() => GymCulture3D.setColor('#ebe9e4'));
    const reports = [];
    for (const kind of ['square', 'text', 'vertical', 'wide', 'transparent']) {
      await page.evaluate(() => { const manager = __lab().designManager; manager.designs.slice().forEach(design => { manager.select(design.id); manager.removeSelected(); }); });
      if (kind === 'text') { await page.locator('#new-text').fill('GYM CULTURE'); await page.locator('#add-3d-text').click(); }
      else await page.locator('#design-upload').setInputFiles(`.venv/custom-lab-artifacts/projection/${kind}.png`);
      await page.waitForSelector('#customizer-3d-container.is-placing');
      const canvas = page.locator('#customizer-3d-container canvas'), box = await canvas.boundingBox();
      await canvas.click({ position: { x: box.width / 2, y: box.height * .46 } });
      await page.waitForFunction(() => __lab().designManager.designs.length === 1);
      const row = await page.evaluate(async kind => {
        const THREE = await import('/static/vendor/three/three.module.min.js');
        const { garmentSurfaceHit } = await import('/static/js/customizer-3d/raycast-manager.js');
        const lab = __lab(), manager = lab.designManager, design = manager.designs[0], id = design.id;
        const ray = new THREE.Raycaster(), coverages = [];
        const size = kind === 'vertical' ? [.11, .32] : kind === 'wide' || kind === 'text' ? [.25, .085] : [.2, .2];
        Object.assign(design, { width: size[0], height: size[1] });
        for (const [x, y] of [[0, .12], [0, .25], [0, -.24], [-.1, -.1], [.1, -.1]]) {
          ray.set(new THREE.Vector3(x, y, 2), new THREE.Vector3(0, 0, -1));
          manager.moveSelected(garmentSurfaceHit(ray.intersectObjects(lab.garmentMeshes)[0], ray.ray.direction));
          for (const [scale, rotation] of [[.8, -20], [1.15, 25], [1, 0]]) {
            manager.updateSelected({ scale, rotation });
            const uv = manager.resources.get(id).mesh.geometry.attributes.uv;
            const mask = document.createElement('canvas'); mask.width = mask.height = 128;
            const ctx = mask.getContext('2d'); ctx.fillStyle = 'white';
            for (let i = 0; i < uv.count; i += 3) {
              ctx.beginPath(); ctx.moveTo(uv.getX(i) * 128, uv.getY(i) * 128);
              ctx.lineTo(uv.getX(i + 1) * 128, uv.getY(i + 1) * 128); ctx.lineTo(uv.getX(i + 2) * 128, uv.getY(i + 2) * 128); ctx.closePath(); ctx.fill();
            }
            const pixels = ctx.getImageData(0, 0, 128, 128).data;
            let count = 0; for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 128) count++;
            coverages.push(count / 16384);
            mask.width = mask.height = 0;
          }
        }
        ray.set(new THREE.Vector3(0, .06, 2), new THREE.Vector3(0, 0, -1));
        manager.moveSelected(garmentSurfaceHit(ray.intersectObjects(lab.garmentMeshes)[0], ray.ray.direction));
        manager.select(null);
        return { kind, minimumCoverage: Math.min(...coverages), cases: coverages.length, idPreserved: manager.designs[0].id === id };
      }, kind);
      reports.push(row); assert.ok(row.idPreserved); assert.ok(row.minimumCoverage >= .96, JSON.stringify(row));
      await page.locator('.editor-panel').screenshot({ path: `tools/custom-lab/oversize-${kind}.png` });
      const state = await page.evaluate(() => GymCulture3D.getCustomizationState());
      await page.evaluate(async state => GymCulture3D.loadCustomization(state), state);
      assert.deepEqual(await page.evaluate(() => GymCulture3D.getCustomizationState().designs), state.designs);
      const unchanged = await page.evaluate(() => {
        const manager = __lab().designManager, design = manager.designs[0];
        manager.select(design.id);
        const before = JSON.stringify(design), resource = manager.resources.get(design.id), geometry = resource.mesh.geometry;
        try { manager.updateSelected({ position: { x: 10, y: 10, z: 10 }, text: 'INVALID ZONE' }); return false; }
        catch { return JSON.stringify(design) === before && resource.mesh.geometry === geometry; }
      });
      assert.ok(unchanged, 'Invalid projection preserves state and geometry');
    }
    fs.writeFileSync('.venv/custom-lab-artifacts/projection/qa.json', JSON.stringify(reports, null, 2));
    console.log('PASS Oversize: five design types, 75 move/scale/rotation cases, intact UV coverage and restored state');
    for (const garment of ['oversized', 'tshirt', 'hoodie']) {
      await page.locator(`[data-garment="${garment}"]`).click();
      await page.waitForFunction(type => GymCulture3D.isReady() && GymCultureCustomizer.state.garmentType === type, garment);
      const canvas = page.locator('#customizer-3d-container canvas'); await canvas.hover();
      const before = await page.evaluate(() => __lab().camera.position.distanceTo(__lab().controls.target));
      await page.mouse.wheel(0, -4000); await page.waitForTimeout(1000);
      const zoom = await page.evaluate(() => ({ distance: __lab().camera.position.distanceTo(__lab().controls.target), min: __lab().controls.minDistance, radius: __lab().garmentRadius }));
      assert.ok(zoom.distance < before * .7, JSON.stringify({ garment, before, zoom }));
      assert.ok(zoom.distance >= zoom.radius + .02);
      await canvas.screenshot({ path: `tools/custom-lab/zoom-${garment}.png` });
    }
    await page.locator('.desktop-nav a').filter({ hasText: 'TIENDA' }).click(); await page.waitForURL('**/#home');
    assert.ok(await page.locator('#home').isVisible());
    await page.locator('.desktop-nav a').filter({ hasText: 'CULTURAS' }).click(); await page.waitForURL('**/crear-mi-remera/#culturas');
    await page.waitForTimeout(1000);
    assert.ok(Math.abs((await page.locator('#culturas').boundingBox()).y - 110) < 40);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#customizer-3d-container').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => GymCulture3D.isReady());
    const touchCanvas = await page.locator('#customizer-3d-container canvas').boundingBox();
    const touch = await page.context().newCDPSession(page);
    const cx = touchCanvas.x + touchCanvas.width / 2, cy = touchCanvas.y + touchCanvas.height / 2;
    const distanceBefore = await page.evaluate(() => __lab().camera.position.distanceTo(__lab().controls.target));
    const fingers = distance => [{ id: 1, x: cx - distance, y: cy }, { id: 2, x: cx + distance, y: cy }];
    await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: fingers(35) });
    for (const distance of [50, 70, 90, 110]) await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: fingers(distance) });
    await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(500);
    assert.ok(await page.evaluate(before => __lab().camera.position.distanceTo(__lab().controls.target) < before * .8, distanceBefore));
    await touch.detach();
    await page.locator('.menu-toggle').click(); await page.locator('.mobile-menu a').filter({ hasText: /^Tienda$/i }).click(); await page.waitForURL('**/#home');
    await page.locator('.menu-toggle').click(); await page.locator('.mobile-menu a').filter({ hasText: /^Culturas$/i }).click(); await page.waitForURL('**/crear-mi-remera/#culturas');
    await page.waitForTimeout(1000);
    assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: 'tools/custom-lab/cultures-below-lab-mobile.png' });
    assert.deepEqual(errors, []);
    console.log('PASS closer safe zoom on three garments, cultures below Lab, navbar desktop/mobile targets and no JS errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
