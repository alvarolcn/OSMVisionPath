const {chromium}=require('../.qa/node_modules/playwright'),assert=require('assert'),fs=require('fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/ortho',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({image:'data:image/png;base64,'+fs.readFileSync('.qa/sample.png').toString('base64'),bbox:[0,0,1000,1000],source:'pnoa'})}));
 await page.goto('http://127.0.0.1:5002');await page.locator('#load').click();await page.locator('#map').waitFor({state:'visible'});
 await page.waitForFunction(()=>!document.getElementById('load').disabled);
 assert(await page.locator('#overlay').isDisabled());assert(await page.locator('#show-mask').isDisabled());
 await page.evaluate(()=>{paths=[[[.1,.3],[.4,.3]],[[.6,.3],[.9,.3]]];geojson={type:'FeatureCollection',features:paths.map(line=>editedFeature(line,{properties:{source:'fixture'}}))};selected=0;updateCandidates();});
 assert(await page.locator('#overlay').isEnabled());
 const click=async(x,y)=>{const at=await page.evaluate(([x,y])=>{const r=canvas.getBoundingClientRect();return {x:r.left+panX+x*1024*viewScale(),y:r.top+panY+y*1024*viewScale()};},[x,y]);await page.mouse.click(at.x,at.y);};
 await page.locator('#split-trace').click();assert((await page.locator('#map').evaluate(el=>getComputedStyle(el).cursor)).includes('scissors-cursor.svg'));await click(.25,.3);assert.equal(await page.evaluate(()=>paths.length),3);
 await page.locator('#map').focus();await page.keyboard.press('Control+z');assert.equal(await page.evaluate(()=>paths.length),2);
 await page.keyboard.press('c');await click(.7,.3);await click(.5,.4);await page.keyboard.press('c');
 assert.equal(await page.evaluate(()=>paths.length),1);assert(await page.evaluate(()=>paths[0].some(p=>Math.abs(p[1]-.4)<.001)));
 assert.equal(await page.evaluate(()=>geojson.features[0].geometry.coordinates.length),await page.evaluate(()=>paths[0].length));
 await page.keyboard.press('Control+z');assert.equal(await page.evaluate(()=>paths.length),2);
 assert.equal(await page.locator('.toolbar .editor-tools #delete-trace').count(),1);
 await page.locator('#map').focus();await page.keyboard.press('Delete');assert.equal(await page.evaluate(()=>paths.length),1);
 await page.keyboard.press('Control+z');assert.equal(await page.evaluate(()=>paths.length),2);
 await page.keyboard.press('c');await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>traceEdit),null);
 for(const index of [0,-1]){
  await page.evaluate(index=>{selected=index;updateCandidates();},index);
  const expected=index===0?1:2;
  const geoDownload=page.waitForEvent('download');await page.locator('#export').click();const geo=await geoDownload;
  assert.equal(JSON.parse(fs.readFileSync(await geo.path(),'utf8')).features.length,expected);
  const osmDownload=page.waitForEvent('download');await page.locator('#export-osm').click();const osm=await osmDownload;
  assert.equal((fs.readFileSync(await osm.path(),'utf8').match(/<way /g)||[]).length,expected);
 }
 await page.evaluate(()=>{paths=[[[.1,.5],[.4,.5]],[[.402,.5],[.8,.5]]];geojson={type:'FeatureCollection',features:paths.map(line=>editedFeature(line))};selected=0;updateCandidates();});
 await page.locator('#join-traces').click();await click(.6,.5);assert.equal(await page.evaluate(()=>paths.length),1);assert.equal(await page.evaluate(()=>traceEdit),null);
 assert.deepEqual(errors,[]);console.log('Trace editing OK: split, delete, C join with intermediate bridge, Escape and Ctrl+Z preserve geometry.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
