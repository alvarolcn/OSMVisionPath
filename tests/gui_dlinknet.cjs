// Optional integration with the main server, actual converted model and PNOA.
const { chromium }=require('../.qa/node_modules/playwright');
const assert=require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:5000');
  await page.locator('#mode').selectOption('segmentation');
  await page.waitForFunction(()=>document.querySelector('#model-status').textContent.includes('dlinknet34.onnx'));
  assert.equal(await page.locator('#replace-model').getAttribute('open'),null);
  assert.equal(await page.locator('#model-file').inputValue(),'');
  await page.locator('#load').click();await page.locator('#map').waitFor({state:'visible',timeout:60000});
  await page.locator('#ortho-loader').waitFor({state:'hidden',timeout:60000});
  assert.equal(await page.evaluate(()=>image.naturalWidth),4096);
  assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  await page.locator('#auto-detect').click();
  await page.waitForFunction(()=>{
   const text=document.querySelector('#status').textContent;
   return text.startsWith('Candidatos detectados')||text.startsWith('No se encontraron trazados');
  },null,{timeout:240000});
  const candidates=await page.evaluate(()=>paths.length);assert(candidates>0);
  await page.locator('#show-mask').check();await page.waitForTimeout(2300);
  await page.screenshot({path:require('path').join(__dirname,'../.qa/pnoa-tiled.png'),fullPage:true});
  await page.locator('#choose-area').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('#osm-map img.leaflet-tile')].some(img=>img.complete&&img.naturalWidth>0),null,{timeout:30000});
  await page.screenshot({path:require('path').join(__dirname,'../.qa/area-picker-real.png'),fullPage:true});
  await page.locator('#close-area').click();
  assert.deepEqual(errors,[]);
  console.log('D-LinkNet GUI and real OSM tiles OK:',await page.locator('#model-status').textContent(),'; candidates:',candidates);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
