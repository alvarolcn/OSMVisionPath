const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
const G=require('../static/trace-geometry');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const bbox=[-456902,4926672,-455918,4927656];
  const fixture=[[[.1,.1],[.2,.10001],[.3,.1],[.4,.3],[.5,.30001],[.6,.3]],[[.2,.10001],[.2,.2],[.2,.3]]];
  const geojson={type:'FeatureCollection',features:fixture.map(line=>({type:'Feature',properties:{source:'PNOA IGN',review_required:true},geometry:{type:'LineString',coordinates:line.map(p=>G.coordinates(p,bbox))}}))};
  await page.route('**/api/ortho',route=>route.fulfill({json:{image:'data:image/png;base64,'+fs.readFileSync(path.join(__dirname,'../.qa/sample.png')).toString('base64'),bbox,width:1024,height:1024,meters_per_pixel:.73}}));
  await page.route('**/api/extract',route=>route.fulfill({json:{paths:fixture,geojson,message:'Candidatos detectados.'}}));
  await page.goto('http://127.0.0.1:5000');assert.equal(await page.locator('#mode').inputValue(),'segmentation');
  await page.locator('#load').click();await page.locator('#ortho-loader').waitFor({state:'hidden'});
  assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  await page.locator('#auto-detect').click();await page.waitForFunction(()=>document.querySelector('#candidate').options.length===2);
  const original=await page.evaluate(()=>JSON.stringify({paths,geojson}));
  await page.locator('#simplify').click();const result=await page.evaluate(()=>({paths,geojson}));
  assert(result.paths[0].length<fixture[0].length);assert.deepEqual(result.paths[1],fixture[1]);
  assert(result.paths[0].some(p=>p[0]===.2));assert.equal(result.geojson.features[0].properties.simplification_tolerance_m,1);
  const downloaded=page.waitForEvent('download');await page.locator('#export-osm').click();const file=await downloaded;assert.equal(file.suggestedFilename(),'caminos-pnoa.osm');
  const xml=fs.readFileSync(await file.path(),'utf8');
  const checked=await page.evaluate(xml=>{const document=new DOMParser().parseFromString(xml,'application/xml');const nodes=[...document.querySelectorAll('node')].map(n=>n.getAttribute('id'));return {errors:document.querySelectorAll('parsererror').length,ways:document.querySelectorAll('way').length,refs:[...document.querySelectorAll('nd')].every(n=>nodes.includes(n.getAttribute('ref')))};},xml);
  assert.deepEqual(checked,{errors:0,ways:2,refs:true});
  await page.locator('#undo-trace').click();assert.equal(await page.evaluate(()=>JSON.stringify({paths,geojson})),original);
  await page.locator('#simplify-scope').selectOption('all');await page.locator('#simplify-tolerance').selectOption('5');await page.locator('#simplify').click();
  assert.equal(await page.evaluate(()=>paths[1].length),2);
  await page.locator('#remove-candidate').click();assert.equal(await page.evaluate(()=>paths.length),1);
  await page.locator('#undo-trace').click();assert.equal(await page.evaluate(()=>paths.length),2);
  await page.locator('#undo-trace').click();assert.equal(await page.evaluate(()=>JSON.stringify({paths,geojson})),original);
  assert(await page.locator('#undo-trace').isDisabled());
  await page.screenshot({path:path.join(__dirname,'../.qa/editing.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log('Editing GUI OK: fit image, default segmentation, selected/all simplification, undo stack and valid JOSM XML download.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
