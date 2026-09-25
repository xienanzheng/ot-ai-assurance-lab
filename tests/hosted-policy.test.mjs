import test from 'node:test';
import assert from 'node:assert/strict';
import { actuationGuard, admit, authorize, consumeAI, emptyLedger, modelRequest, modelResponse, HOSTED_MODEL, forwardRequest } from '../deploy/cloudflare-live/policy.mjs';

test('sessions are separate, expire, and have a global admission limit', () => {
  const ledger=emptyLedger(0);
  for(let i=0;i<3;i++) assert.equal(admit(ledger,`s${i}`,`c${i}`,0).ok,true);
  assert.equal(admit(ledger,'extra','extra',0).status,429);
  assert.equal(authorize(ledger,'unknown',0).status,401);
  assert.equal(authorize(ledger,'s0',1200001).status,401);
  assert.equal(ledger.sessions.s0.containerId,'c0');
  assert.equal(ledger.sessions.s1.containerId,'c1');
});
test('AI budget is enforced across sessions and rejected requests cannot increase it', () => {
  const ledger=emptyLedger(0); admit(ledger,'s','container',0);
  assert.equal(consumeAI(ledger,'forged',0).status,401);
  for(let i=0;i<10;i++) assert.equal(consumeAI(ledger,'container',i*11000).ok,true);
  assert.equal(consumeAI(ledger,'container',120000).status,429);
  assert.equal(ledger.aiCalls,10);
});
test('daily limits survive expiry and reset only on the next UTC day', () => {
  const ledger=emptyLedger(0); ledger.created=20;
  assert.equal(admit(ledger,'s','c',1).status,429);
  assert.equal(admit(ledger,'s','c',86400000).ok,true);
  ledger.aiCalls=200;
  assert.equal(consumeAI(ledger,'c',86400001).status,429);
});
test('API calls are rate limited per session',()=>{
  const ledger=emptyLedger(0);admit(ledger,'s','c',0);
  for(let i=0;i<180;i++) assert.equal(authorize(ledger,'s',0,true).ok,true);
  assert.equal(authorize(ledger,'s',0,true).status,429);
  assert.equal(authorize(ledger,'s',60000,true).ok,true);
});
test('hosted inference pins model and output allowance and validates protocol',()=>{
  const input={model:'anything',messages:[{role:'user',content:'snapshot'}],format:{type:'object'},options:{num_predict:999999}};
  const r=modelRequest(input);
  assert.equal(r.max_tokens,2048);assert.equal(r.stream,false);
  assert.ok(r.messages[0].content.includes('snapshot'));
  assert.throws(()=>modelRequest({...input,messages:[{role:'user',content:'x'.repeat(50001)}]}));
  assert.throws(()=>modelRequest({...input,messages:[]}));
  const result=modelResponse({choices:[{message:{content:'{"changes":{}}',reasoning_content:'Emitted rationale'}}],usage:{completion_tokens:12}});
  assert.equal(result.model,HOSTED_MODEL);assert.equal(result.provider,'cloudflare-workers-ai');
  assert.equal(result.message.thinking,'Emitted rationale');
  assert.throws(()=>modelResponse({}));
});
test('forwarding preserves POST bodies and strips client-selected container ports',async()=>{
  const input=new Request('https://demo.test/api/v1/runs?x=1',{method:'POST',headers:{'Content-Type':'application/json','cf-container-target-port':'4840'},body:'{"scenario":"normal_day"}'});
  const forwarded=await forwardRequest(input);
  assert.equal(await forwarded.text(),'{"scenario":"normal_day"}');
  assert.equal(forwarded.headers.get('cf-container-target-port'),null);
  assert.equal(forwarded.url,'http://lab.internal/api/v1/runs?x=1');
  const tooLarge=await forwardRequest(new Request('https://demo.test/api/v1/runs',{method:'POST',body:'x'.repeat(65537)}));
  assert.equal(tooLarge.status,413);
});

test('proposal field limits reach the provider as structured output constraints',()=>{
  const format={type:'object',properties:{explanation:{type:'string',maxLength:280}},required:['explanation'],additionalProperties:false};
  const input=modelRequest({messages:[{role:'user',content:'Evaluate this simulated snapshot'}],format});
  assert.equal(input.response_format.type,'json_schema');
  assert.equal(input.response_format.json_schema.properties.explanation.maxLength,280);
  assert.deepEqual(input.response_format.json_schema.required,['explanation']);
  assert.equal(input.response_format.json_schema.additionalProperties,false);
});

test('the hosted edge refuses applied AI actuation however it is requested',async()=>{
  // gated_auto is the only mode that writes model output into control, on every route
  // that carries it: the infrastructure command and the water run config alike.
  assert.ok(actuationGuard('/api/v1/infrastructure/grid/command','{"action":"configure","controller_mode":"gated_auto"}'));
  assert.ok(actuationGuard('/api/v1/runs','{"scenario":"normal_day","controller_mode":"gated_auto"}'));
  assert.ok(actuationGuard('/api/v1/agents/water/cycle','{"evaluate_only":false}'));
  // Evaluation, and every other mode, stays available.
  assert.equal(actuationGuard('/api/v1/infrastructure/grid/command','{"action":"configure","controller_mode":"advisory"}'),null);
  assert.equal(actuationGuard('/api/v1/infrastructure/grid/command','{"action":"start"}'),null);
  assert.equal(actuationGuard('/api/v1/agents/water/cycle','{"evaluate_only":true}'),null);
  // A body that is not an object must not throw its way past the guard.
  assert.equal(actuationGuard('/api/v1/runs','not json'),null);
  assert.equal(actuationGuard('/api/v1/runs','null'),null);
  // And the guard has to hold through the real forwarding path, not just in isolation.
  const blocked=await forwardRequest(new Request('https://demo.test/api/v1/infrastructure/nuclear/command',
    {method:'POST',body:'{"action":"configure","controller_mode":"gated_auto"}'}));
  assert.equal(blocked.status,403);
  const allowed=await forwardRequest(new Request('https://demo.test/api/v1/infrastructure/nuclear/command',
    {method:'POST',body:'{"action":"configure","controller_mode":"shadow"}'}));
  assert.equal(allowed.url,'http://lab.internal/api/v1/infrastructure/nuclear/command');
});
