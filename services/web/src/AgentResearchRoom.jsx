import React from "react";
import { HOSTED } from "./HostedSession";

async function api(path, payload, signal) {
  const response = await fetch(`/api/v1/agents${path}`, { signal, method:payload ? "POST":"GET", headers:{"Content-Type":"application/json"}, body:payload ? JSON.stringify(payload):undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function JsonEvidence({ title, value, open=false }) {
  return <details className="agent-evidence" open={open}><summary>{title}</summary><pre>{typeof value === "string" ? value : JSON.stringify(value,null,2)}</pre></details>;
}

function DecisionSummary({ record }) {
  const changes=Object.entries(record.proposal?.changes||{}).filter(([,value])=>value!==null);
  const reasons=record.gate?.violated_constraints||record.gate?.reasons||[];
  return <section className="agent-readable">
    <div className="agent-readable-status"><span className={`walk-verdict ${record.gate?.status}`}>{record.gate?.status||record.status}</span><strong>{record.applied?"Targets applied through gate":"No targets applied"}</strong></div>
    <h3>{record.proposal?.objective||record.proposal?.expected_effect||"Inference evidence"}</h3>
    <p>{record.proposal?.explanation||record.error||"Model response is pending."}</p>
    {!!changes.length&&<dl>{changes.map(([key,value])=><div key={key}><dt>{key.replaceAll("_"," ")}</dt><dd>{String(value)}</dd></div>)}</dl>}
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
  const [thinking,setThinking] = React.useState(!HOSTED);
  const [evaluation,setEvaluation] = React.useState(true);
  const [study,setStudy] = React.useState("label_invariance");
  const [error,setError] = React.useState("");
  const [busy,setBusy] = React.useState(false);
  const [revision,refresh] = React.useReducer(n=>n+1,0);
  React.useEffect(()=>{
    const controller=new AbortController(); let timer;
    const poll=async()=>{
      try {
        const [s,r]=await Promise.all([api("/state",null,controller.signal),api(`/records?domain=${domain}`,null,controller.signal)]);
        if(!controller.signal.aborted){setStatus(s);setRecords(r);}
        if(selected){const d=await api(`/records/${selected}`,null,controller.signal);if(!controller.signal.aborted)setDetail(d);}
      }catch(e){if(!controller.signal.aborted)setError(e.message);}
      if(!controller.signal.aborted)timer=setTimeout(poll,2500);
    };poll();return()=>{controller.abort();clearTimeout(timer);};
  },[domain,selected,revision]);
  const run=async(kind)=>{
    setBusy(true);setError("");
    try{await api(`/${domain}/${kind}`,kind==="study"?{kind:study,thinking}:{thinking,evaluate_only:evaluation});refresh();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  };
  const pending=status?.jobs.some(job=>job.status==="running");
  const ready=status?.model.available && status?.model.model_pulled;
  const choose=(next)=>{setDomain(next);setSelected(null);setDetail(null);setRecords([]);setError("");};
  const download=()=>{
    const url=URL.createObjectURL(new Blob([JSON.stringify(detail,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download=`agent-${domain}-${detail.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <main className="page agent-page">
    <div className="room-intro"><div><span className="eyebrow">{HOSTED ? "Cloud AI" : "Local AI"} · gated decisions · research evidence</span><h1>Agent inspection lab</h1><p>Inspect what the model received, what it said, what it proposed, and what the deterministic gate allowed.</p></div><span className={`infra-pill ${ready?"normal":"warning"}`}>{ready?"Model ready":"Model unavailable"}</span></div>
    <div className="agent-architecture"><div><span>01 · PROCESS CONTROL</span><strong>Deterministic PLC / baseline</strong><p>Runs the process and retains protection authority.</p></div><div><span>02 · SUPERVISORY AGENT</span><strong>{status?.model.model || "Loading model…"}</strong><p>Uses sensor quality, trends, equipment and current targets.</p></div><div><span>03 · REQUIRED GATE</span><strong>Validate → allow or reject</strong><p>Bounds, freshness, operating mode and protective conditions.</p></div></div>
    <div className="training-domains">{["water","nuclear","grid"].map(d=><button key={d} disabled={busy} className={domain===d?"active":""} aria-pressed={domain===d} onClick={()=>choose(d)}>{d==="water"?"Water agent":d==="nuclear"?"Nuclear agent":"Grid agent"}</button>)}</div>
    {error && <div className="training-error" role="alert">{error}<button onClick={()=>setError("")}>Dismiss</button></div>}
    <section className="agent-controls"><div><h2>Run a supervisory decision</h2><p>Current control-room mode: <strong>{plant?.controller_mode || "unknown"}</strong>. Equipment and incident controls are never available to the AI.</p><label><input type="checkbox" disabled={HOSTED} checked={thinking} onChange={e=>setThinking(e.target.checked)} /> {HOSTED ? "Hosted mode captures the final rationale" : "Capture model-emitted reasoning (slower)"}</label><label><input type="checkbox" checked={evaluation} onChange={e=>setEvaluation(e.target.checked)} /> Evaluate on a captured copy; apply no controls</label><button disabled={busy||pending||!ready} onClick={()=>run("cycle")}>Run agent through gate</button></div><div><h2>Controlled alignment study</h2><p>Paired runs hold process inputs fixed. Every study evaluates on detached state and applies no controls.</p><label>Study<select value={study} onChange={e=>setStudy(e.target.value)}><option value="label_invariance">Socioeconomic-label invariance</option><option value="repeatability">Identical-input repeatability</option><option value="safety_priority">Safety versus output-pressure request</option></select></label><button disabled={HOSTED||busy||pending||!ready} onClick={()=>run("study")} title={HOSTED ? "Batch studies are available in the local lab" : undefined}>Run paired study · 2 inferences</button></div></section>
    {pending && <div className="agent-job" role="status">{HOSTED?"Cloud inference is running.":"Local inference is running."} Deterministic process control continues independently. Results will appear below.</div>}
    {status?.jobs.slice(-3).filter(j=>j.status==="failed").map(j=><div className="training-error" key={j.id}>Agent job failed: {j.error}</div>)}
    <div className="agent-review"><section className="agent-records"><h2>Decision records</h2>{records.length?records.map(r=><button key={r.id} className={selected===r.id?"selected":""} onClick={()=>{setSelected(r.id);setDetail(null);}}><span>{r.record_type==="study"?"Paired study":r.request?.model || (HOSTED?"Cloud model decision":"Local model decision")}</span><strong>{r.study?.kind || r.proposal?.objective || r.proposal?.expected_effect || r.status}</strong><small>{new Date(r.created_at).toLocaleTimeString()} · {r.gate?.status || r.status}{r.applied?" · applied":""}</small></button>):<p>No recorded inferences for this domain yet.</p>}</section><section className="agent-detail">{detail?<><div className="agent-detail-heading"><h2>{detail.record_type==="study"?"Study evidence":"Decision evidence"}</h2><button onClick={download}>Export full record</button></div>{detail.record_type!=="study"&&<DecisionSummary record={detail} />}<p className="agent-interpretation">{detail.interpretation} Gate behavior and subsequent process measurements are separate evidence.</p>{detail.study && <JsonEvidence title="Study result and interpretation" value={detail.study} open />}
      <JsonEvidence title="1. Exact model request: instructions, inputs and generation settings" value={detail.request} />
      {detail.before && <JsonEvidence title="Captured process and controller context" value={detail.before} />}
      <JsonEvidence title="2. Model-emitted reasoning (unverified self-report)" value={detail.response?.message?.thinking || "No reasoning text returned for this call. This does not imply the model performed no internal computation."} />
      <JsonEvidence title="3. Structured proposal and stated rationale" value={detail.proposal || detail.response?.message?.content || detail.error || "Waiting for output"} open />
      <JsonEvidence title="4. Deterministic gate decision" value={{...detail.gate,actually_applied:detail.applied ?? false,evaluation_only:detail.evaluate_only}} open />
      <JsonEvidence title="5. Observed outcome and attribution limits" value={detail.outcome || "No later process observation recorded yet."} />
      <JsonEvidence title="Model provenance and timing" value={{model:detail.response?.model,manifest:detail.model_manifest,latency_seconds:detail.latency_seconds,prompt_tokens:detail.response?.prompt_eval_count,generated_tokens:detail.response?.eval_count,done_reason:detail.response?.done_reason}} />
    </>:<div className="agent-empty"><h2>Select a decision to inspect</h2><p>A reasoning trace can be useful evidence, but it does not establish intent, alignment or absence of bias. Start with a paired study and inspect its individual records.</p></div>}</section></div>
  </main>;
}
