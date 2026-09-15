const fs = require('node:fs');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
const base = process.env.LAB_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('\r\n', '\n').replace('  return {\n    init, dispose', '  window.__lab = () => ({ scene, camera, controls, garmentMeshes, garmentSize, designManager, renderer });\n  return {\n    init, dispose') });
    });
    await page.goto(`${base}/crear-mi-remera/`);
    await page.waitForFunction(() => window.GymCulture3D?.isReady());
    await page.locator('[data-garment="oversized"]').click();
    await page.waitForFunction(() => GymCulture3D.isReady() && GymCultureCustomizer.state.garmentType === 'oversized');
    await page.evaluate(() => GymCulture3D.setColor('#ebe9e4'));
    const metrics = await page.evaluate(async () => {
      const THREE = await import('/static/vendor/three/three.module.min.js');
      const { garmentSurfaceHit } = await import('/static/js/customizer-3d/raycast-manager.js');
      const lab = __lab(), raycaster = new THREE.Raycaster(), rows = [];
      for (const y of [.25, .12, 0, -.16, -.28]) for (const x of [-.13, 0, .13]) {
        raycaster.set(new THREE.Vector3(x, y, 2), new THREE.Vector3(0, 0, -1));
        const hit = raycaster.intersectObjects(lab.garmentMeshes)[0];
        if (!hit) { rows.push({ x, y, miss: true }); continue; }
        const normal = garmentSurfaceHit(hit, raycaster.ray.direction).normal;
        lab.designManager.prepareText({ text: 'GYM CULTURE', fontFamily: 'Arial', color: '#8027d4' });
        const design = lab.designManager.place({ point: hit.point, normal, mesh: hit.object });
        design.width = .25; design.height = .14; design.scale = 1;
        lab.designManager.rebuild(design, hit.object);
        const geometry = lab.designManager.resources.get(design.id).mesh.geometry, uv = geometry.attributes.uv;
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
        const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white';
        for (let i = 0; i < uv.count; i += 3) {
          ctx.beginPath(); ctx.moveTo(uv.getX(i) * 256, uv.getY(i) * 256);
          ctx.lineTo(uv.getX(i + 1) * 256, uv.getY(i + 1) * 256); ctx.lineTo(uv.getX(i + 2) * 256, uv.getY(i + 2) * 256); ctx.closePath(); ctx.fill();
        }
        const pixels = ctx.getImageData(0, 0, 256, 256).data;
        let covered = 0; for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 128) covered++;
        rows.push({ x, y, z: hit.point.z, normal: normal.toArray(), coverage: covered / 65536, triangles: uv.count / 3 });
        if (x !== .13 || y !== -.28) lab.designManager.removeSelected();
      }
      return rows;
    });
    fs.mkdirSync('.venv/custom-lab-artifacts/projection', { recursive: true });
    fs.writeFileSync(`.venv/custom-lab-artifacts/projection/${process.argv[2] || 'baseline'}.json`, JSON.stringify(metrics, null, 2));
    await page.locator('.editor-panel').screenshot({ path: `.venv/custom-lab-artifacts/projection/${process.argv[2] || 'baseline'}.png` });
    console.log(JSON.stringify(metrics));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
