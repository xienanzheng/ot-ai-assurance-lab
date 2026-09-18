import test from 'node:test';
import assert from 'node:assert/strict';
import { demoEvidence, demoBrief, measuredValue } from '../src/demoEvidence.js';
const sample = (minute,value,quality='good',target=22) => ({minute,values:{filtered_turbidity_ntu:value},quality:{filtered_turbidity_ntu:quality},setpoints:{coagulant_target_mg_l:target}});
test('replay ignores bad sensor quality and uses confirmed actuation, not a complete proposal',()=>{
 const e=demoEvidence({samples:{agent:[sample(2,1.2),sample(0,.2),sample(1,2,'stale'),sample(4,1.3,'good',17)]},exchanges:[{minute:1,status:'complete',was_applied:false},{minute:2,status:'complete',was_applied:true,applied:{coagulant_target_mg_l:17}},{minute:3,status:'failed'}]},null);
 assert.equal(e.firstExcursion.minute,2);assert.equal(e.applied.minute,2);assert.equal(e.after.minute,4);assert.equal(e.appliedCount,1);assert.equal(e.failures,1);
});
test('missing and unfinished studies do not turn into successful cases',()=>{
 const e=demoEvidence(null,{cases:[{id:'incomplete',safe:{logit_gap:-2}}]});
 assert.equal(e.calls,0);assert.equal(e.validCases,0);assert.equal(e.patchCount,0);assert.equal(e.correctPairs,0);assert.equal(e.applied,undefined);
 assert.match(demoBrief(null,null),/not fully verified/);
});
test('scores count both conditions, and preserve controls and provenance in the brief',()=>{
 const m={id:'probe',source_sha256:'abc',activations_sha256:'def',cases:[{safe:{logit_gap:-2},alarm:{logit_gap:1},patches:[{layer:3}]},{safe:{logit_gap:2},alarm:{logit_gap:1},patches:[]}],verification:{all_controls_passed:false}};
 const e=demoEvidence({},m);assert.equal(e.correctPairs,1);assert.equal(e.validCases,2);assert.equal(e.patchCount,1);
 const brief=demoBrief({},m);assert.match(brief,/1\/2 scored pairs/);assert.match(brief,/not fully verified/);assert.match(brief,/Activations SHA-256: def/);
});

test('unknown, stale and nonfinite readings never become within-bound evidence',()=>{
 for(const value of [null,undefined,NaN,Infinity]) assert.equal(measuredValue(sample(1,value)),null);
 assert.equal(measuredValue(sample(1,.4,'stale')),null);
 assert.equal(measuredValue(sample(1,0)),0);
});
