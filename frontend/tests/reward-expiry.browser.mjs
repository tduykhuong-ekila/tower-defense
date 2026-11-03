// Expired rewards show an explicit result; closing releases the modal/action lock.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1280,height:900}});
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5176';
async function api(path,data,token,host=false){const r=await page.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),await r.text());return r.json();}
try{
 await page.goto(base);
 const match=await api('/matches/',{name:'Reward expiry action recovery',configuration:{gameplay_mode:"LEGACY",initial_coins:1000,reward_grace_period_seconds:0}});
 const joins=[];
 for(let i=0;i<2;i++){const team=await api(`/matches/${match.id}/teams/`,{name:`Expiry ${i}`},match.host_token,true);joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Expiry ${i}`,team_id:team.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 await page.evaluate(room=>localStorage.setItem('full-gameplay-test-room',JSON.stringify(room)),{match,a:joins[0],b:joins[1]});
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=a');
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Câu hỏi tri thức'}),text=await dialog.innerText();
 await dialog.getByPlaceholder('Nhập câu trả lời hoặc kết quả giải mã...').fill(text.includes('2 + 2')?'4':'6');
 await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();await page.getByRole('button',{name:'Mở túi coin · 20–60',exact:true}).waitFor();
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 await page.getByRole('dialog',{name:'Câu hỏi tri thức'}).getByText('ĐÃ HẾT HẠN CHỌN PHẦN THƯỞNG').waitFor({timeout:8000});
 await page.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 const card=page.locator('.arsenal-card').filter({hasText:'Bộ binh'});
 const proof={modalVisible:await page.getByRole('dialog').count(),cardDisabled:await card.isDisabled(),reason:await card.getAttribute('data-reason-code')};
 await fs.writeFile(new URL('../../docs/qa/reward-expiry-browser.json',import.meta.url),JSON.stringify(proof,null,2));console.log(JSON.stringify(proof,null,2));
 if(!process.env.REPRODUCE_ONLY){await page.waitForFunction(()=>!document.querySelector('.arsenal-card')?.disabled,{timeout:3000});await card.click();await page.getByRole('button',{name:'Xuất 1 Bộ binh',exact:true}).click();await page.getByText('Đã triển khai 1 Bộ binh.',{exact:true}).waitFor();console.log('PASS expired reward shows a result; explicit Close restores legal deployment');}
}catch(e){await page.screenshot({path:new URL('../../docs/qa/reward-expiry-failure.png',import.meta.url).pathname});throw e;}finally{await browser.close();}
