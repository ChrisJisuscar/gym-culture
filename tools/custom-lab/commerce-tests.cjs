const assert = require('node:assert/strict');
const { chromium } = require('../../.venv/custom-lab-tools/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless:true, args:['--enable-unsafe-swiftshader']});
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}});
    const errors=[];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('requestfailed', r=>console.error(r.url(), r.failure()));

    // Grilla obligatoria por prenda: Negro/Blanco × M/XL, con variantes en stock 0.
    const grid = {
      tshirt: {id:901, name:'Remera', variants:[{id:910,size:'XL',color:'Negro',stock:0},{id:911,size:'M',color:'Negro',stock:5},{id:912,size:'XL',color:'Blanco',stock:4},{id:913,size:'M',color:'Blanco',stock:0}]},
      oversized: {id:902, name:'Remera Oversize', variants:[{id:920,size:'XL',color:'Negro',stock:0},{id:921,size:'M',color:'Negro',stock:5},{id:922,size:'XL',color:'Blanco',stock:4},{id:923,size:'M',color:'Blanco',stock:0}]},
      hoodie: {id:903, name:'Hoodie', variants:[{id:930,size:'XL',color:'Negro',stock:0},{id:931,size:'M',color:'Negro',stock:5},{id:932,size:'XL',color:'Blanco',stock:4},{id:933,size:'M',color:'Blanco',stock:0}]},
    };
    const products = Object.values(grid).map((g, i) => ({id:g.id, name:g.name, garment_type:Object.keys(grid)[i], price: g.id===902?'120000':g.id===901?'89000':'0', variants:g.variants}));
    const expectVariant = (g, size, color) => grid[g].variants.find(v=>v.size===size&&v.color===color);

    await page.route('**/crear-mi-remera/**', async route=>{
      const response=await route.fetch();
      const body=(await response.text()).replace(/(<script id="customizer-products" type="application\/json">)[\s\S]*?(<\/script>)/, '$1'+JSON.stringify(products)+'$2');
      await route.fulfill({response,body});
    });
    await page.route('**/js/customizer-3d.js', async route => {
      const response = await route.fetch();
      const source = (await response.text()).replaceAll('\r\n', '\n');
      await route.fulfill({response, body: source.replace('  return {\n    init, dispose',
        '  window.__lab = () => ({ scene, renderer, controls, garmentMeshes, garmentMaterials, designManager });\n  return {\n    init, dispose')});
    });
    await page.goto('http://127.0.0.1:8767/crear-mi-remera/?lab-debug=1');
    await page.waitForFunction(()=>window.GymCulture3D?.isReady());
    const state=()=>page.evaluate(()=>GymCulture3D.getCustomizationState());
    const materialHex=()=>page.evaluate(()=>__lab().garmentMaterials[0].color.getHexString());

    // Debug (§12): con ?lab-debug=1 el estado de disponibilidad se registra con las mismas claves por prenda.
    const debugLogs = [];
    page.on('console', msg => {
      if (msg.type() === 'debug' && msg.text().includes('[GYM CULTURE] availability')) debugLogs.push(msg.text());
    });

    for (const garment of ['tshirt','oversized','hoodie']) {
      await page.locator(`[data-garment="${garment}"]`).click();
      await page.waitForFunction(()=>GymCulture3D.isReady());
      const stateSnap = await state();
      assert.equal(stateSnap.garment.type, garment);
      assert.equal(stateSnap.garment.productId, products.find(p=>p.garment_type===garment).id);

      // Barrido de colores: la paleta central completa aparece y NO se oculta ningún swatch.
      const palette = await page.evaluate(()=>[...document.querySelectorAll('.color-option')].map(b=>({color:b.dataset.color, hidden:b.hidden, disabled:b.disabled, hex:b.dataset.hex})));
      assert.equal(palette.length, 2, `${garment} expone los colores de sus variantes reales`);
      assert.equal(palette.some(b=>b.hidden), false, `${garment} no oculta colores`);
      for (const color of ['Negro','Blanco']) {
        const swatch = palette.find(b=>b.color===color);
        assert.ok(swatch, `${color} aparece en ${garment}`);
        assert.equal(swatch.disabled, false, `${color} seleccionable en ${garment}`);
      }

      // Tallas S/M/L/XL/2XL presentes; M y XL siempre disponibles aunque su stock sea 0.
      const sizes = await page.evaluate(()=>[...document.querySelectorAll('.size-option')].map(b=>({size:b.dataset.size, hidden:b.hidden, disabled:b.disabled})));
      for (const size of ['M','XL']) {
        const option = sizes.find(s=>s.size===size);
        assert.ok(option, `${size} existe en ${garment}`);
        assert.equal(option.hidden, false);
        assert.equal(option.disabled, false);
      }

      // Combos de la grilla resuelven selectedVariant SIN depender de stock.
      for (const [size, color, expectedStock] of [['XL','Blanco',4],['M','Blanco',0],['M','Negro',5],['XL','Negro',0]]) {
        await page.locator(`[data-color="${color}"]`).click();
        await page.locator(`[data-size="${size}"]`).click();
        const resolved = await state();
        const expected = expectVariant(garment, size, color);
        assert.equal(resolved.garment.variantId, expected.id, `${garment} ${color}/${size}`);
        assert.equal(resolved.garment.selectedVariant, undefined); // selectedVariant no se serializa
        const raw = await page.evaluate(()=>window.GymCultureCustomizer.state.selectedVariant);
        assert.equal(raw.stock, expectedStock, `${garment} mantiene el stock real de la variante ${expected.id}`);
        assert.equal(await page.locator('#add-cart').isEnabled(), true, `${garment} habilita el carrito con stock ${expectedStock}`);
        if (expectedStock === 0) {
          assert.match(await page.locator('#stock-note').textContent(), /Sin stock inmediato/);
          assert.equal(await page.locator('#stock-hint').isVisible(), true);
        } else {
          assert.match(await page.locator('#stock-note').textContent(), /Disponible/);
          assert.equal(await page.locator('#stock-hint').isHidden(), true);
        }
        if (color === 'Blanco') {
          await page.evaluate(()=>new Promise(r=>setTimeout(r,300)));
          assert.equal(await materialHex(), 'ebe9e4', `${garment} cambia el material 3D a Blanco`);
        }
      }
      if (garment === 'hoodie') {
        for (const hoodState of ['down','up']) {
          await page.locator(`[data-hood-state="${hoodState}"]`).click();
          assert.equal((await state()).garment.hoodState, hoodState);
        }
        await page.locator('[data-hood-state="down"]').click();
      }
    }
    console.log('PASS grilla obligatoria en las tres prendas: colores visibles/seleccionables, tallas M/XL, stock 0 seleccionable, material y estado');
    assert.ok(debugLogs.length >= 6, 'El debug de disponibilidad registró el estado por prenda');

    // CASO A vs CASO B (restauración): combinación existente con stock 0 restaura; inexistente no confunde.
    await page.evaluate((config)=>GymCulture3D.loadCustomization(config), {version:1, garment:{type:'oversized', productId:902, variantId:920, color:'Negro', colorHex:'#111015', size:'XL', hoodState:'down'}, designs:[]});
    assert.equal((await state()).garment.variantId, 920, 'Restaura selección con Negro/XL stock 0');
    assert.match(await page.locator('#stock-note').textContent(), /Sin stock inmediato/);
    assert.equal(await page.locator('#add-cart').isEnabled(), true);
    await page.evaluate((config)=>GymCulture3D.loadCustomization(config), {version:1, garment:{type:'oversized', productId:902, variantId:null, color:'Blanco', colorHex:'#ebe9e4', size:'L', hoodState:'down'}, designs:[]});
    assert.equal((await state()).garment.variantId, null, 'Combinación inexistente => null');
    assert.match(await page.locator('#stock-note').textContent(), /no está configurada/);
    assert.equal(await page.locator('#stock-hint').isHidden(), true);
    assert.equal(await page.locator('#add-cart').isDisabled(), true);
    console.log('PASS Case A (stock 0 restaura y selecciona) vs Case B (combinación inexistente) sin confundirse');

    // Cambio de prenda con selección inválida previa (Blanco/L, Case B): el producto nuevo reencauza.
    assert.equal((await state()).garment.variantId, null);
    await page.locator('[data-garment="tshirt"]').click();
    await page.waitForFunction(()=>GymCulture3D.isReady());
    const reAligned = await state();
    assert.equal(reAligned.garment.color, 'Blanco');
    assert.equal(reAligned.garment.size, 'XL');
    assert.ok([910,911,912,913].includes(reAligned.garment.variantId), `Se reacomodó a una variante real del tshirt (${reAligned.garment.variantId})`);
    assert.equal(await page.locator('#add-cart').isEnabled(), true);
    console.log('PASS cambiar garment no conserva selección inválida previa: reacomoda a una variante real del nuevo producto');

    // Carrito: una variante con stock 0 es válida (Negro/XL del oversized = 920).
    await page.evaluate(()=>localStorage.setItem('gc_access_token','test-only'));
    let payload;
    await page.route('**/api/cart/items/**', async route=>{
      payload=route.request().postDataJSON();
      await route.fulfill({status:201,contentType:'application/json',body:'{}'});
    });
    await page.locator('[data-garment="oversized"]').click();
    await page.waitForFunction(()=>GymCulture3D.isReady());
    await page.locator('[data-color="Negro"]').click();
    await page.locator('[data-size="XL"]').click();
    assert.equal((await state()).garment.variantId, 920);
    await page.locator('#add-cart').click();
    await page.waitForFunction(()=>document.querySelector('#cart-note').textContent.includes('agregado'));
    assert.deepEqual(payload,{product:902,variant:920,quantity:1});
    console.log('PASS carrito acepta la variante con stock 0 (producto 902 / variante 920)');

    // Catálogo vacío: la paleta central no se borra (regresión de "colores que desaparecían").
    await page.unroute('**/crear-mi-remera/**');
    await page.route('**/crear-mi-remera/**', async route=>{
      const response=await route.fetch();
      const body=(await response.text()).replace(/(<script id="customizer-products" type="application\/json">)[\s\S]*?(<\/script>)/, '$1'+JSON.stringify([])+'$2');
      await route.fulfill({response,body});
    });
    await page.goto('http://127.0.0.1:8767/crear-mi-remera/');
    await page.waitForFunction(()=>window.GymCulture3D?.isReady(),null,{timeout:60000});
    assert.equal(await page.evaluate(()=>document.querySelectorAll('.color-option').length),6);
    assert.equal(await page.evaluate(()=>document.querySelectorAll('.size-option').length),5);
    assert.equal(await page.evaluate(()=>[...document.querySelectorAll('.color-option')].every(b=>b.hidden)),true);
    console.log('PASS catálogo vacío conserva paleta central y no borra colores');

    // Restauración resiliente: una imagen rota no aborta la personalización.
    await page.unroute('**/crear-mi-remera/**');
    await page.route('**/crear-mi-remera/**', async route=>{
      const response=await route.fetch();
      const body=(await response.text()).replace(/(<script id="customizer-products" type="application\/json">)[\s\S]*?(<\/script>)/, '$1'+JSON.stringify(products)+'$2');
      await route.fulfill({response,body});
    });
    await page.goto('http://127.0.0.1:8767/crear-mi-remera/');
    await page.waitForFunction(()=>window.GymCulture3D?.isReady(),null,{timeout:60000});
    const broken = {
      version: 1,
      garment: { type:'hoodie', hoodState:'down', color:'Blanco', colorHex:'#ebe9e4', size:'XL', productId:903, variantId:932 },
      designs: [
        { id:'broken-image', type:'image', assetUrl:'/media/definitely-missing.webp', position:{x:0,y:0,z:0}, normal:{x:0,y:0,z:1}, rotation:0, scale:1, aspectRatio:1, width:.2, height:.2 },
        { id:'ok-text', type:'text', text:'PROBANDO', fontFamily:'Outfit', color:'#ffffff', fontSize:280, position:{x:0,y:0,z:.1}, normal:{x:0,y:0,z:1}, rotation:0, scale:1, aspectRatio:2, width:.2, height:.1 },
      ],
    };
    await page.locator('[data-garment="hoodie"]').click();
    await page.waitForFunction(()=>GymCulture3D.isReady());
    await page.evaluate((config)=>GymCulture3D.loadCustomization(config), broken);
    const brokenResult = await state();
    assert.equal(brokenResult.garment.variantId, 932);
    assert.equal(brokenResult.garment.color, 'Blanco');
    assert.equal(brokenResult.designs.length, 2);
    assert.equal(await page.evaluate(()=>__lab().designManager.resources.size), 1);

    assert.deepEqual(errors,[]);
    console.log('PASS todas las verificaciones de color/talla/stock/material/restauración/carrito en tshirt, oversized y hoodie');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});