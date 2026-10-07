const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage();
  await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:fs.readFileSync('.qa/sample.png')}));
  await page.goto('http://127.0.0.1:5002');
  await page.locator('#choose-area').click();
  await page.locator('#picker-osm-url').fill('https://www.openstreetmap.org/#map=16/41.99178/-3.71119');await page.locator('#picker-open-url').click();
  await page.locator('#picker-span').fill('500');await page.locator('#picker-span').press('Tab');await page.locator('#close-area').click();
  await page.locator('#nav-datasets').click();await page.locator('#ds-choose-area').click();
  await page.locator('#picker-osm-url').fill('https://www.openstreetmap.org/#map=15/42.1/-3.8');await page.locator('#picker-open-url').click();
  await page.locator('#picker-span').fill('1000');await page.locator('#picker-span').press('Tab');
  await page.locator('#picker-height').fill('500');await page.locator('#picker-height').press('Tab');
  await page.locator('#picker-generate-url').click();assert.equal(await page.locator('#picker-osm-url').inputValue(),'https://www.openstreetmap.org/#map=15/42.100000/-3.800000');
  await page.locator('#close-area').click();await page.reload();
  assert.equal(Number(await page.locator('#lat').inputValue()),41.99178);
  await page.locator('#choose-area').click();assert.equal(await page.locator('#picker-span').inputValue(),'500');
  await page.locator('#picker-generate-url').click();assert((await page.locator('#picker-osm-url').inputValue()).includes('#map=16/41.991780/-3.711190'));await page.locator('#close-area').click();
  await page.locator('#nav-datasets').click();await page.locator('#ds-choose-area').click();
  await page.waitForFunction(()=>document.getElementById('picker-span').value==='1000');
  assert.equal(await page.locator('#picker-span').inputValue(),'1000');assert((await page.locator('#picker-summary').textContent()).includes('42.100000, -3.800000'));
  assert.equal(await page.locator('#picker-height').inputValue(),'500');
  const ratio=await page.evaluate(()=>{const box=projectedSelection(window.areaPicker.saved('dataset').selection);return (box[2]-box[0])/(box[3]-box[1]);});assert(Math.abs(ratio-2)<.01);
  await page.locator('#apply-area').click();assert((await page.locator('#ds-bbox').inputValue()).startsWith('-3.'));
  console.log('Area storage OK: independent editor/dataset selection, size and map zoom survive reload; generated URL matches current view.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
