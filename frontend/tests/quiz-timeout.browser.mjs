// Real server timeout using the existing imported bank's configured 60-second duration.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1280,height:900}});
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
async function api(path,data,token,host=false){const r=await page.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),await r.text());return r.json();}
try {
 await page.goto(base);
 const bankToken=crypto.randomUUID();
 const response=await page.request.post(base+'/api/v1/question-banks/upload/',{headers:{'X-Question-Bank-Token':bankToken},multipart:{file:{name:'timeout.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:await fs.readFile(new URL('../../backend/tests/fixtures/De_Thi_Quiz_Demo.xlsx',import.meta.url))}}});
 assert.ok(response.ok(),await response.text());const bank=await response.json();
 const match=await api('/matches/',{name:'Real question timeout',question_bank_id:bank.id,question_bank_token:bankToken});
 const joins=[];
 for(let i=0;i<2;i++){const team=await api(`/matches/${match.id}/teams/`,{name:`Timeout ${i}`},match.host_token,true);joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Timeout ${i}`,team_id:team.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 await page.evaluate(room=>localStorage.setItem('full-gameplay-test-room',JSON.stringify(room)),{match,a:joins[0],b:joins[1]});
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=a');
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Câu hỏi tri thức'});await dialog.waitFor();
 const q=await api(`/matches/${match.id}/questions/current/`,undefined,joins[0].participant_token);
 assert.equal(q.question.time_limit_seconds,60);
 await dialog.getByRole('button',{name:/^B\./}).click();
 await dialog.getByText('ĐÃ HẾT THỜI GIAN TRẢ LỜI',{exact:true}).waitFor({timeout:70000});
 // Wait for authoritative expiry, not just the locally interpolated countdown.
 await page.waitForFunction(async ({id,token})=>{const r=await fetch(`/api/v1/matches/${id}/questions/current/`,{headers:{'X-Participant-Token':token}});return (await r.json()).status==='EXPIRED';},{id:match.id,token:joins[0].participant_token},{timeout:8000});
 const expired=await api(`/matches/${match.id}/questions/current/`,undefined,joins[0].participant_token);
 assert.equal(expired.id,q.id);assert.equal(expired.status,'EXPIRED');assert.equal(expired.reward_options,null);
 assert.ok(await dialog.isVisible());
 await page.waitForTimeout(2500);
 assert.equal((await api(`/matches/${match.id}/questions/current/`,undefined,joins[0].participant_token)).id,q.id);
 await dialog.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();
 await dialog.waitFor({state:'hidden'});
 await page.getByRole('button',{name:'Xem kết quả câu hỏi',exact:true}).click();await dialog.waitFor();
 assert.equal((await api(`/matches/${match.id}/questions/current/`,undefined,joins[0].participant_token)).id,q.id);
 await dialog.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).click();
 const next=await api(`/matches/${match.id}/questions/current/`,undefined,joins[0].participant_token);
 assert.equal(next.sequence_number,2);assert.notEqual(next.id,q.id);
 const result={status:'PASS',configuredSeconds:60,explicitTimeout:true,noReward:true,noAutomaticNext:true,nextRequiresUserAction:true};
 await fs.writeFile(new URL('../../docs/qa/quiz-timeout-browser.json',import.meta.url),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
