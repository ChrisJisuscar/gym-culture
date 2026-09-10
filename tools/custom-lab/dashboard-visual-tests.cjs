const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {chromium}=require('../../.venv/custom-lab-tools/node_modules/playwright');
(async()=>{
  const {token}=JSON.parse(await fs.readFile('.venv/backoffice-browser-token.json','utf8'));
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(token=>localStorage.setItem('gc_access_token',token),token);
    await fs.mkdir('.venv/backoffice-refinement',{recursive:true});
    const ready=async()=>{await page.waitForSelector('#bo-metrics[aria-busy="false"]');await page.waitForTimeout(400);assert.equal(await page.locator('#bo-feedback.is-error').count(),0);};
    await page.goto('http://127.0.0.1:8767/backoffice/');await ready();
    const real=await page.evaluate(async()=> (await GymCultureAuth.request('/api/backoffice/dashboard/?period=90')).json());
    const originalId=await page.evaluate(()=>Chart.getChart(document.querySelector('#chart-period canvas')).id);
    for(const period of ['7','90','30','12m']) {
      const response=page.waitForResponse(r=>r.url().includes(`dashboard/?period=${period}`));
      await page.selectOption('#dashboard-period',period);await response;await ready();
      assert.equal(await page.evaluate(()=>Chart.getChart(document.querySelector('#chart-period canvas')).id),originalId);
      await page.locator('.bo-period-panel').screenshot({path:`.venv/backoffice-refinement/real-${period}.png`});
    }
    assert.equal(await page.evaluate(()=>Chart.getChart(document.querySelector('#chart-status canvas')).config.type),'doughnut');
    assert.equal(await page.evaluate(()=>Chart.getChart(document.querySelector('#chart-period canvas')).data.datasets[0].maxBarThickness),12);
    assert.equal(await page.locator('#status-legend li').count(),6);
    await page.screenshot({path:'.venv/backoffice-refinement/desktop-real.png',fullPage:true});
    // Explicit QA fixtures only: never persisted or used by the production endpoint.
    let scenario='many';
    await page.route('**/api/backoffice/dashboard/**',async route=>{
      const data=structuredClone(real);data.period='90';
      if(scenario==='error')return route.fulfill({status:500,json:{detail:'QA error'}});
      if(scenario==='empty') {
        data.kpis=Object.fromEntries(Object.keys(data.kpis).map(key=>[key,0]));
        data.sales_over_time=data.sales_over_time.map(row=>({...row,orders:0,sales:0}));
        data.orders_by_city=[];data.top_products=[];data.low_stock=[];data.recent_orders=[];
        data.orders_by_status=data.orders_by_status.map(row=>({...row,orders:0}));data.period_summary={orders:0,sales:0};
      } else {
        data.sales_over_time=data.sales_over_time.map((row,i)=>({...row,orders:(i%11)+2,sales:((i%7)+1)*1250000}));
        data.orders_by_city=Array.from({length:28},(_,i)=>({city:`Ciudad de prueba ${i+1} con nombre largo`,orders:100-i}));
        data.top_products=Array.from({length:10},(_,i)=>({product__name:`Producto de prueba ${i+1}`,quantity:50-i}));
        data.period_summary={orders:600,sales:12500000};
      }
      await new Promise(resolve=>setTimeout(resolve,250));
      return route.fulfill({json:data});
    });
    const refresh=async()=>{const response=page.waitForResponse(r=>r.url().includes('dashboard/?'));await page.click('#dashboard-retry');await response;};
    await refresh();await ready();
    assert.equal(await page.evaluate(()=>Object.keys(Chart.instances).length),4);
    await page.locator('.bo-period-panel').screenshot({path:'.venv/backoffice-refinement/many-desktop.png'});
    const canvas=page.locator('#chart-period canvas');
    const point=await page.evaluate(()=>{const c=Chart.getChart(document.querySelector('#chart-period canvas'));const p=c.getDatasetMeta(0).data[6];return {x:p.x,y:p.y};});
    const box=await canvas.boundingBox();await page.mouse.move(box.x+point.x,box.y+point.y);await page.waitForTimeout(300);
    assert.ok(await page.evaluate(()=>Chart.getChart(document.querySelector('#chart-period canvas')).tooltip.opacity>0));
    await page.locator('.bo-period-panel').screenshot({path:'.venv/backoffice-refinement/tooltip.png'});
    for(const width of [1024,390,320]) {
      await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(200);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.locator('.bo-period-panel').screenshot({path:`.venv/backoffice-refinement/many-${width}.png`});
    }
    scenario='empty';await refresh();await ready();
    assert.equal(await page.locator('.bo-chart canvas').count(),0);
    assert.equal(await page.locator('.bo-chart .bo-empty').count(),4);
    assert.equal(await page.evaluate(()=>Object.keys(Chart.instances).length),0);
    await page.screenshot({path:'.venv/backoffice-refinement/empty-mobile.png',fullPage:true});
    scenario='error';await refresh();await page.waitForSelector('#bo-feedback.is-error');
    assert.equal(await page.locator('[aria-busy="true"]').count(),0);
    scenario='many';await refresh();await ready();
    assert.equal(await page.evaluate(()=>Object.keys(Chart.instances).length),4);
    assert.deepEqual(errors,[]);
    console.log('PASS real 7/30/90/12m, chart reuse, donut, thin bars, many/empty/error recovery, tooltip, desktop/tablet/mobile 320px and no JS errors');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
