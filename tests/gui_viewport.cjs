const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1800,height:900},deviceScaleFactor:2}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/health',r=>r.fulfill({json:{opencv:'5',model:'fixture.onnx'}}));
  await page.route('**/api/ortho',r=>r.fulfill({json:{image:'data:image/png;base64,'+fs.readFileSync('.qa/sample.png').toString('base64'),bbox:[0,0,1000,1000]}}));
  await page.goto('http://127.0.0.1:5000');await page.locator('#load').click();await page.locator('#ortho-loader').waitFor({state:'hidden'});
  const check=await page.evaluate(()=>({width:canvas.clientWidth,panel:$('viewport').clientWidth,size:1024*viewScale(),height:viewHeight,panX,panY,backing:canvas.width}));
  assert.equal(check.width,check.panel);assert(check.width>1000);assert.equal(check.size,check.height);assert(check.panX>0);assert.equal(check.backing,check.width*2);
  const click=async(x,y)=>{const rect=await page.locator('#map').boundingBox();const p=await page.evaluate(([x,y])=>[panX+x*1024*viewScale(),panY+y*1024*viewScale()],[x,y]);await page.mouse.click(rect.x+p[0],rect.y+p[1]);};
  assert.equal(await page.locator('#tool-hand').getAttribute('aria-pressed'),'true');
  await page.locator('#tool-nodes').click();assert.equal(await page.locator('#tool').inputValue(),'correct');assert.equal(await page.locator('#tool-nodes').getAttribute('aria-pressed'),'true');
  await page.locator('#tool-hand').click();assert.equal(await page.locator('#tool').inputValue(),'select');assert.equal(await page.locator('#tool-nodes').getAttribute('aria-pressed'),'false');
  await page.locator('#map').focus();await page.keyboard.press('a');await click(.25,.75);
  const point=await page.evaluate(()=>points[0]);assert(Math.abs(point[0]-.25)<.002&&Math.abs(point[1]-.75)<.002);
  await page.keyboard.press('s');assert.equal(await page.locator('#tool').inputValue(),'select');
  assert.equal(await page.locator('#tool-hand').getAttribute('aria-pressed'),'true');
  await page.locator('#zoom-fill').click();let fill=await page.evaluate(()=>({size:1024*viewScale(),width:viewWidth,height:viewHeight}));assert(fill.size>=fill.width-.01&&fill.size>=fill.height-.01);
  await page.locator('#zoom-in').click();await page.locator('#tool-nodes').click();
  const rect=await page.locator('#map').boundingBox(),beforeDrag=await page.evaluate(()=>({panX,panY,points:JSON.stringify(points)}));
  await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.55,rect.y+rect.height*.55,{steps:5});await page.mouse.up();
  const afterDrag=await page.evaluate(()=>({panX,panY,points:JSON.stringify(points)}));
  assert.notEqual(afterDrag.panX,beforeDrag.panX);assert.equal(afterDrag.points,beforeDrag.points);assert.equal(await page.locator('#tool').inputValue(),'correct');assert.equal(await page.locator('#tool-nodes').getAttribute('aria-pressed'),'true');
  await page.setViewportSize({width:1200,height:1000});await page.waitForTimeout(150);assert.deepEqual(await page.evaluate(()=>points[0]),point);
  await page.locator('#zoom-reset').click();assert.equal(await page.locator('#zoom-value').textContent(),'100%');
  await page.locator('#map').focus();await page.keyboard.press('a');await click(.75,.25);await page.keyboard.press('Escape');assert.equal(await page.locator('#tool').inputValue(),'select');
  assert.equal(await page.evaluate(()=>points.length),2);assert.deepEqual(errors,[]);
  console.log('Viewport OK: full rectangular panel, contain/fill, retina, S/Esc and marker coordinates preserved on resize.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
