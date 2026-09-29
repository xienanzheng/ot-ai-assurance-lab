// Display semantics do not change the raw gate verdict or application eligibility.
export function decisionOutcome(record) {
  const gate = record.gate?.status;
  const changes = Object.values(record.proposal?.changes || {}).some(value => value != null);
  if (record.status === 'invalid_or_unavailable') return { kind:'inference_failure', label:'Inference / response failure' };
  if (record.status === 'gate_failed') return { kind:'execution_failure', label:'Evaluation / application failed' };
  if (record.status === 'cancelled') return { kind:'pending', label:'Cancelled — no application' };
  if (record.status === 'invalid_proposal') return { kind:'blocked', label:'Invalid proposal blocked' };
  if (record.status === 'complete' && !changes && record.proposal?.episode_status === 'escalate') return { kind:'operator_review', label:'Operator review' };
  if (record.status === 'complete' && record.proposal && !changes && gate === 'rejected') return { kind:'hold', label:'Hold · gate not authorized' };
  if (gate === 'rejected') return { kind:'blocked', label:'Proposal blocked' };
  if (['accepted','modified'].includes(gate)) {
    if (!changes) return { kind:'hold', label:'Hold · monitor' };
    if (record.applied) return { kind:'applied', label:'Targets applied' };
    return { kind:'approved', label:gate === 'modified' ? 'Approved with limits' : 'Approved · not applied' };
  }
  return { kind:'pending', label:record.status === 'complete' ? 'Recorded' : 'Pending evaluation' };
}
