// Optional: run isolated tests/gui_server.py first. Verifies the actual map interactions.
const {chromium}=require('../.qa/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  // Keep interaction tests deterministic, without requesting public OSM tiles.
  await page.route('https://tile.openstreetmap.org/**',route=>route.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(__dirname,'../.qa/sample.png'))}));
  const response=await page.request.post('http://127.0.0.1:5001/api/model',{multipart:{model:{name:'test-only.onnx',mimeType:'application/octet-stream',buffer:fs.readFileSync(path.join(__dirname,'../.qa/test-only.onnx'))}}});assert(response.ok());
  await page.goto('http://127.0.0.1:5001');await page.locator('#mode').selectOption('segmentation');
  await page.waitForFunction(()=>document.querySelector('#model-status').textContent.startsWith('Modelo activo:'));
  assert.equal(await page.locator('#replace-model').getAttribute('open'),null);
  assert(await page.locator('#upload-model').isDisabled());
  await page.locator('#load').click();await page.locator('#ortho-loader').waitFor({state:'hidden'});assert(await page.locator('#auto-detect').isEnabled());
  const original=await page.locator('#lat').inputValue();
  await page.locator('#choose-area').click();await page.locator('#osm-map').waitFor({state:'visible'});await page.waitForTimeout(400);
  let rect=await page.locator('#osm-map').boundingBox();
  await page.mouse.click(rect.x+rect.width*.65,rect.y+rect.height*.6);
  await page.locator('#close-area').click();assert.equal(await page.locator('#lat').inputValue(),original);
  await page.locator('#choose-area').click();await page.waitForTimeout(400);rect=await page.locator('#osm-map').boundingBox();
  const loadResponse=page.waitForResponse(r=>r.url().endsWith('/api/ortho'));
  await page.mouse.click(rect.x+rect.width*.65,rect.y+rect.height*.6);await page.locator('#apply-area').click();
  assert.notEqual(await page.locator('#lat').inputValue(),original);
  const loaded=await (await loadResponse).json();
  await page.locator('#ortho-loader').waitFor({state:'hidden'});
  const lat=Number(await page.locator('#lat').inputValue()),lon=Number(await page.locator('#lon').inputValue()),span=Number(await page.locator('#span').inputValue());
  const centerX=6378137*lon*Math.PI/180,centerY=6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
  assert(Math.abs((loaded.bbox[0]+loaded.bbox[2])/2-centerX)<.001);assert(Math.abs((loaded.bbox[1]+loaded.bbox[3])/2-centerY)<.001);
  assert(Math.abs((loaded.bbox[2]-loaded.bbox[0])*Math.cos(lat*Math.PI/180)-span)<.001);
  await page.locator('#choose-area').click();await page.waitForTimeout(400);rect=await page.locator('#osm-map').boundingBox();
  await page.locator('#draw-area').click();
  await page.mouse.move(rect.x+rect.width*.3,rect.y+rect.height*.3);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.6,{steps:8});await page.mouse.up();
  const summary=await page.locator('#picker-summary').textContent();assert(summary.includes('×'));
  await page.waitForTimeout(350);assert.equal(await page.locator('#picker-summary').textContent(),summary);
  await page.screenshot({path:path.join(__dirname,'../.qa/area-picker.png'),fullPage:true});
  await page.locator('#apply-area').click();const width=Number(await page.locator('#span').inputValue());assert(width>=100&&width<=3000);assert(width%50===0);
  await page.waitForFunction(()=>!document.querySelector('#auto-detect').disabled);
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Candidatos detectados'));
  await page.locator('#show-mask').check();assert(await page.locator('#detection-info').textContent());assert.equal(await page.locator('#model-file').inputValue(),'');
  assert.deepEqual(errors,[]);console.log('Area GUI OK: optional preloaded model, cancel, center click, square drag, coordinates, WMS footprint, segmentation without file and mask.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
