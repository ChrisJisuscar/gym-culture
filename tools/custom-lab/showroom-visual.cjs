const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.on('pageerror', error => console.error('PAGE', error.message));
    await page.goto('http://127.0.0.1:8765/crear-mi-remera/');
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    await page.locator('#recommendation-viewer').scrollIntoViewIfNeeded();
    await page.waitForSelector('#recommendation-viewer.has-live-viewer');
    await page.addStyleTag({ content: '.nav-shell { visibility: hidden !important; }' });
    await page.locator('#recommendations-showroom').screenshot({ path: 'tools/custom-lab/showroom-desktop.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#recommendation-viewer').scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.locator('#recommendations-showroom').screenshot({ path: 'tools/custom-lab/showroom-mobile.png' });
    console.log('Captured desktop and mobile. Canvas count:', await page.locator('canvas').count());
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
