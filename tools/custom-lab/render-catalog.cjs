const fs = require('node:fs/promises');
const {chromium} = require('../../.venv/custom-lab-tools/node_modules/playwright');
(async()=>{
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
  try {
    const page=await browser.newPage();
    await page.goto('http://127.0.0.1:8765/crear-mi-remera/');
    await page.waitForFunction(()=>window.GymCulture3D?.isReady());
    for(const type of ['tshirt','hoodie']) {
      await page.evaluate(type=>GymCulture3D.setGarmentType(type),type);
      await page.waitForFunction(()=>GymCulture3D.isReady());
      const bytes=await page.evaluate(async()=>Array.from(new Uint8Array(await (await GymCulture3D.capturePreviews()).front.arrayBuffer())));
      await fs.writeFile(`backend/products/assets/${type}.webp`,Buffer.from(bytes));
    }
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
