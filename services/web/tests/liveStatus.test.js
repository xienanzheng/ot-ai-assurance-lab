import test from 'node:test';
import assert from 'node:assert/strict';
import { liveStatus, readLabJson } from '../src/liveStatus.js';
test('failed polling does not imply zero decisions or a paused plant',()=>{
 const s=liveStatus({connection:'offline',records:[]});
 assert.equal(s.model,'Live lab unavailable');
 assert.equal(s.records,'Records unavailable');
 assert.equal(s.plant,'Plant status unavailable');
});
test('record count distinguishes all records from completed evaluations',()=>{
 const s=liveStatus({connection:'online',agent:{model:{available:true,model_pulled:true}},plant:{controller_mode:'baseline',running:false},records:[{status:'failed'},{status:'complete',evaluate_only:true}]});
 assert.equal(s.model,'Local model ready');assert.equal(s.records,'2 records · 1 evaluation');assert.equal(s.plant,'baseline · paused');
});
test('HTML response becomes an actionable API error',async()=>{
 await assert.rejects(readLabJson(new Response('<!DOCTYPE HTML>',{status:404,headers:{'Content-Type':'text/html'}})),/Live API unavailable/);
});
