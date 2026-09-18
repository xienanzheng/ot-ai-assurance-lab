import React from "react";

const names = { water: "Water treatment", nuclear: "Nuclear PWR", grid: "Power grid" };
const initialTags = { water: "clearwell_level_pct", nuclear: "reactor_power_pct", grid: "frequency_model_hz" };
const guidance = {
  water: ["Establish stable pressure, storage, pH and chlorine residual.", "Run a fault from Water HMI and compare reported sensors with model estimates.", "Acknowledge alarms, inspect the PLC response, and export delivered-water and energy results."],
  nuclear: ["Run nominal conditions, then select a transient and step through its onset.", "Observe primary-loop flow, steam-generator inventory and the first-out trip indication.", "Track residual heat after shutdown and verify that AI proposals cannot change protection."],
  grid: ["Establish normal dispatch and inspect supply, demand and battery state of charge.", "Run a line or generator outage and inspect each electrical island and its served load.", "Compare unserved energy and alarm duration across repeated dispatch strategies."],
};
const pretty = (s) => s.replaceAll("_", " ");

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    let detail = `${response.status}: request failed`;
    try { const body = await response.json(); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body); } catch { /* Keep HTTP status. */ }
    throw new Error(detail);
  }
  return response.json();
}

function Trend({ samples, tag, unit }) {
  const points = samples.filter((s) => Number.isFinite(s.values[tag]));
  if (points.length < 2) return <p className="training-empty">Step or start the simulation to build a trend.</p>;
  const values = points.map((s) => s.values[tag]);
  const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const start = points[0].minute, end = points.at(-1).minute;
  const coords = points.map((s) => `${50 + (s.minute-start)/(end-start || 1)*830},${175-(s.values[tag]-low)/span*135}`).join(" ");
  return <svg viewBox="0 0 920 220" role="img" aria-label={`${pretty(tag)} from minute ${start} to ${end}, minimum ${low.toFixed(3)}, maximum ${high.toFixed(3)} ${unit}`}>
    {[40, 85, 130, 175].map((y) => <line key={y} x1="50" x2="880" y1={y} y2={y} stroke="#30414c" />)}
    <polyline points={coords} fill="none" stroke="#60ddc4" strokeWidth="2.5" />
    <text x="50" y="25">{high.toFixed(3)} {unit}</text><text x="50" y="198">{low.toFixed(3)} {unit}</text>
    <text x="220" y="212">Minute {start}</text><text x="790" y="212">Minute {end}</text>
  </svg>;
}

export default function TrainingRoom({ domain, onDomainChange, water, infrastructure, scenarios, infrastructureScenarios, onOpenRoom, onWaterAction, onInfrastructureCommand }) {
  const setDomain = onDomainChange;
  const [report, setReport] = React.useState(null);
  const [error, setError] = React.useState("");
  const [fetchError, setFetchError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [tag, setTag] = React.useState(initialTags[domain]);
  const [revision, refresh] = React.useReducer((n) => n + 1, 0);
  const plant = domain === "water" ? water : infrastructure[domain];
  const choices = domain === "water" ? scenarios : infrastructureScenarios[domain];

  React.useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try {
        const next = await request(`/api/v1/training/${domain}`, { signal: controller.signal });
        if (!controller.signal.aborted) { setReport(next); setFetchError(""); }
      } catch (problem) { if (!controller.signal.aborted) setFetchError(problem.message); }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 1500);
    };
    poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [domain, revision]);

  const perform = async (callback) => {
    setBusy(true); setError("");
    try { await callback(); refresh(); } catch (problem) { setError(problem.message); }
    finally { setBusy(false); }
  };
  const command = (action, options = {}) => perform(() => domain === "water" ? onWaterAction(action, options) : onInfrastructureCommand(domain, action, options));
  const annotate = (body) => perform(async () => {
    await request(`/api/v1/training/${domain}`, { method: "POST", body: JSON.stringify(body) });
    if (body.action === "note") setNote("");
  });
  const selectDomain = (next) => { setDomain(next); setTag(initialTags[next]); setReport(null); setNote(""); setError(""); };
  const current = report?.domain === domain ? report : null;
  const tags = Object.keys(plant?.sensors || {}).sort();
  const sensor = plant?.sensors?.[tag];
  const trip = plant?.equipment?.reactor_protection?.first_out;
  return <main className="page training-page">
    <div className="room-intro"><div><span className="eyebrow">Operator exercise workspace</span><h1>Run. Observe. Explain.</h1><p>One exercise record for each control room, with minute samples, alarm transitions and operator observations.</p></div><button onClick={() => onOpenRoom(domain === "water" ? "hmi" : domain)}>Open {names[domain]} HMI →</button></div>
    <div className="training-domains" role="group" aria-label="Simulation domain">{Object.entries(names).map(([id, name]) => <button disabled={busy} aria-pressed={domain === id} className={domain === id ? "active" : ""} key={id} onClick={() => selectDomain(id)}>{name}</button>)}</div>
    {(error || fetchError) && <div role="alert" className="training-error">{error || fetchError}</div>}
    <section className="training-toolbar">
      <label>Scenario · selecting starts a fresh record<select disabled={busy} value={plant?.scenario || ""} onChange={(e) => command("configure", { scenario: e.target.value })}>{choices.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
      <div className="training-clock"><small>{plant?.running ? "RUNNING" : "PAUSED"}</small><strong>{plant?.elapsed_minutes ?? 0} <small>min</small></strong></div>
      <button disabled={busy || !plant} onClick={() => command(plant.running ? "pause" : "start")}>{plant?.running ? "Pause" : "Start / resume"}</button>
      <button disabled={busy || !plant} onClick={() => command("step", { minutes: 1 })}>+1 minute</button>
      {domain !== "water" && <button disabled={busy || !plant} onClick={() => command("step", { minutes: 10 })}>+10 minutes</button>}
      <button disabled={busy || !plant} onClick={() => command("reset")}>Reset exercise</button>
    </section>
    <p className="training-caption">{choices.find((s) => s.id === plant?.scenario)?.description} Export your record before changing scenario or resetting.</p>
    <section className="training-metrics">
      <div><span>Recorded samples</span><strong>{current?.sample_count ?? "—"}</strong><small>One per simulated minute, including initial state</small></div>
      <div><span>Time in critical condition</span><strong>{current?.critical_minutes ?? "—"} <small>min</small></strong><small>Measured at minute boundaries</small></div>
      <div><span>Unacknowledged alarms</span><strong>{current?.alarms.filter((a) => !a.acknowledged).length ?? "—"}</strong><small>Acknowledgement leaves protection active</small></div>
      {Object.entries(current?.metrics || {}).map(([name, value]) => <div key={name}><span>{pretty(name)}</span><strong>{Number(value).toFixed(2)}</strong><small>Integrated over this exercise</small></div>)}
    </section>
    <div className="training-columns">
      <section className="infra-card training-trend"><div className="infra-card-title"><span>Process trend · latest 120 minutes</span><strong>{sensor ? `${Number(sensor.value).toFixed(3)} ${sensor.unit}` : "Waiting"}</strong></div><label>Sensor<select value={tag} onChange={(e) => setTag(e.target.value)}>{tags.map((name) => <option value={name} key={name}>{pretty(name)} · {plant.sensors[name].unit}</option>)}</select></label><Trend samples={current?.recent_samples || []} tag={tag} unit={sensor?.unit || ""} /><small>Reported quality: {sensor?.quality || "unavailable"}. Export JSON includes quality and commands for each sample.</small></section>
      <section className="infra-card training-guide"><div className="infra-card-title">Exercise objectives</div><ol>{guidance[domain].map((step) => <li key={step}>{step}</li>)}</ol>{trip && <div className="training-trip"><strong>First-out trip · minute {trip.minute}</strong><p>{trip.causes.join("; ")}</p><small>Causes detected at the same scan are recorded together.</small></div>}{domain === "grid" && plant?.model_health?.islands?.map((island) => <div className="training-island" key={island.reference_bus}><strong>{island.buses.join(" · ")}</strong><span>{island.energized ? "Energized" : "De-energized"} · {island.served_mw.toFixed(1)} / {island.demand_mw.toFixed(1)} MW served</span></div>)}</section>
    </div>
    <div className="training-columns">
      <section className="infra-card"><div className="infra-card-title"><span>Alarm annunciator</span><b>{current?.alarms.length || 0}</b></div>{current?.alarms.length ? current.alarms.map((alarm) => <div className={`training-alarm ${alarm.severity}`} key={alarm.occurrence}><div><strong>{alarm.code}</strong><p>{alarm.message}</p><small>First observed: minute {alarm.first_minute}</small></div><button disabled={busy || alarm.acknowledged} onClick={() => annotate({ action: "acknowledge", occurrence: alarm.occurrence })}>{alarm.acknowledged ? "Acknowledged" : "Acknowledge"}</button></div>) : <p className="training-empty">No active process alarms.</p>}</section>
      <section className="infra-card"><div className="infra-card-title">Operator log</div><form onSubmit={(e) => { e.preventDefault(); annotate({ action: "note", note }); }}><label>Observation<textarea maxLength={500} required value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed, what you observed, and why you acted…" /></label><button disabled={busy || !note.trim()}>Record observation</button></form><div className="training-events">{current?.events.map((event) => <div key={event.id}><small>T+{event.minute} min · {event.kind}</small><p>{event.message}</p></div>)}</div></section>
    </div>
    <section className="training-export"><div><strong>Exercise evidence</strong><p>{current?.retention || "Loading record…"}</p>{!!current?.dropped_samples && <p>{current.dropped_samples} older samples have rolled off; totals cover the full exercise.</p>}</div><a href={`/api/v1/training/${domain}/export?format=csv`}>Download CSV</a><a href={`/api/v1/training/${domain}/export?format=json`}>Download JSON + event log</a></section>
  </main>;
}
