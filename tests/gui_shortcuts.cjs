const {chromium}=require('../.qa/node_modules/playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/health',r=>r.fulfill({json:{opencv:'5.0.0',model:'fixture.onnx'}}));
  await page.route('**/api/ortho',r=>r.fulfill({json:{image:'data:image/png;base64,'+fs.readFileSync('.qa/sample.png').toString('base64'),bbox:[0,0,1000,1000]}}));
  await page.goto('http://127.0.0.1:5000');await page.locator('#load').click();await page.locator('#ortho-loader').waitFor({state:'hidden'});
  await page.locator('#mode').selectOption('automatic');
  assert.equal(await page.locator('#tool').inputValue(),'select');
  const rect=await page.locator('#map').boundingBox();
  const click=async x=>{const at=await page.evaluate(x=>[panX+x*1024*viewScale(),panY+.5*1024*viewScale()],x);await page.mouse.click(rect.x+at[0],rect.y+at[1]);};
  await click(.5);await page.keyboard.press('a');
  for(const x of [.1,.2,.3])await click(x);
  assert.deepEqual(await page.evaluate(()=>pointIds),[1,2,3]);
  await page.keyboard.press('Escape');await click(.2);await page.keyboard.press('Delete');
  assert.deepEqual(await page.evaluate(()=>pointIds),[1,3]);
  assert.equal(await page.evaluate(()=>points.length),2);
  await page.keyboard.press('a');await click(.4);
  assert.deepEqual(await page.evaluate(()=>pointIds),[1,3,2]);
  await page.locator('#undo-trace').click();assert.deepEqual(await page.evaluate(()=>pointIds),[1,3]);
  await page.locator('#undo-trace').click();assert.deepEqual(await page.evaluate(()=>pointIds),[1,2,3]);
  const latitude=await page.locator('#lat').inputValue();
  await page.locator('#lat').focus();await page.keyboard.press('a');await page.keyboard.press('Delete');
  assert.deepEqual(await page.evaluate(()=>pointIds),[1,2,3]);
  await page.locator('#lat').fill(latitude);
  await page.locator('#zoom-in').click();await page.locator('#map').focus();await page.keyboard.press('Escape');
  assert.equal(await page.locator('#tool').inputValue(),'select');
  const panRect=await page.locator('#map').boundingBox();
  const before=await page.evaluate(()=>({panX,panY,points:JSON.stringify(points)}));
  await page.mouse.move(panRect.x+panRect.width*.5,panRect.y+panRect.height*.5);await page.mouse.down();await page.mouse.move(panRect.x+panRect.width*.55,panRect.y+panRect.height*.55,{steps:5});await page.mouse.up();
  const after=await page.evaluate(()=>({panX,panY,points:JSON.stringify(points)}));
  assert.notEqual(before.panX,after.panX);assert.equal(before.points,after.points);
  await page.locator('#mode').selectOption('wololo');assert.equal(await page.locator('#tool').inputValue(),'select');
  assert.deepEqual(errors,[]);console.log('Shortcuts GUI OK: hand pan, A marker, Esc hand, selected Delete, vacant IDs reused, undo and input guards.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
