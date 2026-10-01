export function freshReading(sensor, time) {
  const age=(Date.parse(time)-Date.parse(sensor?.timestamp))/1000;
  return sensor?.quality==='good'&&age>=0&&age<=120&&Number.isFinite(sensor.value)?sensor.value:null;
}
export function feedbackView(loop, plant, plc) {
  const current=loop?.domain==='water'&&!!plc?.controller_generation&&loop.controller_generation===plc.controller_generation?loop:null;
  if(!current)return {loop:null,label:'Off',detail:'Start monitoring & control to enable automatic reviews.'};
  if(current.status==='stopped')return {loop:current,label:'Stopped · baseline control',detail:current.reason};
  if(!plant?.running)return {loop:current,label:'Paused · clock stopped',detail:'Resume the exercise clock to continue monitoring.'};
  if(current.status==='inferencing')return {loop:current,label:`${current.provider?.toUpperCase()} is analysing`,detail:'A fresh gate check is required before applying targets.'};
  const remaining=Math.max(0,(current.next_review_minute??plant.elapsed_minutes)-plant.elapsed_minutes);
  const last=current.calls_used>=current.max_calls;
  return {loop:current,label:current.observation_only?'Observing · no actuation':'Observing process response',
    detail:remaining>0?`${last?'Final observation ends':'Next automatic review'} at minute ${current.next_review_minute} · ${remaining} simulated min remaining`:'Waiting for the next review'};
}
export function changedTargets(initial, edited, live) {
  const changes={};
  for(const [key,value] of Object.entries(edited)) {
    if(key==='backwash_request'){if(value)changes[key]=true;continue;}
    if(value===initial[key])continue;
    if(live[key]!==initial[key])throw Error('A target changed while this form was open. Reopen Direct controls and review the live values.');
    changes[key]=value;
  }
  return changes;
}

// Preserve command order across workspace navigation and scenario resets.
export function createWaterCommandQueue(api, onPending = () => {}) {
  let tail = Promise.resolve(), count = 0;
  return (action, options = {}, config = {}) => {
    count += 1;
    onPending(true);
    const command = tail.then(async () => {
      const state = await api('/api/v1/state');
      let runId = state.active_run_id, nextConfig = null;
      if (action === 'configure' || !runId) {
        nextConfig = {...config, ...options};
        const created = await api('/api/v1/runs', {method:'POST', body:JSON.stringify(nextConfig)});
        runId = created.id;
        await api(`/api/v1/runs/${runId}/reset`, {method:'POST'});
      }
      if (action !== 'configure') {
        await api(`/api/v1/runs/${runId}/${action}`, {method:'POST',
          body:action === 'step' ? JSON.stringify(options) : undefined});
      }
      return {state:await api('/api/v1/state'), config:nextConfig};
    }).finally(() => {count -= 1; onPending(count > 0);});
    tail = command.catch(() => {});
    return command;
  };
}
