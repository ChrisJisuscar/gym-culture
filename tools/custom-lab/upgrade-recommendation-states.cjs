// One-time conversion of legacy recommendations using the actual Custom Lab.
// Existing IDs, metadata and designs are preserved; real WebP previews are saved.
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const sessions = require('./session-fixture.cjs');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const fixture = sessions.create();
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await sessions.login(page, fixture, base);
    page.on('pageerror', error => console.error('PAGE', error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.goto(`${base}/backoffice/recommendations/`);
    const data = await page.evaluate(async () => (await backofficeRequest('/api/backoffice/recommendations/')).json());
    for (const item of data.results.filter(item => !item.customization_state?.version && item.design_asset_url)) {
      await page.goto(`${base}/backoffice/recommendations/${item.id}/edit/`);
      await page.waitForFunction(() => !document.querySelector('#save-recommendation').disabled || document.querySelector('#recommendation-editor-feedback').classList.contains('is-error'));
      if (await page.locator('#save-recommendation').isDisabled()) throw new Error(await page.locator('#recommendation-editor-feedback').textContent());
      const saved = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith(`/recommendations/${item.id}/`));
      await page.locator('#save-recommendation').click();
      const response = await saved;
      if (!response.ok()) throw new Error(await response.text());
      await page.waitForFunction(() => document.querySelector('#recommendation-editor-feedback').textContent.startsWith('Recomendación guardada'));
      console.log(`UPGRADED ${item.id} ${item.name}`);
    }
  } finally { await browser.close(); sessions.remove(fixture); }
})().catch(error => { console.error(error); process.exitCode = 1; });
