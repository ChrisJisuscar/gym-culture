const assert = require('node:assert/strict');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__layoutEngine = () => ({ preview, camera });\n  return {\n    init, dispose') });
    });
    await page.route('**/js/showroom-orbit.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replace('this.angle = Math.PI / 2;', 'window.__layoutOrbit = this; this.angle = Math.PI / 2;') });
    });
    await page.goto(`${process.env.LAB_URL || 'http://127.0.0.1:8765'}/crear-mi-remera/`);
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    for (const width of [1440, 900, 390, 320]) {
      await page.setViewportSize({ width, height: 1100 });
      for (const type of ['tshirt', 'oversized', 'hoodie']) {
        await page.locator(`[data-garment="${type}"]`).click();
        await page.waitForFunction(type => GymCulture3D.isReady() && GymCultureCustomizer.state.garmentType === type, type);
        await page.locator('#recommendation-viewer').scrollIntoViewIfNeeded();
        await page.waitForFunction(type => !document.querySelector('#use-recommendation').disabled && __layoutEngine().preview?.type === type && GymCulture3D.isPreviewActive(), type);
        const result = await page.evaluate(async () => {
          const { Box3, Vector3 } = await import('/static/vendor/three/three.module.min.js');
          const { preview, camera } = __layoutEngine();
          const viewer = document.querySelector('#recommendation-viewer').getBoundingClientRect();
          preview.model.updateMatrixWorld(true); camera.updateMatrixWorld(true);
          const bounds = new Box3().setFromObject(preview.model);
          const projected = [];
          for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) {
            const point = new Vector3(x, y, z).project(camera);
            projected.push({ x: viewer.x + (point.x + 1) * viewer.width / 2, y: viewer.y + (1 - point.y) * viewer.height / 2 });
          }
          const garment = { left: Math.min(...projected.map(p => p.x)), right: Math.max(...projected.map(p => p.x)), top: Math.min(...projected.map(p => p.y)), bottom: Math.max(...projected.map(p => p.y)) };
          const intersect = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
          let modelCollisions = 0, previewCollisions = 0, firstCollision;
          for (let step = 0; step < 72; step++) {
            __layoutOrbit.angle = step * Math.PI / 36; __layoutOrbit.layout();
            const cards = __layoutOrbit.buttons.filter(b => b.style.visibility !== 'hidden').map(b => b.getBoundingClientRect());
            if (cards.some(b => intersect(b, garment))) { modelCollisions++; firstCollision ||= { step, garment, viewer: viewer.toJSON(), cards: cards.map(b => b.toJSON()) }; }
            if (cards.some((a, i) => cards.slice(i + 1).some(b => intersect(a, b)))) previewCollisions++;
          }
          return { modelCollisions, previewCollisions, firstCollision, overflow: document.documentElement.scrollWidth > innerWidth };
        });
        const { firstCollision, ...metrics } = result;
        assert.deepEqual(metrics, { modelCollisions: 0, previewCollisions: 0, overflow: false }, JSON.stringify({ width, type, firstCollision }));
      }
    }
    console.log('PASS full orbit at 72 angles, three garments, 1440/900/390/320px: no visible preview overlap or model obstruction');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
