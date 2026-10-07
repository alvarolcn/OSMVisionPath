// Optional: npm install --prefix .qa playwright; python tests/check_onnx.py; node tests/gui.cjs
const { chromium } = require('../.qa/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/ortho',route=>route.fulfill({json:{image:'data:image/png;base64,'+fs.readFileSync(path.join(__dirname,'../.qa/sample.png')).toString('base64'),bbox:[0,0,1000,1000],width:1024,height:1024}}));
  await page.goto('http://127.0.0.1:5001');
  await page.locator('#mode').selectOption('automatic');
  await page.locator('#load').click();await page.locator('#map').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  await page.locator('#zoom-reset').click();
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.querySelector('#candidate').options[0].value!=='');
  const initial=await page.locator('#candidate option').count();assert(initial>0);
  await page.locator('#zoom-in').click();assert.equal(await page.locator('#zoom-value').textContent(),'140%');
  await page.locator('#edit-candidate').click();
  await page.waitForTimeout(2300);
  const snapshot=await page.evaluate(()=>({points:points.map(p=>[...p]),zoom,panX,panY}));
  const rect=await page.locator('#map').boundingBox();
  const point=snapshot.points.findIndex(([x,y])=>x*1024*snapshot.zoom+snapshot.panX>30&&x*1024*snapshot.zoom+snapshot.panX<994&&y*1024*snapshot.zoom+snapshot.panY>30&&y*1024*snapshot.zoom+snapshot.panY<994);
  assert(point>=0);
  const p=snapshot.points[point],x=rect.x+(p[0]*1024*snapshot.zoom+snapshot.panX)*rect.width/1024,y=rect.y+(p[1]*1024*snapshot.zoom+snapshot.panY)*rect.height/1024;
  await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+15,y+12,{steps:4});await page.mouse.up();
  const changed=await page.evaluate(i=>points[i],point);assert(Math.abs(changed[0]-p[0])>.001);
  assert(Math.abs(changed[0]-p[0]-15/rect.width/snapshot.zoom)<.0001);
  await page.locator('#detect').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Corrección aplicada'));
  await page.locator('#zoom-reset').click();assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  const download=page.waitForEvent('download');await page.locator('#export').click();assert.equal((await download).suggestedFilename(),'caminos-pnoa.geojson');
  await page.locator('#remove-candidate').click();assert.equal(await page.locator('#candidate option').count(),Math.max(1,initial-1));
  await page.locator('#mode').selectOption('segmentation');assert(await page.locator('#auto-detect').isDisabled());
  await page.locator('#model-file').setInputFiles(path.join(__dirname,'../.qa/test-only.onnx'));
  await page.locator('#upload-model').click();await page.waitForFunction(()=>document.querySelector('#model-status').textContent.startsWith('Modelo activo:'));
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.querySelector('#candidate').options[0].value!=='');
  await page.screenshot({path:path.join(__dirname,'../.qa/gui.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log('GUI OK: automatic candidates, zoom, drag correction, recalculation, export, discard and ONNX inference.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
