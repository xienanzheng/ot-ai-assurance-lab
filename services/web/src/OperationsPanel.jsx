import React from "react";

async function call(domain, payload, signal) {
  const response = await fetch(`/api/v1/operations/${domain}`, {
    method: payload ? "POST" : "GET", signal,
    headers: { "Content-Type": "application/json" }, body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function EquipmentCard({ device, submit, busy }) {
  const [mode, setMode] = React.useState(device.mode);
  const [pct, setPct] = React.useState(device.setpoint_pct);
  const [dirty, setDirty] = React.useState(false);
  React.useEffect(() => {
    if (!dirty) { setMode(device.mode); setPct(device.setpoint_pct); }
  }, [device.mode, device.setpoint_pct, dirty]);
  return <article className={`ops-device ${device.status}`}>
    <div className="ops-device-head"><span>{device.tag}</span><b>{device.status}</b></div>
    <h3>{device.name}</h3><small>{device.system}</small>
    <div className="ops-output"><strong>{device.output.toFixed(1)}</strong><span>{device.unit}</span></div>
    <div className="ops-feedback"><span style={{ width: `${device.feedback_pct}%` }} /></div>
    <p>{device.effect}</p>
    <div className="ops-readback"><span>Feedback <b>{device.feedback_pct}%</b></span><span>Runtime <b>{device.runtime_min} min</b></span><span>Starts <b>{device.starts}</b></span></div>
    <label>Requested mode<select aria-label={`${device.tag} mode`} value={mode} disabled={busy} onChange={(e) => { setMode(e.target.value); setDirty(true); }}><option value="auto">Auto / standby logic</option><option value="run">Run at setpoint</option><option value="off">Off</option></select></label>
    <label>Setpoint <strong>{pct}%</strong><input aria-label={`${device.tag} setpoint`} disabled={busy || mode !== "run"} type="range" min="0" max="100" step="5" value={pct} onChange={(e) => { setPct(Number(e.target.value)); setDirty(true); }} /></label>
    <button disabled={busy || !dirty} onClick={async () => { if (await submit({ action: "equipment", changes: { [device.tag]: { mode, setpoint_pct: pct } } })) setDirty(false); }}>Apply {device.tag} request</button>
  </article>;
}

export default function OperationsPanel({ domain }) {
  const [data, setData] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [connection, setConnection] = React.useState("");
  const [filter, setFilter] = React.useState("All systems");
  React.useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try { const next = await call(domain, null, controller.signal); if (!controller.signal.aborted) { setData(next); setConnection(""); } }
      catch (err) { if (!controller.signal.aborted) setConnection(err.message); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 1500);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [domain]);
  const submit = async (payload) => {
    setBusy(true); setError("");
    try { setData(await call(domain, payload)); return true; }
    catch (err) { setError(err.message); return false; }
    finally { setBusy(false); }
  };
  const impact = data?.impact;
  const systems = ["All systems", ...new Set(data?.devices.map((d) => d.system) || [])];
  return <section className="operations-panel">
    <div className="ops-heading"><div><span className="eyebrow">Equipment · resilience · community service</span><h2>Equipment and incident desk</h2><p>Commanded settings and simulated field feedback are separate. Equipment responses advance with the process clock.</p></div><span className="ops-count">{data?.devices.length || 0} auxiliary assets</span></div>
    {(error || connection) && <div className="training-error" role="alert">{error || connection}</div>}
    <div className="ops-incident-grid">{data?.incident_definitions.map((incident) => <article key={incident.id}><span className="ops-scenario-label">PREDEFINED FICTIONAL EXERCISE</span><h3>{incident.name}</h3><p>{incident.description}</p><button disabled={busy || !!data.incident} onClick={() => submit({ action: "incident", incident_id: incident.id, duration_minutes: 45 })}>Inject incident & run · 45 simulated min</button></article>)}</div>
    {data?.incident && <div className="ops-active"><div><strong>{data.incident.name}</strong><span>Active from minute {data.incident.started_minute} to {data.incident.ends_minute}. Ending the disturbance does not reset latched trips.</span></div><button disabled={busy} onClick={() => submit({ action: "end_incident" })}>End external disturbance</button></div>}
    {impact && <section className={`ops-impact ${impact.severity}`}><div><span>{impact.label}</span><strong>{impact.coverage_pct.toFixed(1)}%</strong><b>{impact.severity}</b></div>{impact.equivalent_accounts_affected !== null && <div><span>Equivalent accounts affected</span><strong>{impact.equivalent_accounts_affected.toLocaleString()}</strong><small>Fictional {impact.assumed_accounts.toLocaleString()}-account service area</small></div>}<div><span>Equivalent full-loss time</span><strong>{impact.equivalent_full_loss_minutes.toFixed(2)} <small>min</small></strong><small>Integral of the fractional service deficit</small></div><p>{impact.note}</p><div className="ops-districts">{impact.districts.map((d) => <div key={d.name}><span>{d.name}</span><meter min="0" max="100" value={d.coverage_pct} aria-label={`${d.name} demand served`} /><b>{d.coverage_pct.toFixed(1)}% served</b></div>)}</div></section>}
    <div className="ops-equipment-toolbar"><h3>Auxiliary equipment controls</h3><label>System<select value={filter} onChange={(e) => setFilter(e.target.value)}>{systems.map((system) => <option key={system}>{system}</option>)}</select></label></div>
    <div className="ops-equipment-grid">{data?.devices.filter((d) => filter === "All systems" || d.system === filter).map((device) => <EquipmentCard key={`${domain}-${device.tag}`} device={device} submit={submit} busy={busy} />)}</div>
    {data?.sludge_inventory_pct !== null && data?.sludge_inventory_pct !== undefined && <p className="ops-footnote">Clarifier sludge inventory: {data.sludge_inventory_pct.toFixed(1)}%. Sludge withdrawal changes this inventory during the exercise.</p>}
    <p className="ops-footnote">Illustrative auxiliary equipment. Independent protection and existing PLC permissives retain priority. Commands and incident events are included in the exercise evidence.</p>
  </section>;
}
