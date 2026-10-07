const {chromium}=require('../.qa/node_modules/playwright'),assert=require('assert');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage();
 await page.route('**/api/system-memory',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({available_bytes:8*1024**3,total_bytes:16*1024**3,recommended_megapixels:39,bytes_per_pixel:96,model_reserve_bytes:512*1024**2})}));
 await page.goto('http://127.0.0.1:5002');await page.waitForFunction(()=>document.getElementById('ortho-max-mp').value==='39');
 assert((await page.locator('#ortho-memory-info').textContent()).includes('8.0 GB'));
 await page.locator('#ortho-max-mp').fill('1');await page.locator('#ortho-max-mp').dispatchEvent('input');assert((await page.locator('#ortho-size-estimate').textContent()).includes('Supera'));
 await page.locator('#ortho-max-mp').fill('0');await page.locator('#ortho-max-mp').dispatchEvent('input');await page.reload();await page.waitForFunction(()=>document.getElementById('ortho-memory-info').textContent.includes('8.0 GB'));assert.equal(await page.locator('#ortho-max-mp').inputValue(),'0');
 await page.locator('#ortho-use-recommended').click();await page.waitForFunction(()=>document.getElementById('ortho-max-mp').value==='39');
 assert.equal(await page.evaluate(()=>localStorage.getItem('terra-ortho-max-mp')),'39');console.log('Memory GUI OK: recommendation, area estimate, override, unlimited, persistence and reset.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
