import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../deploy/cloudflare/worker.mjs';

test('control requests never reach an origin or asset binding', async () => {
  const env={ASSETS:{fetch(){throw Error('must not be called');}}};
  for(const method of ['GET','POST','PUT','DELETE']) {
    const response=await worker.fetch(new Request('https://demo.test/api/v1/runs',{method}),env);
    assert.equal(response.status,503);
    assert.equal((await response.json()).code,'recorded_demo_only');
  }
});
test('root redirects to recorded evidence and other pages are denied', async () => {
  const response=await worker.fetch(new Request('https://demo.test/'),{});
  assert.equal(response.status,302);
  assert.equal(response.headers.get('location'),'https://demo.test/research.html');
  assert.equal((await worker.fetch(new Request('https://demo.test/admin'),{})).status,404);
});
test('only recorded assets are served, with same-origin policy', async () => {
  const response=await worker.fetch(new Request('https://demo.test/research/index.json'),{ASSETS:{fetch:async()=>new Response('{}')}});
  assert.equal(response.status,200);
  assert.match(response.headers.get('content-security-policy'),/connect-src 'self'/);
  assert.equal((await worker.fetch(new Request('https://demo.test/research/index.json',{method:'POST'}),{})).status,405);
});
test('asset response retains HTML body, content type, and missing-file status',async()=>{
  const html='<!doctype html><title>OT lab</title>';
  const response=await worker.fetch(new Request('https://demo.test/research.html'),{ASSETS:{fetch:async()=>new Response(html,{headers:{'Content-Type':'text/html'}})}});
  assert.equal(await response.text(),html);
  assert.equal(response.headers.get('Content-Type'),'text/html');
  const missing=await worker.fetch(new Request('https://demo.test/assets/missing.js'),{ASSETS:{fetch:async()=>new Response('Not found',{status:404})}});
  assert.equal(missing.status,404);
});
