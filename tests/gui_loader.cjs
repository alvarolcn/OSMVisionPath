const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('https://tile.openstreetmap.org/**',route=>route.abort());
  await page.goto('http://127.0.0.1:5000');
  const image=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=4096;const ctx=c.getContext('2d');ctx.fillStyle='#416e39';ctx.fillRect(0,0,4096,4096);return c.toDataURL();});
  let release=null,requestCount=0;
  await page.route('**/api/ortho',async route=>{requestCount++;await new Promise(resolve=>release=resolve);await route.fulfill({json:{image,bbox:[0,0,1000,1000],width:4096,height:4096,meters_per_pixel:.1831}});});
  await page.locator('#choose-area').click();await page.locator('#osm-map').waitFor({state:'visible'});
  await page.locator('#apply-area').click();await page.locator('#ortho-loader').waitFor({state:'visible'});
  assert.equal(await page.locator('#viewport').getAttribute('aria-busy'),'true');
  assert(await page.locator('#load').isDisabled());
  await page.waitForTimeout(500);assert(await page.locator('#ortho-loader').isVisible());assert.equal(requestCount,1);
  release();await page.locator('#ortho-loader').waitFor({state:'hidden'});
  assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  assert((await page.locator('#resolution').textContent()).includes('4096 × 4096'));
  assert.equal(await page.evaluate(()=>image.naturalWidth),4096);
  assert.equal(await page.locator('#viewport').getAttribute('aria-busy'),'false');
  await page.unroute('**/api/ortho');
  await page.route('**/api/ortho',route=>route.fulfill({status:502,json:{error:'WMS de prueba no disponible'}}));
  await page.locator('#choose-area').click();await page.locator('#apply-area').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='WMS de prueba no disponible');
  assert(await page.locator('#ortho-loader').isHidden());assert(await page.locator('#load').isEnabled());
  assert.deepEqual(errors,[]);console.log('Loader GUI OK: automatic area load, visible until decoding, 4096px image, fitted view and cleanup on error.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
