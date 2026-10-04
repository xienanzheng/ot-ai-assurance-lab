import test from 'node:test';
import assert from 'node:assert/strict';
import { decisionOutcome } from '../services/web/src/decisionOutcome.mjs';
test('review without commands is distinct from rejected actuation', () => {
  assert.equal(decisionOutcome({status:'complete',proposal:{episode_status:'escalate',changes:{}},gate:{status:'rejected'}}).kind,'operator_review');
  assert.equal(decisionOutcome({status:'complete',proposal:{episode_status:'escalate',changes:{pressure_target_m:45}},gate:{status:'rejected'}}).kind,'blocked');
});
test('failures and pending records never claim a hold or accepted action', () => {
  assert.equal(decisionOutcome({status:'invalid_or_unavailable',gate:{status:'not_submitted'}}).kind,'inference_failure');
  assert.equal(decisionOutcome({status:'awaiting_gate',proposal:{changes:{}}}).kind,'pending');
  assert.equal(decisionOutcome({status:'gate_failed',proposal:{changes:{}}}).kind,'execution_failure');
});
test('hold, approved and applied have separate outcomes', () => {
  assert.equal(decisionOutcome({status:'complete',proposal:{changes:{x:null}},gate:{status:'accepted'}}).kind,'hold');
  assert.equal(decisionOutcome({status:'complete',proposal:{changes:{x:1}},gate:{status:'accepted'}}).kind,'approved');
  assert.equal(decisionOutcome({status:'complete',applied:true,proposal:{changes:{x:1}},gate:{status:'accepted'}}).kind,'applied');
});
test('a low-confidence empty proposal is a hold with an explicit unapproved gate', () => {
  assert.equal(decisionOutcome({status:'complete',proposal:{episode_status:'continue',changes:{}},gate:{status:'rejected'}}).label,'Hold · gate not authorized');
});
