// Exercises disposable hosted sessions only; does not target the local operator lab.
// Usage: node scripts/check_hosted_sessions.mjs http://127.0.0.1:18890 [--ai]
import assert from 'node:assert/strict';
const base=process.argv[2];
if(!base)throw new Error('Provide the hosted Worker URL');
const origin=new URL(base).origin;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report=[];
async function api(path,{method='GET',body,cookie}={}){
  const r=await fetch(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',...(cookie?{Cookie:cookie}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(120000)});
  const data=await r.json();
  return {r,data};
}
async function create(){
  const {r,data}=await api('/api/session',{method:'POST'});assert.equal(r.status,200,JSON.stringify(data));
  const cookie=r.headers.get('set-cookie').split(';')[0];
  for(let i=0;i<30;i++){
    const state=await api('/api/v1/state',{cookie});
    if(state.r.ok)return cookie;
    await pause(2000);
  }
  throw new Error('Container did not become ready');
}
async function call(cookie,path,body,method=body===undefined?'GET':'POST'){
  const {r,data}=await api(path,{cookie,body,method});assert.ok(r.ok,`${path}: ${r.status} ${JSON.stringify(data)}`);return data;
}
const sessions=[];
try{
  assert.equal((await api('/api/v1/state')).r.status,401);
  assert.equal((await fetch(origin+'/api/session',{method:'POST',headers:{Origin:'https://unrelated.example'}})).status,403);
  const a=await create();sessions.push(a);const b=await create();sessions.push(b);
  assert.notEqual(a,b);report.push('distinct server-issued sessions; unauthorized and cross-origin calls rejected');
  const beforeB=await call(b,'/api/v1/state');
  const run=await call(a,'/api/v1/runs',{scenario:'normal_day',controller_mode:'baseline',ai_schedule_enabled:false});
  await call(a,`/api/v1/runs/${run.id}/reset`,{});
  await call(a,`/api/v1/runs/${run.id}/step`,{minutes:10});
  const water=await call(a,'/api/v1/state');
  assert.ok(water.plant.elapsed_minutes>=10);assert.ok(Object.keys(water.plant.sensors).length>50);
  const afterB=await call(b,'/api/v1/state');assert.equal(afterB.plant.elapsed_minutes,beforeB.plant.elapsed_minutes);
  assert.equal((await call(b,'/api/v1/runs')).length,0);
  const injections=await call(a,'/api/v1/injections');
  assert.ok(injections.definitions.length);
  await call(a,`/api/v1/injections/${injections.definitions[0].id}`,{duration_minutes:10});
  await call(a,`/api/v1/runs/${run.id}/pause`,{});
  assert.ok((await call(a,'/api/v1/injections')).active.length);
  const exported=await call(a,`/api/v1/runs/${run.id}/export?format=json`);assert.ok(exported);
  report.push('water step, sensors, fault injection, pause, export; second visitor unchanged');
  const scenarios=await call(a,'/api/v1/infrastructure/scenarios');
  for(const domain of ['nuclear','grid']){
    const scenario=scenarios[domain].find(s=>s.id.includes(domain==='grid'?'generator_trip':'coolant_pump_trip'))||scenarios[domain][1];
    await call(a,`/api/v1/infrastructure/${domain}/command`,{action:'reset',scenario:scenario.id});
    await call(a,`/api/v1/infrastructure/${domain}/command`,{action:'step',minutes:15});
    const plants=await call(a,'/api/v1/infrastructure/state');
    assert.equal(plants[domain].scenario,scenario.id);assert.ok(plants[domain].elapsed_minutes>=15);
    assert.ok(Object.keys(plants[domain].sensors).length>5);
    const other=await call(b,'/api/v1/infrastructure/state');assert.equal(other[domain].elapsed_minutes,0);
    report.push(`${domain}: disturbance, stepping, sensors, and visitor isolation`);
  }
  assert.equal((await api('/api/v1/agents/water/study',{cookie:a,method:'POST',body:{}})).r.status,403);
  if(process.argv.includes('--ai')){
    for(const domain of ['water','nuclear','grid']){
      await pause(11000);
      const job=await call(a,`/api/v1/agents/${domain}/cycle`,{evaluate_only:true,thinking:false});
      let finished;
      for(let i=0;i<60;i++){
        const state=await call(a,'/api/v1/agents/state');const current=state.jobs.find(j=>j.id===job.id);
        if(current?.status==='complete'){finished=await call(a,`/api/v1/agents/records/${current.record_id}`);break;}
        if(current?.status==='failed'){
          const evidence=current.record_id?await call(a,`/api/v1/agents/records/${current.record_id}`):null;
          throw new Error(`${domain}: ${current.error}; audit: ${evidence?.error||'unavailable'}`);
        }
        await pause(2000);
      }
      assert.ok(finished,`${domain} inference timeout`);
      assert.equal(finished.execution_location,'cloud');assert.equal(finished.applied,false);
      assert.ok(['accepted','modified','rejected'].includes(finished.gate?.status),JSON.stringify(finished.gate));
      assert.ok(finished.before?.plant?.sensors);
      report.push(`${domain}: real cloud model → ${finished.gate.status} gate → persisted non-actuating audit`);
    }
  }
  await call(a,'/api/session',undefined,'DELETE');
  assert.equal((await api('/api/v1/state',{cookie:a})).r.status,401);
  report.push('ended session denied further API access');
  console.log(JSON.stringify({passed:true,checks:report},null,2));
}finally{
  for(const cookie of sessions)await api('/api/session',{cookie,method:'DELETE'}).catch(()=>{});
}
