const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage();let downloads=0,active='models/first.onnx',detections=0;
  const rectangle=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=800;c.height=400;return c.toDataURL();});
  const json=(route,data)=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  await page.route('**/api/health',route=>json(route,{opencv:'5',model:active}));
  await page.route('**/api/editor-models',route=>json(route,{active,models:[{id:'models/first.onnx'},{id:'models/second.onnx'}]}));
  await page.route('**/api/editor-models/activate',route=>{active=route.request().postDataJSON().model;return json(route,{model:active});});
  await page.route('**/api/ortho',route=>{downloads++;return json(route,{image:rectangle,bbox:[0,0,1000,500],source:'pnoa',meters_per_pixel:1});});
  await page.route('**/api/extract',route=>{detections++;return json(route,{paths:[],geojson:{type:'FeatureCollection',features:[]},message:'Detectado'});});
  await page.goto('http://127.0.0.1:5002');
  await page.waitForFunction(()=>document.getElementById('editor-model').options.length===2);
  assert(await page.locator('#tool').isHidden());assert(await page.locator('#color-correction').isHidden());assert(await page.locator('#tool-nodes').isHidden());
  await page.locator('#load').click();await page.waitForFunction(()=>!document.getElementById('auto-detect').disabled);
  assert.equal(await page.evaluate(()=>planeHeight()),512);
  await page.locator('#map').focus();await page.keyboard.press('a');assert.equal(await page.locator('#tool').inputValue(),'select');
  assert.equal(await page.locator('#tool-hand').getAttribute('aria-pressed'),'true');
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.getElementById('status').textContent==='Detectado');
  await page.locator('#zoom-in').click();const zoom=await page.locator('#zoom-value').textContent();
  await page.locator('#editor-model').selectOption('models/second.onnx');
  await page.waitForFunction(()=>document.getElementById('status').textContent==='Modelo seleccionado y activado.');
  assert(await page.locator('#auto-detect').isEnabled());assert.equal(downloads,1);assert.equal(await page.locator('#zoom-value').textContent(),zoom);
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.getElementById('status').textContent==='Detectado');
  assert.equal(detections,2);assert.equal(downloads,1);
  await page.locator('#mode').selectOption('wololo');assert(await page.locator('#tool').isVisible());assert(await page.locator('#tool-nodes').isVisible());
  await page.locator('#map').focus();await page.keyboard.press('a');assert.equal(await page.locator('#tool').inputValue(),'correct');
  await page.locator('#mode').selectOption('segmentation');assert.equal(await page.locator('#tool').inputValue(),'select');
  await page.locator('#ortho-gsd').selectOption('2');assert(await page.locator('#auto-detect').isDisabled());
  console.log('Model switch OK: detects twice on one downloaded image, preserves zoom, area changes still require reload.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
