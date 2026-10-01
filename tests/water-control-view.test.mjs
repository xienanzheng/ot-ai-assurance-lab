import test from 'node:test';
import assert from 'node:assert/strict';
import {changedTargets,feedbackView,freshReading,createWaterCommandQueue} from '../services/web/src/waterControlView.mjs';
test('editing pressure preserves a newer chlorine target',()=>{
 const initial={pressure_target_m:44,chlorine_target_mg_l:1.05};
 assert.deepEqual(changedTargets(initial,{...initial,pressure_target_m:42,backwash_request:false},{...initial,chlorine_target_mg_l:1.0}),{pressure_target_m:42});
 assert.throws(()=>changedTargets(initial,{...initial,chlorine_target_mg_l:1.1},{...initial,chlorine_target_mg_l:1.0}),/changed while/);
});
test('monitoring distinguishes off, delayed automatic review, final observation and baseline return',()=>{
 const plc={controller_generation:'g'},plant={elapsed_minutes:20,running:true};
 const loop={domain:'water',controller_generation:'g',status:'observing',next_review_minute:28,calls_used:1,max_calls:3};
 assert.match(feedbackView(loop,plant,plc).detail,/Next automatic review at minute 28 · 8/);
 assert.match(feedbackView({...loop,calls_used:3},plant,plc).detail,/Final observation ends/);
 assert.match(feedbackView({...loop,status:'stopped',reason:'Budget complete'},plant,plc).label,/baseline/);
 assert.equal(feedbackView({...loop,controller_generation:'old'},plant,plc).label,'Off');
 assert.match(feedbackView(loop,{...plant,running:false},plc).label,/Paused/);
});
test('invalid and stale values never appear as normal readings',()=>{
 const sensor={value:1.1,quality:'good',timestamp:'2026-01-01T00:00:00Z'};
 assert.equal(freshReading(sensor,'2026-01-01T00:01:00Z'),1.1);
 assert.equal(freshReading(sensor,'2026-01-01T00:03:00Z'),null);
 assert.equal(freshReading({...sensor,quality:'bad'},sensor.timestamp),null);
});

test('a step queued during scenario reset waits and uses the authoritative new run',async()=>{
 let active='old',releaseReset;
 const blocked=new Promise(resolve=>{releaseReset=resolve;});
 const calls=[],pending=[];
 const api=async(path)=>{
   calls.push(path);
   if(path==='/api/v1/state')return {active_run_id:active};
   if(path==='/api/v1/runs')return {id:'new'};
   if(path.endsWith('/reset')){await blocked;active='new';}
   if(path.endsWith('/step'))assert.equal(path,'/api/v1/runs/new/step');
   return {};
 };
 const command=createWaterCommandQueue(api,x=>pending.push(x));
 const reset=command('configure',{scenario:'chlorine_efficiency_trim'});
 const step=command('step',{minutes:15});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls.some(x=>x.endsWith('/step')),false);
 releaseReset();await Promise.all([reset,step]);
 assert.equal(calls.filter(x=>x.endsWith('/step')).length,1);
 assert.equal(pending.at(-1),false);
});
test('failed water commands are reported and do not poison the queue',async()=>{
 let fail=true;
 const command=createWaterCommandQueue(async path=>{
   if(path==='/api/v1/state')return {active_run_id:'current'};
   if(fail){fail=false;throw Error('Reset interrupted');}return {};
 });
 await assert.rejects(command('reset'),/Reset interrupted/);
 assert.equal((await command('pause')).state.active_run_id,'current');
});
test('call budget completion remains visible as read-only monitoring',()=>{
 const loop={domain:'water',controller_generation:'g',status:'monitoring',budget_complete:true,calls_used:2,max_calls:2};
 const view=feedbackView(loop,{running:true,elapsed_minutes:40},{controller_generation:'g'});
 assert.match(view.label,/Monitoring · baseline control/);
 assert.match(view.detail,/AI call budget complete/);
});
