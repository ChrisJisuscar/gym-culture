const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {chromium}=require('../../.venv/custom-lab-tools/node_modules/playwright');
(async()=>{
  const {token}=JSON.parse(await fs.readFile('.venv/backoffice-browser-token.json','utf8'));
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(token=>localStorage.setItem('gc_access_token',token),token);
    await fs.mkdir('.venv/backoffice-audit',{recursive:true});
    const visit=async(path,name)=>{
      await page.goto('http://127.0.0.1:8767'+path);
      await page.waitForFunction(()=>{const el=document.querySelector('#bo-feedback');return el&&!el.textContent.includes('Cargando');});
      assert.equal(await page.locator('#bo-feedback.is-error').count(),0,await page.locator('#bo-feedback').textContent());
      await page.waitForFunction(()=>[...document.images].every(img=>img.complete));
      assert.equal(await page.locator('body').textContent().then(text=>text.includes('undefined')),false);
      await page.screenshot({path:`.venv/backoffice-audit/${name}.png`});
    };
    for(const section of ['dashboard','orders','production','products','stock','customers']) {
      await visit(section==='dashboard'?'/backoffice/':`/backoffice/${section}/`,section);
    }
    const orders=await page.evaluate(async()=> (await GymCultureAuth.request('/api/backoffice/orders/')).json());
    if(orders.results.length) {
      await visit(`/backoffice/orders/${orders.results[0].id}/`,'order-detail');
      assert.match(await page.locator('.bo-heading h1').textContent(),/^GC-/);
    }
    // Exercise refresh and focused-variant navigation with intercepted mutations.
    let replenished=false;
    const variant={id:901,product:902,product_name:'Remera Oversize',color:'Blanco',size:'XL',active:true,stock_status:'OUT',stock:0,pending_demand:2,pending_orders:1};
    await page.route('**/api/backoffice/stock/**',async route=>{
      const url=new URL(route.request().url());
      if(route.request().method()==='POST') {
        assert.equal(url.pathname,'/api/backoffice/stock/901/adjust/');
        assert.equal(route.request().postDataJSON().quantity,2);
        replenished=true;
        return route.fulfill({json:{updated_variant:{...variant,pending_demand:0,pending_orders:0}}});
      }
      if(url.pathname.includes('/history/')) return route.fulfill({json:{count:0,results:[]}});
      assert.equal(url.searchParams.get('variant'),'901');
      return route.fulfill({json:{count:1,next:null,previous:null,results:[{...variant,pending_demand:replenished?0:2,pending_orders:replenished?0:1}]}});
    });
    await visit('/backoffice/stock/?variant=901','focused-stock');
    assert.match(await page.locator('.bo-demand-card').textContent(),/Faltan 2 unidades/);
    await page.locator('[data-adjust-stock="901"]').click();
    assert.equal(await page.locator('#stock-dialog input[name="quantity"]').inputValue(),'');
    await page.locator('#stock-dialog input[name="quantity"]').fill('2');
    await page.locator('#stock-dialog textarea[name="reason"]').fill('Reposicion de prueba');
    await page.locator('#stock-dialog .bo-primary').click();
    await page.waitForFunction(()=>document.querySelector('.bo-demand-card').textContent.includes('Faltan 0 unidades'));
    await page.screenshot({path:'.venv/backoffice-audit/stock-refreshed.png'});
    await page.setViewportSize({width:390,height:844});
    await visit('/backoffice/products/','products-mobile');
    assert.deepEqual(errors,[]);
    console.log('PASS six real Backoffice pages, order identity/previews, focused variant, confirmed restock refresh, mobile and no JS errors');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
