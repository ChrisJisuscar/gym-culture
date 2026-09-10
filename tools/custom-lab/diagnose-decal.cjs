const {chromium}=require('../../.venv/custom-lab-tools/node_modules/playwright');
(async()=>{
let browser;
try{
browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1100}});
const patch=async r=>{const response=await r.fetch();await r.fulfill({response,body:(await response.text()).replaceAll('\r\n','\n').replace('  return {\n    init, dispose','  window.__lab=()=>({scene,camera,garmentMeshes,garmentSize,designManager,renderer});\n  return {\n    init, dispose')});};
await page.route('**/js/customizer-3d.js',patch);

async function open(){await page.goto('http://127.0.0.1:8767/crear-mi-remera/',{waitUntil:'networkidle'});await page.waitForFunction(()=>window.GymCulture3D?.isReady());}

async function measure(garment){
  await open();
  if(garment!=='tshirt'){
    await page.locator(`[data-garment="${garment}"]`).click();
    await page.waitForTimeout(600);
    await page.waitForFunction(()=>GymCulture3D.isReady());
  }
  await page.evaluate(()=>GymCulture3D.setColor('#ebe9e4'));
  await page.locator('#add-3d-text').click();
  const canvas=page.locator('.customizer-3d-canvas');
  const box=await canvas.boundingBox();
  await canvas.click({position:{x:box.width*.5,y:box.height*.46}});
  await page.waitForTimeout(300);
  const out=await page.evaluate(()=>{
    const {designManager,garmentSize,garmentMeshes}=__lab();
    const r=[...designManager.resources.values()][0];
    const d=designManager.selected();
    if(!r||!r.mesh.geometry.attributes.position)return {state:'no-decal'};
    const pos=d.position,nrm=d.normal;
    const G=r.mesh.geometry;
    const p=G.attributes.position,n=G.attributes.normal,uv=G.attributes.uv;
    const norm=a=>{const l=Math.hypot(a[0],a[1],a[2])||1;return [a[0]/l,a[1]/l,a[2]/l];};
    const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
    const dir=norm([nrm.x,nrm.y,nrm.z]);
    let right=cross([0,1,0],dir);
    if(Math.hypot(...right)<.5)right=cross([1,0,0],dir);
    right=norm(right);
    const up=norm(cross(dir,right));
    let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9,minZ=1e9,maxZ=-1e9;
    let meanDot=0,grazer=0,side=0,count=0;
    for(let i=0;i<p.count;i+=3){
      const cx=(p.getX(i)+p.getX(i+1)+p.getX(i+2))/3;
      const cy=(p.getY(i)+p.getY(i+1)+p.getY(i+2))/3;
      const cz=(p.getZ(i)+p.getZ(i+1)+p.getZ(i+2))/3;
      const vx=cx-pos.x,vy=cy-pos.y,vz=cz-pos.z;
      const dz=vx*dir[0]+vy*dir[1]+vz*dir[2];
      const px=vx-dz*dir[0],py=vy-dz*dir[1],pz=vz-dz*dir[2];
      const sx=px*right[0]+py*right[1]+pz*right[2];
      const sy=px*up[0]+py*up[1]+pz*up[2];
      minX=Math.min(minX,sx);maxX=Math.max(maxX,sx);
      minY=Math.min(minY,sy);maxY=Math.max(maxY,sy);
      minZ=Math.min(minZ,dz);maxZ=Math.max(maxZ,dz);
      let nx=0,ny=0,nz=0;
      for(let j=0;j<3;j++){nx+=n.getX(i+j);ny+=n.getY(i+j);nz+=n.getZ(i+j);}
      const fn=norm([nx,ny,nz]);
      const ddot=fn[0]*dir[0]+fn[1]*dir[1]+fn[2]*dir[2];
      meanDot+=ddot;count++;
      if(ddot<=.15)grazer++;
      else if(ddot<=.5)side++;
    }
    const W=d.width,H=d.height;
    return {state:'ok',decalTriangles:count,designW:W,designH:H,aspect:(W/H),
      ratioW:(maxX-minX)/W,ratioH:(maxY-minY)/H,
      depthSpan:maxZ-minZ,meanDot:meanDot/count,grazer,side,
      posY:pos.y,posZ:pos.z,normalZ:nrm.z,
      garmentSize,
      meshNames:garmentMeshes.map(m=>m.name)};
  });
  return {garment,...out};
}

console.log(JSON.stringify(await measure('tshirt')));
console.log(JSON.stringify(await measure('oversized')));
console.log(JSON.stringify(await measure('hoodie')));
await page.screenshot({path:'.venv/diag-oversized.png'});
}catch(e){console.error(e);process.exitCode=1;}
finally{ if(browser) await browser.close(); else process.exit(0); }
})().catch(e=>{console.error(e);process.exitCode=1;});