import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

async function api(path,body){const r=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const data=await r.json(); if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)); return data;}
function Chart({history,p}){
 const rows=history.filter(s=>s.readings[p.sensor]); if(rows.length<2)return <div className="empty">Collecting response history…</div>;
 const vals=rows.flatMap(s=>[s.target,s.readings[p.sensor].value]); const lo=Math.min(...vals,p.objective[0])-.1*(p.maximum-p.minimum),hi=Math.max(...vals,p.objective[1])+.1*(p.maximum-p.minimum);
 const start=rows[0].process_time,span=Math.max(1,rows.at(-1).process_time-start),x=s=>60+(s.process_time-start)/span*740,y=v=>220-(v-lo)/(hi-lo)*180;
 const path=fn=>rows.map((s,i)=>(i?'L':'M')+x(s)+','+y(fn(s))).join(' ');
 return <svg viewBox="0 0 830 270" role="img" aria-label={`${p.sensor}: measured response and controller target over process time`}>
  <rect x="60" y={y(p.objective[1])} width="740" height={y(p.objective[0])-y(p.objective[1])} fill="#dbeedc"/>
  {[0,.5,1].map(t=><g key={t}><line x1="60" x2="800" y1={40+t*180} y2={40+t*180} stroke="#dbe1e3"/><text x="4" y={45+t*180}>{(hi-t*(hi-lo)).toFixed(2)}</text></g>)}
  <path d={path(s=>s.target)} fill="none" stroke="#ab6e20" strokeDasharray="6 5" strokeWidth="2"/>
  <path d={path(s=>s.readings[p.sensor].value)} fill="none" stroke="#146046" strokeWidth="3"/>
  <text x="60" y="254">{(start/60).toFixed(1)} min</text><text x="730" y="254">{(rows.at(-1).process_time/60).toFixed(1)} min</text>
 </svg>;
}
function App(){
 const [data,setData]=useState(null),[records,setRecords]=useState([]),[error,setError]=useState(''),[connectionError,setConnectionError]=useState(''),[pending,setPending]=useState(false);
 const [provider,setProvider]=useState('qwen'),[policy,setPolicy]=useState('off'),[apply,setApply]=useState(false),[limit,setLimit]=useState(3),[scenario,setScenario]=useState('drift');
 const refresh=async()=>{const [d,r]=await Promise.all([api('status'),api('records')]);setData(d);setRecords(r);};
 useEffect(()=>{const poll=()=>refresh().then(()=>setConnectionError('')).catch(e=>setConnectionError(e.message));poll();const t=setInterval(poll,1500);return()=>clearInterval(t);},[]);
 const act=async(path,body)=>{setPending(true);setError('');try{await api(path,body);await refresh();}catch(e){setError(e.message);}finally{setPending(false);}};
 if(!data)return <main><h1>Connecting to the local bench…</h1>{(error||connectionError)&&<p role="alert">{error||connectionError}</p>}</main>;
 const p=data.package,s=data.snapshot,busy=pending||data.busy,reading=s?.readings[p.sensor];
 return <><header><a href="/" className="brand">Airgap the AI <span>Local V2</span></a><div className="status">{s?.critical||s?.trip_latched?'Protection active':s?.armed?'Simulated control armed':'Observation only'}</div><a href="/api/export" download="v2-evidence.json">Export evidence</a></header>
 <main><div className="title"><div><h1>{p.title}</h1><p>Observe. Propose. Verify the response.</p></div><div className="clock">{((s?.process_time||0)/60).toFixed(1)}<small>process minutes · 1×</small></div></div>
 {(error||connectionError)&&<div className="error" role="alert">{error||connectionError}</div>}{data.capture_error&&<div className="error" role="status">Telemetry: {data.capture_error}</div>}
 <div className="workspace"><section className="process"><div className="readings"><div><label>Measured {p.sensor.replaceAll('_',' ')}</label><strong>{reading?.value.toFixed(3)??'—'} <small>{p.unit}</small></strong></div><div><label>Accepted controller target</label><strong>{s?.target.toFixed(3)??'—'} <small>{p.unit}</small></strong></div><div><label>Objective</label><strong>{p.objective.join('–')}</strong></div></div>
 <Chart history={data.history} p={p}/><div className="legend"><span>━ Measured</span><span>┄ Controller target</span><span>▰ Objective band</span></div>
 <div className="process-state"><span>Flow: {s?.readings.flow.value??'—'} L/s</span><span>Sensor: {reading?.quality??'—'}</span><span>Trip: {s?.trip_latched?'latched':'clear'}</span><span>Observe for: {Math.max(0,(s?.wait_until||0)-(s?.process_time||0)).toFixed(0)} s</span></div>
 <div className="scenario"><label htmlFor="scenario">Exercise</label><select id="scenario" value={scenario} onChange={e=>setScenario(e.target.value)}>{[['drift','Gradual drift'],['critical','Critical transition'],['no_flow','Missing flow'],['bad_sensor','Bad sensor quality'],['stale_sensor','Stale sensor'],['override','Operator override'],['normal','Clear disturbance'],['reset','New bench session']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select><button disabled={busy} onClick={()=>act('scenario',{name:scenario})}>Load exercise</button></div>
 </section><aside><h2>Decision controls</h2><label htmlFor="model">Model</label><select id="model" value={provider} onChange={e=>setProvider(e.target.value)}>{Object.entries(data.providers).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
 <label htmlFor="audit" title="Off skips review; observe reviews in the background; required blocks a new command until a matching pass.">Audit policy</label><select id="audit" value={policy} onChange={e=>setPolicy(e.target.value)}><option value="off">Off</option><option value="observe">Background review</option><option value="required">Require a pass</option></select><small>{data.auditor} · Active: {data.policy}. Arm to adopt a change.</small>
 <button disabled={busy||data.feedback.active} onClick={()=>act('arm',{policy})}>Arm simulated control</button>
 <label className="check"><input type="checkbox" checked={apply} onChange={e=>setApply(e.target.checked)}/> Apply through gate</label>
 <button className="primary" disabled={busy||data.feedback.active||!s||(apply&&!s.armed)} onClick={()=>act('analysis',{provider,apply})}>{data.busy?'Analysing…':'Analyse now'}</button>
 <div className="monitor"><h3>Observe & adjust</h3><label htmlFor="budget">Decision budget</label><input id="budget" type="number" min="1" max="12" value={limit} onChange={e=>setLimit(Number(e.target.value))}/><button disabled={busy||data.feedback.active||!s||(apply&&!s.armed)} onClick={()=>act('feedback',{provider,apply,limit})}>Start monitoring</button><p>{data.feedback.calls}/{data.feedback.limit} decisions · {data.feedback.reason}</p></div>
 <button className="stop" onClick={()=>act('stop',{})}>Stop AI control</button><small>Stops new requests. The accepted target remains.</small></aside></div>
 <section className="decisions"><div className="section-title"><h2>Decision records</h2><span>{records.length} exchanges</span></div>{records.length===0?<p className="empty">Choose a model and analyse the captured process state.</p>:records.slice(0,30).map(r=><article key={r.id}>
 <div className="record-heading"><h3>{r.proposal?.status==='adjust'?`Proposed target: ${r.input?.snapshot?.target??'—'} → ${r.proposal.target} ${r.input?.package?.unit||''}`:r.proposal?.status==='escalate'?'Operator review required':r.proposal?.status==='hold'?'Hold target':r.error||'Analysis running'}</h3><span className={'badge '+(r.status==='applied'?'ok':'')}>{r.status.replaceAll('_',' ')}</span></div><p>{r.input?.package?.id || 'Earlier record'} · {r.provider} · {r.inference_seconds?.toFixed(1)??'—'} s{r.decision_evidence?.attempts?.length>1&&' · 2 inference passes'}</p>
 <p>{r.proposal?.rationale&&`Model explanation: ${r.proposal.rationale}`}</p><div className="result"><span>Proposed: <b>{r.proposal?.target??'No change'}</b></span><span>Accepted: <b>{r.command?.actually_applied?r.command.accepted_target:'None'}</b></span><span>Outcome: <b>{r.outcome?.status||'Not started'}</b></span></div>
 {r.audit&&<p className="audit"><b>{r.audit_evidence?.verdict_source==='deterministic checks'?'Check':'Audit'} {r.audit.status}</b> — {r.audit.reason}<small> · {r.audit_provider}</small></p>}{r.gate?.reasons?.length>0&&<p>{r.gate.reasons.join(' · ')}</p>}
 <details><summary>Structured proposal & evidence</summary><pre>{JSON.stringify(r,null,2)}</pre></details></article>)}</section>
 <footer>Independent local test bench · Process package {p.id} / {p.version}</footer></main></>;
}
createRoot(document.getElementById('root')).render(<App/>);
