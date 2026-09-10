const {chromium}=require('../../.venv/custom-lab-tools/node_modules/playwright');
(async()=>{
let browser;
try{
browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1100}});
const patch=async r=>{const response=await r.fetch();await r.fulfill({response,body:(await response.text()).replaceAll('\r\n','\n').replace('  return {\n    init, dispose','  window.__lab=()=>({scene,camera,garmentMeshes,garmentSize,designManager,renderer});\n  return {\n    init, dispose')});};
await page.route('**/js/customizer-3d.js',patch);
async function open(){await page.goto('http://127.0.0.1:8767/crear-mi-remera/',{waitUntil:'networkidle'});await page.waitForFunction(()=>window.GymCulture3D?.isReady());}

async function probe(garment){
  await open();
  if(garment!=='tshirt'){
    await page.locator(`[data-garment="${garment}"]`).click();
    await page.waitForTimeout(700);
    await page.waitForFunction(()=>GymCulture3D.isReady());
  }
  await page.evaluate(()=>GymCulture3D.setColor('#4a4650'));
  await page.locator('#add-3d-text').click();
  const canvas=page.locator('.customizer-3d-canvas');
  const box=await canvas.boundingBox();
  const fxp=box.width*.5,fyp=box.height*.46;
  await page.evaluate(`(()=>{const {scene,camera,renderer}=__lab();renderer.render(scene,camera);const gl=renderer.getContext();const w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;const buf=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,buf);window.__before={buf,w,h};})()`);
  await canvas.click({position:{x:fxp,y:fyp}});
  await page.waitForTimeout(400);
  const res=await page.evaluate(`(()=>{
    const {scene,camera,renderer,designManager}=__lab();
    renderer.render(scene,camera);
    const gl=renderer.getContext();
    const w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
    const buf=new Uint8Array(w*h*4);
    gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,buf);
    const before=window.__before.buf;
    let minX=w,minY=h,maxX=-1,maxY=-1,cnt=0;
    const x0=Math.floor(w*.05),x1=Math.floor(w*.95),y0=0,y1=h;
    for(let y=y0;y<y1;y++){
      for(let x=x0;x<x1;x++){
        const i=(y*w+x)*4;
        const d=Math.abs(buf[i]-before[i])+Math.abs(buf[i+1]-before[i+1])+Math.abs(buf[i+2]-before[i+2]);
        if(d>60){if(x<minX)minX=x;if(x>maxX)maxX=x;if(y<minY)minY=y;if(y>maxY)maxY=y;cnt++;}
      }
    }
    const visible=cnt>3;
    const aspectWH=visible?((maxX-minX)/((maxY-minY)||1)):0;
    const cx=visible?(minX+maxX)/(2*w):0;
    const cyVisible=visible?(minY+maxY)/(2*h):0;
    const design=designManager.selected();
    const r=[...designManager.resources.values()][0];
    return {visible,cnt,aspectWH,cx,cy:cyVisible,bbox:visible?[minX,minY,maxX,maxY]:null,
      design:{w:design.width,h:design.height},decalTriangles:r?r.mesh.geometry.attributes.position.count/3:0,
      buffer:[w,h]};
  })()`);
  return {garment,click:[fxp,fyp],canvas:[box.width,box.height],...res};
}
console.log(JSON.stringify(await probe('tshirt')));
console.log(JSON.stringify(await probe('oversized')));
console.log(JSON.stringify(await probe('hoodie')));
await page.screenshot({path:'.venv/diag-pixel.png'});
}catch(e){console.error(e);process.exitCode=1;}
finally{ if(browser) await browser.close(); else process.exit(0); }
})().catch(e=>{console.error(e);process.exitCode=1;});