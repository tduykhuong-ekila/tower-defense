import test from 'node:test';
import assert from 'node:assert/strict';
import {apiRequest} from '../src/services/api';

test('a timed-out request releases its promise with a resync message and never retries a purchase',async()=>{
 const originalFetch=globalThis.fetch,originalStorage=globalThis.sessionStorage,originalTimeout=AbortSignal.timeout;
 let attempts=0;
 try{
  globalThis.sessionStorage={getItem:()=>null} as any;
  AbortSignal.timeout=()=>AbortSignal.abort(new DOMException('timed out','TimeoutError'));
  globalThis.fetch=async(_url,options)=>{attempts++;assert.ok(options?.signal);throw options!.signal!.reason;};
  await assert.rejects(apiRequest('/matches/test/actions/deploy/',{method:'POST'}),/Đồng bộ lại trạng thái/);
  assert.equal(attempts,1);
 }finally{globalThis.fetch=originalFetch;globalThis.sessionStorage=originalStorage;AbortSignal.timeout=originalTimeout;}
});

test('structured action rejection preserves the actual server explanation',async()=>{
 const originalFetch=globalThis.fetch,originalStorage=globalThis.sessionStorage;
 try{
  globalThis.sessionStorage={getItem:()=>null} as any;
  globalThis.fetch=async()=>new Response(JSON.stringify({error:'Không đủ coin: cần 35, hiện có 10.',error_code:'INSUFFICIENT_COINS'}),{status:400,headers:{'Content-Type':'application/json'}});
  await assert.rejects(apiRequest('/matches/test/actions/deploy/',{method:'POST'}),/Không đủ coin/);
 }finally{globalThis.fetch=originalFetch;globalThis.sessionStorage=originalStorage;}
});
