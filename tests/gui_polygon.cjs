const {chromium}=require('../.qa/node_modules/playwright'),assert=require('assert'),fs=require('fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}});let selection;
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:fs.readFileSync('.qa/sample.png')}));
 await page.route('**/api/ortho',r=>{selection=r.request().postDataJSON();return r.fulfill({contentType:'application/json',body:JSON.stringify({image:'data:image/png;base64,'+fs.readFileSync('.qa/sample.png').toString('base64'),bbox:selection.bbox,source:'pnoa',width:1024,height:1024})});});
 await page.goto('http://127.0.0.1:5002');await page.locator('#choose-area').click();await page.locator('#draw-polygon').click();assert.equal(await page.locator('#osm-map .leaflet-overlay-pane path').count(),0);assert((await page.locator('#close-polygon').evaluate(el=>getComputedStyle(el).animationName)).includes('close-polygon-pulse'));
 const box=await page.locator('#osm-map').boundingBox();
 for(const [x,y] of [[.2,.2],[.75,.2],[.45,.75]])await page.mouse.click(box.x+x*box.width,box.y+y*box.height);
 assert(await page.locator('#apply-area').isDisabled());await page.locator('#close-polygon').click();assert(await page.locator('#apply-area').isEnabled());await page.locator('#apply-area').click();
 await page.waitForFunction(()=>loadedPolygon?.length===3&&!busy);
 assert.equal(selection.polygon.length,3);assert.equal(selection.bbox.length,4);
 assert.equal(await page.evaluate(()=>window.areaPicker.saved('editor').selection.polygon.length),3);
 await page.locator('#choose-area').click();await page.waitForFunction(()=>!document.getElementById('clear-polygon').hidden);assert(await page.locator('#draw-polygon').evaluate(el=>el.classList.contains('active')));assert(!(await page.locator('#pick-center').evaluate(el=>el.classList.contains('active'))));await page.locator('#clear-polygon').click();await page.locator('#close-area').click();
 assert.deepEqual(await page.evaluate(()=>window.areaPicker.saved('editor').selection.polygon??null),null);
 console.log('Polygon GUI OK: draw vertices, close, bbox and normalized polygon submitted, persistent selection and remove polygon.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
