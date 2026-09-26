import React from "react";
import { HOSTED } from "./HostedSession";

async function api(path, payload, signal) {
  const response = await fetch(`/api/v1/agents${path}`, { signal, method:payload ? "POST":"GET", headers:{"Content-Type":"application/json"}, body:payload ? JSON.stringify(payload):undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function Help({ children, label }) {
  const id=React.useId();
  const [open,setOpen]=React.useState(false);
  const [position,setPosition]=React.useState({});
  const locate=e=>{const r=e.currentTarget.getBoundingClientRect();setPosition({left:Math.max(12,Math.min(r.left,window.innerWidth-252)),top:Math.max(12,r.top-116)});};
  return <span className="agent-help" onMouseEnter={locate} onFocus={locate}><button type="button" aria-label={label} aria-describedby={id} aria-expanded={open} onClick={()=>setOpen(v=>!v)} onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);e.currentTarget.blur();}}}>?</button><span id={id} role="tooltip" style={position} className={open?"visible":""}>{children}</span></span>;
}

function JsonEvidence({ title, value, open=false }) {
  return <details className="agent-evidence" open={open}><summary>{title}</summary><pre>{typeof value === "string" ? value : JSON.stringify(value,null,2)}</pre></details>;
}

function DecisionSummary({ record }) {
  const changes=Object.entries(record.proposal?.changes||{}).filter(([,value])=>value!==null);
  const approved=record.gate?.applied_values||record.gate?.applied||{};
  const reasons=record.gate?.violated_constraints||record.gate?.reasons||[];
  return <section className="agent-readable">
    <div className="agent-readable-status"><span className={`walk-verdict ${record.gate?.status}`}>{record.gate?.status||record.status}</span><strong>{record.applied?"Targets applied through gate":"No targets applied"}</strong></div>
    <h3>{record.proposal?.objective||record.proposal?.expected_effect||"Inference evidence"}</h3>
    <p>{record.proposal?.explanation||record.error||"Model response is pending."}</p>
    {!!changes.length&&<dl>{changes.map(([key,value])=><div key={key}><dt>{key.replaceAll("_"," ")}</dt><dd>{String(value)}{record.applied&&approved[key]!==undefined&&approved[key]!==null&&approved[key]!==value&&<small> → applied {String(approved[key])}</small>}</dd></div>)}</dl>}
    {!changes.length&&<p><strong>Hold current targets</strong> · no setpoint change proposed.</p>}
    {record.applied&&<p>Control lease: {record.lease_minutes||5} simulated minutes. Observe the HMI as the simulation advances.</p>}
    {!!reasons.length&&<div className="agent-readable-reasons"><strong>Why the gate intervened</strong><ul>{reasons.map(reason=><li key={reason}>{reason}</li>)}</ul></div>}
    {record.error&&<p role="alert">Validation / execution error: {record.error}</p>}
    <small>{record.proposal?.confidence!==undefined?`Model-reported confidence: ${Math.round(record.proposal.confidence*100)}% · `:""}{record.latency_seconds!==undefined?`${record.latency_seconds.toFixed(1)} s inference`:""} · Confidence is not a calibrated safety score.</small>
  </section>;
}

export default function AgentResearchRoom({ domain, setDomain, plant, initialRecordId = null }) {
  const [status,setStatus] = React.useState(null);
  const [records,setRecords] = React.useState([]);
  const [selected,setSelected] = React.useState(initialRecordId);
  const [detail,setDetail] = React.useState(null);
  const [thinking,setThinking] = React.useState(false);
  const [profile,setProfile] = React.useState("fast");
  const [knowledge,setKnowledge] = React.useState("lexical");
  const [evaluation,setEvaluation] = React.useState(()=>sessionStorage.getItem("ot-analysis-evaluate-only")==="true");
  const [provider,setProvider] = React.useState(()=>sessionStorage.getItem("ot-analysis-provider")==="jev"?"jev":"qwen");
  const [comparison,setComparison] = React.useState([]);
  const [activeJob,setActiveJob] = React.useState(null);
  const [study,setStudy] = React.useState("label_invariance");
  const [error,setError] = React.useState("");
  const [busy,setBusy] = React.useState(false);
  const [revision,refresh] = React.useReducer(n=>n+1,0);
  React.useEffect(()=>{sessionStorage.setItem("ot-analysis-provider",provider);},[provider]);
  React.useEffect(()=>{sessionStorage.setItem("ot-analysis-evaluate-only",String(evaluation));},[evaluation]);
  React.useEffect(()=>{
    const controller=new AbortController(); let timer;
    const poll=async()=>{
      try {
        const [s,r]=await Promise.all([api("/state",null,controller.signal),api(`/records?domain=${domain}`,null,controller.signal)]);
        if(!controller.signal.aborted){setStatus(s);setRecords(r);const done=s.jobs.find(j=>j.id===activeJob&&j.status==='complete');if(done){setSelected(done.record_id);setActiveJob(null);}}
        if(selected){const d=await api(`/records/${selected}`,null,controller.signal);if(!controller.signal.aborted)setDetail(d);
          const children=await Promise.all((d.comparison?.record_ids||[]).map(id=>api(`/records/${id}`,null,controller.signal)));
          if(!controller.signal.aborted)setComparison(children);}
      }catch(e){if(!controller.signal.aborted)setError(e.message);}
      if(!controller.signal.aborted)timer=setTimeout(poll,2500);
    };poll();return()=>{controller.abort();clearTimeout(timer);};
  },[domain,selected,revision,activeJob]);
  const run=async(kind)=>{
    setBusy(true);setError("");
    try{const job=await api(`/${domain}/${kind}`,kind==="study"?{kind:study,thinking}:{provider,thinking,evaluate_only:evaluation,knowledge_mode:knowledge,inference_profile:profile});setActiveJob(job.id);refresh();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  };
  const pending=status?.jobs.some(job=>job.status==="running");
  const qwenReady=status?.model.available && status?.model.model_pulled;
  const ready=provider==="jev"?status?.jev_available:qwenReady;
  const choose=(next)=>{setDomain(next);setSelected(null);setDetail(null);setRecords([]);setError("");};
  const apply=async(record)=>{setBusy(true);setError("");try{const job=await api(`/records/${record.id}/apply`,{});setActiveJob(job.id);refresh();}catch(e){setError(e.message);}finally{setBusy(false);}};
  const download=async(all=false)=>{
    let evidence=detail;
    try{if(all){const list=await api('/records?limit=100');evidence=await Promise.all(list.map(r=>api(`/records/${r.id}`)));}else if(detail?.comparison)evidence={...detail,decisions:comparison};}catch(e){setError(e.message);return;}
    const url=URL.createObjectURL(new Blob([JSON.stringify(evidence,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download=`agent-${all?"session":domain}-${all?Date.now():detail.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <main className="page agent-page">
    <div className="room-intro"><div><span className="eyebrow">{HOSTED ? "Cloud AI" : "Local AI"} · gated decisions · research evidence</span><h1>Agent inspection lab</h1><p>Inspect what the model received, what it said, what it proposed, and what the deterministic gate allowed.</p></div><span className={`infra-pill ${ready?"normal":"warning"}`}>{ready?"Model ready":"Model unavailable"}</span></div>
    <div className="agent-architecture"><div><span>01 · PROCESS CONTROL</span><strong>Deterministic PLC / baseline</strong><p>Runs the process and retains protection authority.</p></div><div><span>02 · SUPERVISORY AGENT</span><strong>{provider==="jev"?"Jev · typed decisions":status?.model.model || "Loading model…"}</strong><p>Uses sensor quality, trends, equipment and current targets.</p></div><div><span>03 · REQUIRED GATE</span><strong>Validate → allow or reject</strong><p>Bounds, freshness, operating mode and protective conditions.</p></div></div>
    <div className="training-domains">{["water","nuclear","grid"].map(d=><button key={d} disabled={busy} className={domain===d?"active":""} aria-pressed={domain===d} onClick={()=>choose(d)}>{d==="water"?"Water agent":d==="nuclear"?"Nuclear agent":"Grid agent"}</button>)}</div>
    {error && <div className="training-error" role="alert">{error}<button onClick={()=>setError("")}>Dismiss</button></div>}
    <section className="agent-controls"><div>
      <h2>Next analysis</h2>
      <label className="agent-option-label">Model <Help label="About model switching">Changes the next analysis only. Plant state and records stay intact.</Help></label>
      <div className="agent-model-options" role="group" aria-label="Analysis model">
        <button aria-pressed={provider==="qwen"} onClick={()=>setProvider("qwen")}><strong>Qwen</strong><small>{HOSTED?"Cloudflare":"Local Ollama"}</small></button>
        <button aria-pressed={provider==="jev"} onClick={()=>setProvider("jev")}><strong>Jev</strong><small>OpenRouter · typed choices</small></button>
      </div>
      <div className="agent-option-label"><label><input type="checkbox" checked={!evaluation} onChange={e=>setEvaluation(!e.target.checked)} /> Apply approved targets</label><Help label="About applying targets">Live gate rechecks first. HMI targets update for up to 5 simulated minutes; then prior targets return. Recovery is measured, not guaranteed.</Help></div>
      <div className="agent-run-actions"><button disabled={busy||pending||!ready} onClick={()=>run("cycle")}>{evaluation?"Evaluate proposal":"Run & apply through gate"}</button><button disabled={busy||pending||!qwenReady||!status?.jev_available} onClick={()=>run("compare")}>Compare both</button><Help label="About comparing models">Same captured state, two AI calls. Neither applies automatically. Select one for a fresh gate check.</Help></div>
      {provider==="jev"&&!status?.jev_available&&<small role="status">Jev is not configured or its connection is unavailable.</small>}
      <details className="agent-settings"><summary>Analysis options</summary>
        <label>Decision profile<select disabled={provider==="jev"} value={profile} onChange={e=>{setProfile(e.target.value);if(e.target.value==="fast")setThinking(false);}}><option value="standard">Standard</option><option value="fast">Fast · concise</option></select></label>
        <label>Plant knowledge<select disabled={provider==="jev"} value={knowledge} onChange={e=>setKnowledge(e.target.value)}><option value="off">Live context</option><option value="lexical">Plant records · BM25</option>{!HOSTED&&<option value="hybrid">Plant records · embeddings</option>}</select></label>
        <label><input type="checkbox" disabled={HOSTED||profile==="fast"||provider==="jev"} checked={thinking} onChange={e=>setThinking(e.target.checked)} /> Capture emitted reasoning</label>
        <Help label="About model context">Qwen uses the selected knowledge profile. Jev receives live plant context and bounded candidates; it returns choices and probabilities, not reasoning text.</Help>
      </details>
    </div><div><h2>Controlled alignment study</h2><p>Paired Qwen runs. Fixed process inputs. No actuation.</p><label>Study<select value={study} onChange={e=>setStudy(e.target.value)}><option value="label_invariance">Socioeconomic-label invariance</option><option value="repeatability">Identical-input repeatability</option><option value="safety_priority">Safety versus output pressure</option></select></label><button disabled={HOSTED||busy||pending||!qwenReady} onClick={()=>run("study")} title={HOSTED?"Available in the local lab":undefined}>Run paired study</button></div></section>
    {pending && <div className="agent-job" role="status">{HOSTED?"Cloud inference is running.":"Local inference is running."} Deterministic process control continues independently. Results will appear below.</div>}

    {status?.jobs.slice(-3).filter(j=>j.status==="failed").map(j=><div className="training-error" key={j.id}>Agent job failed: {j.error}</div>)}
    <div className="agent-review"><section className="agent-records"><h2>Decision records</h2><button disabled={!records.length} onClick={()=>download(true)}>Export session · JSON</button>{records.length?records.map(r=><button key={r.id} className={selected===r.id?"selected":""} onClick={()=>{setSelected(r.id);setDetail(null);}}><span>{r.record_type==="comparison"?"Qwen / Jev comparison":r.record_type==="study"?"Paired study":r.model_name || "Model decision"}</span><strong>{r.study?.kind || r.proposal?.objective || r.proposal?.expected_effect || r.status}</strong><small>{new Date(r.created_at).toLocaleTimeString()} · {r.gate?.status || r.status}{r.applied?" · applied":""}</small></button>):<p>No recorded inferences for this domain yet.</p>}</section><section className="agent-detail">{detail?<><div className="agent-detail-heading"><h2>{detail.record_type==="study"?"Study evidence":"Decision evidence"}</h2><button onClick={()=>download(false)}>Export full record</button></div>{detail.record_type!=="study"&&detail.record_type!=="comparison"&&<DecisionSummary record={detail} />}
      {detail.comparison&&<><div className="agent-comparison">{comparison.map(record=><section key={record.id}><h3>{record.provider==="jev"?"Jev":"Qwen"}</h3><DecisionSummary record={record}/><button disabled={busy||pending||!!record.application_id||record.gate?.status==="rejected"||!Object.values(record.proposal?.changes||{}).some(v=>v!==null)} onClick={()=>apply(record)}>{record.application_id?"Application recorded":"Apply through live gate"}</button><button onClick={()=>setSelected(record.id)}>Inspect record</button></section>)}</div>{detail.comparison.failures?.map(f=><p role="alert" key={f.provider}>{f.provider}: {f.error}</p>)}</>}
      {detail.response?.answers&&<JsonEvidence title="Jev choice and probabilities" value={detail.response.answers} open/>}<p className="agent-interpretation">{detail.interpretation} Gate behavior and subsequent process measurements are separate evidence.</p>{detail.study && <JsonEvidence title="Study result and interpretation" value={detail.study} open />}
      {detail.record_type!=="comparison"&&<>
      <JsonEvidence title="1. Exact model request: instructions, inputs and generation settings" value={detail.request} />
      {detail.inference_profile && <JsonEvidence title="Inference profile and context compression" value={detail.inference_profile} />}
      {detail.retrieval && <JsonEvidence title="Retrieved plant knowledge and sources" value={detail.retrieval} />}
      {detail.before && <JsonEvidence title="Captured process and controller context" value={detail.before} />}
      <JsonEvidence title="2. Model-emitted reasoning (unverified self-report)" value={detail.response?.message?.thinking || "No reasoning text returned for this call. This does not imply the model performed no internal computation."} />
      <JsonEvidence title="3. Structured proposal and stated rationale" value={detail.proposal || detail.response?.message?.content || detail.error || "Waiting for output"} open />
      <JsonEvidence title="4. Deterministic gate decision" value={{...detail.gate,actually_applied:detail.applied ?? false,evaluation_only:detail.evaluate_only}} open />
      <JsonEvidence title="5. Observed outcome and attribution limits" value={detail.outcome || "No later process observation recorded yet."} />
      <JsonEvidence title="Model provenance and timing" value={{model:detail.response?.model,manifest:detail.model_manifest,latency_seconds:detail.latency_seconds,profile:detail.inference_profile?.profile,prompt_seconds:detail.response?.prompt_eval_duration/1e9,generation_seconds:detail.response?.eval_duration/1e9,retrieval_ms:detail.retrieval?.retrieval_ms,prompt_tokens:detail.response?.prompt_eval_count,generated_tokens:detail.response?.eval_count,done_reason:detail.response?.done_reason}} />
      </>}
      {detail.comparison&&<JsonEvidence title="Shared captured state" value={detail.before}/>}
    </>:<div className="agent-empty"><h2>Select a decision to inspect</h2><p>A reasoning trace can be useful evidence, but it does not establish intent, alignment or absence of bias. Start with a paired study and inspect its individual records.</p></div>}</section></div>
  </main>;
}
