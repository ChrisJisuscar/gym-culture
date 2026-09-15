const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const session = require('./session-fixture.cjs');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const fixture = session.create();
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  let context; const created = []; const cultureIds = [];
  try {
    context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
    const page = await context.newPage(), errors = [], adminHeaders = [], networkErrors = [];
    page.on('pageerror', error => errors.push(error.message)); page.on('dialog', dialog => dialog.accept());
    page.on('request', request => { if (request.url().includes('/api/backoffice/')) adminHeaders.push(request.headers()); });
    page.on('response', response => { if (response.url().includes('/api/backoffice/') && response.status() >= 400) networkErrors.push(`${response.status()} ${response.url()}`); });
    await context.addInitScript(token => { if (!localStorage.getItem('gc_access_token')) localStorage.setItem('gc_access_token', token); }, fixture.customerAccess);
    await page.goto(`${base}/backoffice/recommendations/new/`);
    assert.ok(page.url().includes('/backoffice/login/'));
    await page.locator('#id_username').fill(fixture.customer); await page.locator('#id_password').fill(fixture.password); await page.locator('button[type="submit"]').click();
    assert.ok(await page.locator('.bo-auth-error').isVisible());
    await page.locator('.bo-auth-card').screenshot({ path: 'tools/custom-lab/backoffice-session-login.png' });
    await session.login(page, fixture, base);
    assert.equal(await page.evaluate(() => localStorage.getItem('gc_access_token')), fixture.customerAccess);
    const cookie = (await context.cookies()).find(cookie => cookie.name === 'sessionid');
    assert.ok(cookie.httpOnly); assert.equal(cookie.sameSite, 'Lax');
    for (const section of ['orders', 'production', 'products', 'stock', 'customers']) {
      await page.goto(`${base}/backoffice/${section}/`);
      await page.waitForFunction(() => { const feedback = document.querySelector('#bo-feedback'); return feedback && !/Cargando|Actualizando/.test(feedback.textContent); });
      assert.equal(await page.locator('#bo-feedback.is-error').count(), 0);
    }
    const req = async (url, options = {}) => {
      const csrf = (await context.cookies()).find(cookie => cookie.name === 'csrftoken').value;
      return context.request.fetch(`${base}${url}`, { ...options, headers: { ...options.headers, 'X-CSRFToken': csrf } });
    };
    const noCsrf = await context.request.post(`${base}/api/backoffice/recommendations/cultures/`, { data: { name: 'Blocked', slug: 'blocked' } });
    assert.equal(noCsrf.status(), 403);
    const createCulture = async label => {
      const slug = `${fixture.admin}-${label}`;
      const response = await req('/api/backoffice/recommendations/cultures/', { method: 'POST', data: { slug, name: `QA ${label}` } });
      assert.equal(response.status(), 201, await response.text());
      const id = (await (await req('/api/backoffice/recommendations/cultures/')).json()).find(item => item.slug === slug).id;
      cultureIds.push(id); return id;
    };
    const culture = await createCulture('order'), otherCulture = await createCulture('other');
    const picture = fs.readFileSync('.venv/custom-lab-artifacts/background/B.png');
    for (let i = 0; i < 5; i++) {
      const response = await req('/api/backoffice/recommendations/', { method: 'POST', multipart: { name: `QA design ${i + 1}`, culture: i === 4 ? otherCulture : culture, garment_type: 'tshirt', active: 'true', preview_image: { name: 'preview.png', mimeType: 'image/png', buffer: picture }, design_asset: { name: 'art.png', mimeType: 'image/png', buffer: picture } } });
      assert.equal(response.status(), 201, await response.text()); created.push((await response.json()).id);
    }
    await page.goto(`${base}/backoffice/recommendations/`);
    await page.locator('#recommendation-culture-filter').selectOption(String(culture));
    const ids = () => page.locator('[data-recommendation-id]').evaluateAll(rows => rows.map(row => Number(row.dataset.recommendationId)));
    await page.waitForFunction(() => document.querySelectorAll('[data-recommendation-id]').length === 4);
    const handle = await page.locator(`[data-recommendation-id="${created[1]}"] .bo-drag-handle`).boundingBox();
    const first = await page.locator(`[data-recommendation-id="${created[0]}"]`).boundingBox();
    const reorder = page.waitForResponse(response => response.url().endsWith('/recommendations/reorder/') && response.request().method() === 'POST');
    await page.mouse.move(handle.x + 12, handle.y + 15); await page.mouse.down(); await page.mouse.move(first.x + 100, first.y + 8, { steps: 10 }); await page.mouse.up();
    assert.equal((await reorder).status(), 200);
    await page.waitForFunction(() => document.querySelector('#bo-feedback').textContent.startsWith('Orden guardado'));
    assert.deepEqual(await ids(), [created[1], created[0], created[2], created[3]]);
    await page.reload(); await page.locator('#recommendation-culture-filter').selectOption(String(culture));
    await page.waitForFunction(() => document.querySelectorAll('[data-recommendation-id]').length === 4);
    assert.deepEqual(await ids(), [created[1], created[0], created[2], created[3]]);
    await page.locator(`[data-recommendation-id="${created[2]}"] [data-move-recommendation="-1"]`).click();
    await page.waitForFunction(id => Number(document.querySelectorAll('[data-recommendation-id]')[1].dataset.recommendationId) === id, created[2]);
    const other = await (await req(`/api/backoffice/recommendations/${created[4]}/`)).json(); assert.equal(other.sort_order, 1);
    await page.screenshot({ path: 'tools/custom-lab/backoffice-reorder.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    const touchHandle = page.locator(`[data-recommendation-id="${created[2]}"] .bo-drag-handle`);
    await touchHandle.scrollIntoViewIfNeeded();
    const touchBox = await touchHandle.boundingBox(), targetBox = await page.locator(`[data-recommendation-id="${created[1]}"]`).boundingBox();
    const cdp = await context.newCDPSession(page);
    const touchReorder = page.waitForResponse(response => response.url().endsWith('/recommendations/reorder/') && response.request().method() === 'POST');
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: touchBox.x + 12, y: touchBox.y + 12 }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: targetBox.x + 50, y: targetBox.y + 8 }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    assert.equal((await touchReorder).status(), 200); await cdp.detach();
    await page.waitForFunction(id => Number(document.querySelector('[data-recommendation-id]').dataset.recommendationId) === id, created[2]);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: 'tools/custom-lab/backoffice-reorder-mobile.png' });
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.locator(`[data-edit-recommendation="${created[0]}"]`).click();
    await page.waitForFunction(() => window.GymCulture3D?.isReady() && !document.querySelector('#save-recommendation').disabled);
    assert.equal(await page.locator('script[src*="auth-session.js"]').count(), 0);
    assert.equal(await page.locator('[name="sort_order"]').count(), 0);
    await page.locator('#new-text').fill('SESSION QA'); await page.locator('#add-3d-text').click();
    const canvas = page.locator('#customizer-3d-container canvas'), box = await canvas.boundingBox();
    await canvas.click({ position: { x: box.width / 2, y: box.height * .59 } });
    const save = page.waitForResponse(response => response.url().endsWith(`/recommendations/${created[0]}/`) && response.request().method() === 'PATCH');
    await page.locator('#save-recommendation').click(); const saved = await save;
    assert.equal(saved.status(), 200, await saved.text()); const item = await saved.json();
    assert.ok(item.preview_url.endsWith('.webp')); assert.equal(item.id, created[0]);
    assert.ok(item.customization_state.designs.some(design => design.text === 'SESSION QA'));
    await page.waitForFunction(() => document.querySelector('#recommendation-editor-feedback').textContent.startsWith('Recomendación guardada'));
    await page.reload(); await page.waitForFunction(() => window.GymCulture3D?.isReady() && !document.querySelector('#save-recommendation').disabled);
    assert.ok(await page.evaluate(() => GymCulture3D.getCustomizationState().designs.some(design => design.text === 'SESSION QA')));
    await page.screenshot({ path: 'tools/custom-lab/recommendation-session-editor.png', fullPage: true });
    assert.ok(adminHeaders.length > 8); assert.ok(adminHeaders.every(headers => !headers.authorization));
    assert.deepEqual(errors, []);
    assert.deepEqual(networkErrors, []);
    for (const id of created.splice(0)) assert.equal((await req(`/api/backoffice/recommendations/${id}/`, { method: 'DELETE' })).status(), 204);
    await page.locator('form[action="/backoffice/logout/"] button').click(); await page.waitForURL('**/backoffice/login/');
    assert.equal(await page.evaluate(() => localStorage.getItem('gc_access_token')), fixture.customerAccess);
    assert.equal((await context.request.get(`${base}/api/auth/me/`, { headers: { Authorization: `Bearer ${fixture.customerAccess}` } })).status(), 200);
    assert.equal((await context.request.get(`${base}/api/backoffice/recommendations/`)).status(), 403);
    console.log('PASS session login/logout, customer rejection, CSRF, independent JWT, all Backoffice sections, mouse/touch reorder + reload + fallback, cultures independent, editor restore/save/preview without JWT, no JS or unexpected HTTP errors');
  } finally {
    // Only test-owned rows/users are removed. Existing administrator accounts and designs are untouched.
    const { execFileSync } = require('node:child_process'), path = require('node:path');
    execFileSync(path.resolve('.venv/Scripts/python.exe'), ['backend/manage.py', 'shell', '-c', "import json,sys; from recommendations.models import Culture; ids=json.load(sys.stdin); Culture.objects.filter(pk__in=ids,slug__startswith='qa-session-').delete()"], { input: JSON.stringify(cultureIds), encoding: 'utf8' });
    await browser.close(); session.remove(fixture);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
