import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { capacity, jevRequest, actuationGuard, admit, authorize, consumeAI, emptyLedger, modelRequest, modelResponse, HOSTED_MODEL, forwardRequest } from '../deploy/cloudflare-live/policy.mjs';

test('capacity is configured server-side with bounded integers',()=>{
  assert.deepEqual(capacity(),{active:3,dailySessions:20,sessionAI:10,dailyAI:200});
  const settings=capacity({LAB_MAX_ACTIVE:'6',LAB_DAILY_SESSIONS:'60',LAB_SESSION_AI:'20',LAB_DAILY_AI:'600'});
  const ledger=emptyLedger(0);
  for(let i=0;i<6;i++)assert.equal(admit(ledger,`s${i}`,`c${i}`,0,settings).ok,true);
  assert.equal(admit(ledger,'s6','c6',0,settings).status,429);
  for(const bad of ['0','-1','2.5','NaN','Infinity','7','',true])assert.throws(()=>capacity({LAB_MAX_ACTIVE:bad}));
  assert.throws(()=>capacity({LAB_SESSION_AI:'101'}));
  assert.throws(()=>capacity({LAB_DAILY_AI:'10001'}));
});
test('remaining allowance includes both daily and session budgets, even after config reductions',()=>{
  const settings=capacity({LAB_SESSION_AI:'20',LAB_DAILY_AI:'21'});
  const ledger=emptyLedger(0);admit(ledger,'s','c',0,settings);
  ledger.aiCalls=20;
  assert.equal(authorize(ledger,'s',0,false,settings).ai_remaining,1);
  assert.equal(consumeAI(ledger,'c',0,settings).remaining,0);
  assert.equal(consumeAI(ledger,'c',11000,settings).status,429);
  assert.equal(authorize(ledger,'s',11000,false,settings).ai_remaining,0);
  ledger.sessions.s.aiCalls=22;
  assert.equal(authorize(ledger,'s',12000,false,settings).ai_remaining,0);
});
test('container ceiling and configured admission capacity agree',async()=>{
  const {MAX_CONTAINER_INSTANCES}=await import('../deploy/cloudflare-live/policy.mjs');
  const config=JSON.parse(readFileSync(new URL('../deploy/cloudflare-live/wrangler.jsonc',import.meta.url),'utf8'));
  assert.equal(config.containers[0].max_instances,MAX_CONTAINER_INSTANCES);
  assert.ok(capacity(config.vars).active<=config.containers[0].max_instances);
});
test('capacity increase preserves expiry cleanup and failed-call reservations',()=>{
  const settings=capacity({LAB_MAX_ACTIVE:'6',LAB_SESSION_AI:'20'});
  const ledger=emptyLedger(0);
  for(let i=0;i<6;i++)admit(ledger,`s${i}`,`c${i}`,0,settings);
  assert.equal(consumeAI(ledger,'c0',0,settings).remaining,19);
  assert.equal(consumeAI(ledger,'c0',1,settings).status,429);
  assert.equal(ledger.aiCalls,1);
  assert.equal(admit(ledger,'new','new',1200001,settings).status,429);
});

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

test('hosted forwarding permits gate-controlled simulated application',async()=>{
  assert.equal(actuationGuard('/api/v1/agents/water/cycle','{"evaluate_only":false}'),null);
  const result=await forwardRequest(new Request('https://demo.test/api/v1/agents/water/cycle',{method:'POST',body:'{"evaluate_only":false,"provider":"jev"}'}));
  assert.equal(result.url,'http://lab.internal/api/v1/agents/water/cycle');
});
test('Jev requests pin the provider and reject unrestricted questions',()=>{
  const input={model:'other',state:{sensors:{}},questions:{response:{type:'choice',instructions:'Choose a target',criteria:{hold:'Hold',adjust:'Adjust'}}}};
  const output=jevRequest(input);
  assert.equal(output.model,'typesafe/jev-1.13');
  assert.throws(()=>jevRequest({...input,questions:{response:{type:'text'}}}));
  assert.throws(()=>jevRequest({...input,state:'x'.repeat(50001)}));
});

test('Jev operator response survives the hosted adapter',()=>{
  const response={type:'choice',instructions:'Choose',criteria:{hold:'Hold',review:'Review'}};
  const operator_response={type:'choice',instructions:'Select required operator plan',criteria:{required_plan:'SOP plan',not_required:'No escalation'}};
  const request=jevRequest({state:{},questions:{response,operator_response}});
  assert.deepEqual(request.questions.operator_response,operator_response);
  assert.throws(()=>jevRequest({state:{},questions:{response,operator_response:{...operator_response,criteria:{bad:'Unapproved'}}}}));
});
