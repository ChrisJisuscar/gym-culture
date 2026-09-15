// Uses real elapsed browser time, including a deliberately throttled 5 FPS run.
const assert = require('node:assert/strict');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    for (const mode of process.argv[2] ? [process.argv[2]] : ['desktop', 'mobile', '5fps']) {
      const context = await browser.newContext({ viewport: mode === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1100 }, hasTouch: mode === 'mobile', reducedMotion: 'no-preference' });
      const page = await context.newPage(), errors = [], failures = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => { if (response.url().includes('/api/') && response.status() >= 400) failures.push(`${response.status()} ${response.url()}`); });
      await page.route('**/js/showroom-orbit.js', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, body: (await response.text()).replace('this.angle = Math.PI / 2;', 'window.__orbit = this; this.angle = Math.PI / 2;') });
      });
      await page.route('**/js/customizer-3d.js', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__engine = () => ({ scene, renderer, controls });\n  return {\n    init, dispose') });
      });
      await page.addInitScript(slow => {
        const request = window.requestAnimationFrame.bind(window), cancel = window.cancelAnimationFrame.bind(window);
        window.__frames = new Map(); let serial = 0;
        window.requestAnimationFrame = callback => {
          const id = ++serial, start = performance.now();
          const frame = time => {
            if (slow && time - start < 200) { __frames.set(id, request(frame)); return; }
            __frames.delete(id); callback(time);
          };
          __frames.set(id, request(frame)); return id;
        };
        window.cancelAnimationFrame = id => { cancel(__frames.get(id)); __frames.delete(id); };
      }, mode === '5fps');
      await page.goto(`${base}/crear-mi-remera/?culture=urban`);
      await page.waitForFunction(() => window.GymCulture3D?.isReady());
      const ready = async () => {
        await page.locator('#recommendation-viewer').scrollIntoViewIfNeeded();
        await page.waitForFunction(() => GymCulture3D.isPreviewActive() && !document.querySelector('#use-recommendation').disabled && __orbit.visible);
      };
      const snapshot = () => page.evaluate(() => ({ angle: __orbit.angle, time: performance.now(), style: document.querySelector('.orbit-preview').style.transform }));
      const moving = async (label, ms, fullSpeed = false) => {
        const before = await snapshot(); await page.waitForTimeout(ms); const after = await snapshot();
        const delta = after.angle - before.angle, seconds = (after.time - before.time) / 1000;
        assert.ok(delta > .08, `${mode}: ${label} stopped (${delta})`);
        assert.notEqual(after.style, before.style);
        if (fullSpeed) assert.ok(Math.abs(delta / seconds - Math.PI * 2 / 30) < .025, `Rotation period depends on FPS: ${delta / seconds}`);
        console.log(`PASS ${mode}: ${label}: ${(delta * 180 / Math.PI).toFixed(1)} degrees / ${seconds.toFixed(1)} seconds`);
      };
      await ready();
      assert.equal(await page.locator('[data-showroom-motion]').count(), 0);
      await page.evaluate(() => { window.__identity = __engine(); });
      await moving('untouched autoplay', 10000, true);
      if (mode === '5fps') { assert.deepEqual(errors, []); await context.close(); continue; }
      await page.locator('#showroom-stage').scrollIntoViewIfNeeded();
      const box = await page.locator('.orbit-preview:visible').first().boundingBox();
      const x = box.x + box.width / 2, y = box.y + box.height / 2;
      let touch;
      if (mode === 'mobile') {
        touch = await context.newCDPSession(page);
        await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      } else { await page.mouse.move(x, y); await page.mouse.down(); }
      assert.equal(await page.evaluate(() => !!__orbit.drag), true);
      const held = await snapshot(); await page.waitForTimeout(350); assert.equal((await snapshot()).angle, held.angle);
      if (touch) {
        for (let offset = 10; offset <= 50; offset += 10) await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + offset, y }] });
        await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await touch.detach();
      } else { await page.mouse.move(x + 80, y, { steps: 12 }); await page.mouse.up(); }
      assert.equal(await page.evaluate(() => __orbit.drag), null);
      assert.notEqual((await snapshot()).angle, held.angle);
      await page.waitForTimeout(3300); await moving('resumes after drag', 2200, true);
      for (const direction of ['next', 'prev']) {
        const before = await page.locator('#recommendation-title').textContent();
        await page.locator(`[data-showroom-${direction}]`).click(); await ready();
        assert.notEqual(await page.locator('#recommendation-title').textContent(), before);
        await moving(direction, 1800, true);
      }
      await page.locator('[data-culture="anime"]').click(); await ready();
      await page.waitForFunction(() => document.querySelector('#recommendation-details').textContent.includes('ANIME'));
      await moving('culture change', 1800, true);
      await page.locator('[data-garment="hoodie"]').click(); await ready();
      await page.waitForFunction(() => document.querySelector('#recommendation-details').textContent.includes('Hoodie'));
      await moving('garment change', 1800, true);
      assert.equal(await page.evaluate(() => __frames.size), 1);
      assert.equal(await page.evaluate(() => ['scene', 'renderer', 'controls'].every(key => __engine()[key] === __identity[key])), true);
      assert.equal(await page.locator('canvas').count(), 1);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await moving('autoplay has no manual or media toggle', 1200, true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(errors, []); assert.deepEqual(failures, []);
      await page.addStyleTag({ content: '.nav-shell { visibility: hidden !important; }' });
      await page.locator('#recommendations-showroom').screenshot({ path: `tools/custom-lab/showroom-autoplay-${mode}.png` });
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
