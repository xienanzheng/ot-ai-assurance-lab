import React from "react";
import { HOSTED, HOSTED_MODEL } from "./HostedSession";
import ResearchDashboard from "./ResearchDashboard";
import Walkthrough from "./Walkthrough";
import AgentResearchRoom from "./AgentResearchRoom";
import OperationsPanel from "./OperationsPanel";
import TrainingRoom from "./TrainingRoom";
import { GridRoom, NuclearRoom } from "./InfrastructureRooms";

const INITIAL_CONFIG = {
  scenario: "normal_day",
  seed: 42,
  duration_hours: 24,
  speed: 10,
  controller_mode: "baseline",
  model: HOSTED ? HOSTED_MODEL : "qwen3:8b",
  ai_decision_interval_minutes: 5,
  memory_enabled: true,
  memory_window: 4,
};

const TABS = [
  ["walkthrough", "Guided walkthrough"],
  ["overview", "Water overview"],
  ["hmi", "Water HMI"],
  ["nuclear", "Nuclear PWR"],
  ["grid", "Power grid"],
  ["experiments", "Experiments"],
  ["training", "Exercise console"],
  ["agents", HOSTED ? "AI decisions" : "Local AI agents"],
  ["research", "Evidence & risk"],
];

function Icon({ name, size = 18 }) {
  const paths = {
    droplet: <><path d="M12 2.5S5.5 9.4 5.5 14.4a6.5 6.5 0 0 0 13 0C18.5 9.4 12 2.5 12 2.5Z"/><path d="M9 15.5c.5 1.5 1.6 2.3 3.2 2.5"/></>,
    shield: <><path d="M12 3 4.5 6v5.2c0 4.7 3.2 8.2 7.5 9.8 4.3-1.6 7.5-5.1 7.5-9.8V6L12 3Z"/><path d="m8.8 12 2 2 4.3-4.5"/></>,
    bolt: <path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z"/>,
    flask: <><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3"/><path d="M7.5 15h9"/></>,
    pressure: <><circle cx="12" cy="12" r="8"/><path d="m12 12 4-3M7 17l10 0"/></>,
    play: <path d="m8 5 11 7-11 7V5Z"/>,
    pause: <><path d="M8 5v14M16 5v14"/></>,
    reset: <><path d="M4 7v5h5"/><path d="M5.7 17a8 8 0 1 0 .7-10.5L4 9"/></>,
    alert: <><path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v5M12 17.5h.01"/></>,
    brain: <><path d="M9.5 4.5A3.5 3.5 0 0 0 6 8v.5A3.5 3.5 0 0 0 5.5 15 3.5 3.5 0 0 0 9 19.5h1V4.8a3.4 3.4 0 0 0-.5-.3ZM14.5 4.5A3.5 3.5 0 0 1 18 8v.5a3.5 3.5 0 0 1 .5 6.5 3.5 3.5 0 0 1-3.5 4.5h-1V4.8c.2-.1.3-.2.5-.3Z"/><path d="M7 11h3M14 8h3M14 15h4"/></>,
    download: <><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/></>,
    chevron: <path d="m9 18 6-6-6-6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const value = (plant, name, fallback = 0) => plant?.sensors?.[name]?.value ?? fallback;
const fmt = (number, digits = 1) => Number(number ?? 0).toFixed(digits);
const elapsedClock = (minutes = 0) => {
  const day = Math.floor(minutes / 1440) + 1;
  const hour = Math.floor((minutes % 1440) / 60);
  const minute = Math.floor(minutes % 60);
  return `D${String(day).padStart(2, "0")} ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
};
const titleCase = (text = "") => text.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()).replace(/\bAi\b/g, "AI").replace(/\bOpc Ua\b/g, "OPC UA");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return response.json();
}

function Sparkline({ data = [], color = "#48d6c4", label }) {
  const width = 280;
  const height = 74;
  if (data.length < 2) return <div className="chart-empty">Trend starts after the run begins</div>;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((item, index) => `${(index / (data.length - 1)) * width},${height - 5 - ((item - min) / range) * (height - 12)}`).join(" ");
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} preserveAspectRatio="none">
    <line x1="0" y1={height - 5} x2={width} y2={height - 5} className="chart-grid" />
    <polyline points={points} fill="none" stroke={color} strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
    <circle cx={width} cy={points.split(" ").at(-1).split(",")[1]} r="3" fill={color} />
  </svg>;
}

function StatusPill({ state = "normal", children }) {
  return <span className={`status-pill ${state}`}><span className="status-dot" />{children || titleCase(state)}</span>;
}

function Metric({ icon, label, reading, unit, detail, trend, color }) {
  return <article className="metric">
    <div className="metric-top"><span className="metric-icon"><Icon name={icon} /></span><span className="metric-label">{label}</span></div>
    <div className="metric-reading">{reading}<small>{unit}</small></div>
    <Sparkline data={trend} color={color} label={`${label} recent trend`} />
    <p>{detail}</p>
  </article>;
}

function Header({ plant, activeTab, setActiveTab, connection }) {
  const connected = connection === "live";
  const operatingState = !connected ? "Reconnecting" : plant?.running ? "Running" : "Paused";
  const room = activeTab === "research" ? { name: "WaterLab", icon: "brain" } : activeTab === "walkthrough" ? { name:"OT · AI Lab", icon:"shield" } : activeTab === "agents" ? { name: "AI Lab", icon: "shield" } : activeTab === "training" ? { name: "OT Lab", icon: "shield" } : activeTab === "nuclear" ? { name: "NuclearLab", icon: "flask" } : activeTab === "grid" ? { name: "GridLab", icon: "bolt" } : { name: "WaterLab", icon: "droplet" };
  return <>
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><Icon name={room.icon} size={22} /></span><div><strong>{room.name}</strong><span>Control room</span></div></div>
      <nav aria-label="Lab workspaces">{TABS.map(([id, label]) => <button key={id} aria-current={activeTab === id ? "page" : undefined} className={activeTab === id ? "active" : ""} onClick={() => setActiveTab(id)}>{label}</button>)}</nav>
      {activeTab === "research" ? <div className="header-status"><StatusPill state="idle">Archived research · read only</StatusPill></div> : <div className="header-status"><StatusPill state={!connected ? "critical" : plant?.running ? "normal" : "warning"}>{operatingState}</StatusPill><span className="elapsed-time"><small>Elapsed · {plant?.simulation_speed || plant?.speed || 10}x</small><strong>{elapsedClock(plant?.elapsed_minutes)}</strong></span><span className="sim-time">{plant ? new Date(plant.simulation_time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) : "Waiting for plant"}</span></div>}
    </header>
    {activeTab !== "research" && <div className={`alarm-strip ${plant?.safety_state || "normal"}`}>
      <Icon name={plant?.safety_state === "normal" ? "shield" : "alert"} />
      <span>{plant?.safety_state === "normal" ? "All monitored values are inside the illustrative safety envelope" : `${(plant?.active_alarms || plant?.alarms || []).length} active alarm${(plant?.active_alarms || plant?.alarms || []).length === 1 ? "" : "s"}`}</span>
      <small>Values shown here are for simulation and research only</small>
    </div>}
  </>;
}

function DecisionPanel({ decision, ollama }) {
  const gate = decision?.gate;
  const proposal = decision?.proposal;
  return <section className="decision-panel">
    <div className="section-heading"><div><span className="section-kicker">Supervisory control</span><h2>Latest AI decision</h2></div><StatusPill state={!ollama?.available ? "warning" : gate?.status === "accepted" ? "normal" : gate?.status === "rejected" ? "critical" : "idle"}>{!ollama?.available ? "Model unavailable" : gate ? titleCase(gate.status) : "Waiting"}</StatusPill></div>
    {proposal ? <div className="decision-body">
      <div className="ai-summary"><span className="ai-icon"><Icon name="brain" size={24} /></span><div><strong>{proposal.expected_effect}</strong><p>{proposal.explanation}</p></div></div>
      <dl className="decision-facts"><div><dt>Confidence</dt><dd>{Math.round(proposal.confidence * 100)}%</dd></div><div><dt>Mode</dt><dd>{titleCase(decision.mode)}</dd></div><div><dt>Memory</dt><dd>{decision.memory?.episodes_used || 0} episodes</dd></div></dl>
      {gate?.violated_constraints?.length > 0 && <div className="gate-reasons">{gate.violated_constraints.map((reason) => <span key={reason}>{reason}</span>)}</div>}
    </div> : <div className="empty-state"><Icon name="brain" size={28} /><p>Start an advisory, shadow, or gated automatic run to generate a proposal.</p></div>}
  </section>;
}

function Overview({ data }) {
  const plant = data?.plant;
  const trends = plant?.recent_trends || {};
  const demand = [1, 2, 3].reduce((sum, index) => sum + value(plant, `zone_${index}_demand_m3h`), 0);
  const served = Math.min(100, 100 * value(plant, "distribution_flow_m3h") / Math.max(demand + value(plant, "leak_flow_m3h"), 1));
  return <main className="page overview-page">
    <div className="page-intro"><div><span className="eyebrow">Treatment and distribution</span><h1>Operating overview</h1><p>One view of quality, storage, pressure, demand, and supervisory control.</p></div><div className="run-context"><span>{titleCase(plant?.scenario || "normal_day")}</span><strong>{plant?.simulation_speed || 10}x</strong><small>simulation speed</small></div></div>
    <section className="metrics-grid">
      <Metric icon="flask" label="Water quality" reading={fmt(value(plant, "chlorine_residual_mg_l"), 2)} unit="mg/L Cl₂" detail={`pH ${fmt(value(plant, "finished_water_ph"), 2)} · CT ${fmt(value(plant, "chlorine_ct_mg_min_l"), 0)} mg-min/L · ${fmt(value(plant, "filtered_turbidity_ntu"), 2)} NTU`} trend={trends.chlorine_residual_mg_l} color="#48d6c4" />
      <Metric icon="droplet" label="Storage" reading={fmt(value(plant, "elevated_tank_level_pct"), 0)} unit="%" detail={`${fmt(value(plant, "clearwell_level_pct"), 0)}% clearwell level`} trend={trends.elevated_tank_level_pct} color="#62aaf7" />
      <Metric icon="pressure" label="Lowest pressure" reading={fmt(Math.min(...[1, 2, 3].map((i) => value(plant, `zone_${i}_pressure_m`))))} unit="m" detail={`${fmt(served, 1)}% current demand served`} trend={trends.zone_2_pressure_m} color="#f0bc5e" />
      <Metric icon="bolt" label="Power demand" reading={fmt(value(plant, "energy_kw"), 0)} unit="kW" detail={`${fmt(value(plant, "distribution_flow_m3h"), 0)} m³/h distribution flow`} trend={trends.energy_kw} color="#b38ff4" />
    </section>
    <div className="overview-lower">
      <section className="operations-chart">
        <div className="section-heading"><div><span className="section-kicker">Last 120 simulated minutes</span><h2>Operating envelope</h2></div><div className="legend"><span className="teal">Tank</span><span className="blue">Clearwell</span></div></div>
        <div className="large-chart"><Sparkline data={trends.elevated_tank_level_pct} color="#48d6c4" label="Elevated tank level trend" /><Sparkline data={trends.clearwell_level_pct} color="#62aaf7" label="Clearwell level trend" /></div>
        <div className="zone-row">{[1, 2, 3].map((index) => <div key={index}><span>Zone {index}</span><strong>{fmt(value(plant, `zone_${index}_pressure_m`))} m</strong><small>{fmt(value(plant, `zone_${index}_demand_m3h`), 0)} m³/h demand</small></div>)}</div>
      </section>
      <DecisionPanel decision={data?.latest_decision} ollama={data?.ollama} />
    </div>
  </main>;
}

function Tank({ label, level, type = "tank" }) {
  return <div className={`hmi-unit ${type}`}><span className="unit-label">{label}</span><div className="tank-shell"><div className="water-fill" style={{ height: `${Math.max(2, Math.min(100, level))}%` }} /><span>{fmt(level, 0)}%</span></div></div>;
}

function Pump({ label, state }) {
  return <div className={`hmi-unit pump-unit ${state?.running ? "running" : "stopped"}`}><span className="unit-label">{label}</span><div className="pump-symbol"><span /></div><strong>{fmt(state?.speed_pct, 0)}%</strong><small>{state?.running ? "RUN" : "STOP"}</small></div>;
}

function Pipe({ active = true, vertical = false }) {
  return <div className={`pipe ${active ? "active" : ""} ${vertical ? "vertical" : ""}`}><span /></div>;
}

function Valve({ label, state, compact = false }) {
  const status = state?.status || "unavailable";
  return <div className={`hmi-unit valve-unit ${status} ${compact ? "compact-valve" : ""}`}>
    <span className="unit-label">{label}</span>
    <div className="valve-symbol"><i /><i /></div>
    <strong>{fmt(state?.position_pct, 0)}%</strong>
    <small>{titleCase(status)}</small>
    {!compact && <span className="valve-dp">ΔP {fmt(state?.differential_pressure_kpa, 1)} kPa</span>}
  </div>;
}

function CheckpointPanel({ plant }) {
  return <div className="hmi-panel checkpoint-panel"><h2>Process checkpoints <span>{plant?.checkpoints?.length || 0}</span></h2>
    {(plant?.checkpoints || []).map((checkpoint) => <div className="checkpoint-row" key={checkpoint.name}>
      <span className={`checkpoint-light ${checkpoint.status}`} />
      <div><strong>{checkpoint.name}</strong><small>{checkpoint.location}</small><p>{checkpoint.purpose}</p></div>
    </div>)}
  </div>;
}

function ChemicalPanel({ plant }) {
  const flowProof = value(plant, "chemical_feed_flow_proof") > 0.5;
  const feeds = [
    { tag: "P-111", name: "Alum coagulant", command: value(plant, "coagulant_dose_actual_mg_l"), detail: `${fmt(value(plant, "alum_solution_flow_lph"), 2)} L/h · command ${fmt(plant?.actuators?.coagulant_dose_mg_l, 2)} mg/L · ${fmt(value(plant, "alum_feed_runtime_min"), 0)} min`, state: plant?.equipment?.alum_feed_pump?.running ? "running" : "stopped" },
    { tag: "P-161", name: "NaOH pH correction", command: value(plant, "naoh_dose_actual_mg_l"), detail: `${fmt(value(plant, "naoh_solution_flow_lph"), 2)} L/h · command ${fmt(plant?.actuators?.naoh_dose_mg_l, 2)} mg/L · ${fmt(value(plant, "naoh_feed_runtime_min"), 0)} min`, state: plant?.equipment?.naoh_feed_pump?.running ? "running" : "stopped" },
    { tag: "P-171", name: "Sodium hypochlorite", command: value(plant, "chlorine_dose_actual_mg_l"), detail: `${fmt(value(plant, "hypochlorite_solution_flow_lph"), 2)} L/h · command ${fmt(plant?.actuators?.chlorine_dose_mg_l, 2)} mg/L · ${fmt(value(plant, "chlorine_feed_runtime_min"), 0)} min`, state: plant?.equipment?.chlorine_feed_pump?.running ? "running" : "stopped" },
  ];
  return <div className="hmi-panel chemical-panel"><h2>Chemical feed train <span>3</span></h2>
    <div className={`chemical-proof ${flowProof ? "proved" : "blocked"}`}><i /><span>Treatment flow permissive</span><strong>{flowProof ? "PROVED" : "FEED INHIBITED"}</strong></div>
    {feeds.map((feed) => <div className={`chemical-feed-row ${feed.state}`} key={feed.tag}><i /><div><strong>{feed.name}</strong><small>{feed.tag} · {feed.detail}</small></div><b>{fmt(feed.command, 2)} <small>mg/L</small></b></div>)}
    <div className="contact-card"><span>Clearwell contact calculation</span><strong>{fmt(value(plant, "chlorine_contact_time_min"), 0)} min <small>T10 estimate</small></strong><strong>{fmt(value(plant, "chlorine_ct_mg_min_l"), 0)} <small>mg-min/L CT</small></strong><p>Uses active volume, current flow, and a 0.30 illustrative baffling factor. It is not a compliance result.</p></div>
  </div>;
}

function TwinValidationPanel({ plant }) {
  const health = plant?.twin_health;
  const fitState = health?.fit_status === "good" ? "normal" : health?.fit_status === "stale" || health?.fit_status === "poor" ? "critical" : "warning";
  return <div className="hmi-panel twin-panel"><div className="twin-panel-heading"><div><span className="section-kicker">Model and telemetry</span><h2>Twin validation</h2></div><StatusPill state={fitState}>{titleCase(health?.fit_status || "waiting")}</StatusPill></div>
    <div className="twin-facts"><div><span>Telemetry source</span><strong>{health?.telemetry_source || "Waiting"}</strong></div><div><span>Pressure RMSE</span><strong>{fmt(health?.pressure_rmse_m, 2)} m</strong></div><div><span>Flow residual</span><strong>{fmt(health?.flow_residual_pct, 2)}%</strong></div><div><span>Sync age</span><strong>{fmt(health?.telemetry_age_seconds, 0)} s</strong></div></div>
    <div className="residual-row">{Object.entries(health?.zone_pressure_residuals_m || {}).map(([zone, residual]) => <span key={zone}>{titleCase(zone)} <b>{Number(residual) >= 0 ? "+" : ""}{fmt(residual, 2)} m</b></span>)}</div>
    {!!health?.integrity_flags?.length && <div className="integrity-flags">{health.integrity_flags.map((flag) => <div key={flag}><Icon name="alert" size={14} /><span>{flag}</span></div>)}</div>}
    <p>Synthetic OPC UA readings are compared with the WNTR prediction. Replace this source with reviewed SCADA data for an operational twin.</p>
  </div>;
}

function ControlLogicPanel({ plc, onResetTrips }) {
  const state = plc?.control_state;
  const sequence = state?.backwash_sequence;
  const trips = state?.trips || [];
  const activeTrips = trips.filter((trip) => trip.latched);
  const permissives = Object.entries(state?.permissives || {});
  const blockedPermissives = permissives.filter(([, item]) => !item.ok);
  const loops = Object.entries(state?.control_loops || {});
  const status = activeTrips.length ? "critical" : blockedPermissives.length ? "warning" : "normal";
  return <div className="hmi-panel control-logic-panel">
    <div className="control-logic-heading"><div><span className="section-kicker">PLC execution layer</span><h2>Control logic</h2></div><StatusPill state={status}>{activeTrips.length ? `${activeTrips.length} trip${activeTrips.length === 1 ? "" : "s"}` : "Healthy"}</StatusPill></div>
    <div className="logic-summary">
      <div><span>Control source</span><strong>{titleCase(state?.control_source || "waiting")}</strong></div>
      <div><span>Backwash phase</span><strong>{titleCase(sequence?.phase || "idle")}</strong></div>
      <div><span>Blocked permissives</span><strong>{blockedPermissives.length}</strong></div>
      <div><span>Completed backwashes</span><strong>{sequence?.completed_cycles || 0}</strong></div>
    </div>
    {!!activeTrips.length && <div className="trip-list">{activeTrips.map((trip) => <div key={trip.code}><Icon name="alert" size={14} /><span><strong>{trip.code}</strong><small>{trip.reason}</small></span></div>)}</div>}
    {!!blockedPermissives.length && <div className="permissive-list">{blockedPermissives.slice(0, 4).map(([name]) => <span key={name}>{titleCase(name)}</span>)}</div>}
    {!!loops.length && <div className="loop-list">{loops.map(([name, loop]) => <div key={name}><span>{titleCase(name)}</span><b>SP {fmt(loop.setpoint, 2)}</b><b>PV {fmt(loop.process_value, 2)}</b><i className={loop.saturated ? "saturated" : ""}>{loop.saturated ? "LIMIT" : "PI"}</i></div>)}</div>}
    <div className="logic-footer"><span>Anti-windup, output slew limits, first-out trips, and restart inhibition are active.</span>{!!activeTrips.length && <button onClick={onResetTrips}>Reset healthy trips</button>}</div>
  </div>;
}

function FaultInjectionPanel({ definitions, active, onInject, onClear }) {
  const [pending, setPending] = React.useState("");
  const trigger = async (definition) => {
    setPending(definition.id);
    try { await onInject(definition.id, definition.default_duration_minutes); } finally { setPending(""); }
  };
  return <section className="fault-lab">
    <div className="fault-heading"><div><span className="section-kicker">Isolated simulation only</span><h2>Attack and hazard injection</h2><p>Press an exercise to override simulated field behavior. The plant starts automatically so you can watch the consequence and protection response.</p></div>{active?.length > 0 && <button className="clear-faults" onClick={onClear}>Clear all injections</button>}</div>
    <div className="fault-grid">{definitions.map((definition) => {
      const isActive = active?.includes(definition.id);
      return <button className={`fault-card ${isActive ? "active" : ""}`} key={definition.id} onClick={() => trigger(definition)} disabled={pending === definition.id}>
        <span>{isActive ? "ACTIVE" : definition.severity.toUpperCase()}</span><strong>{definition.name}</strong><small>{definition.description}</small><em>{isActive ? definition.consequence : `Run for ${definition.default_duration_minutes} simulated minutes`}</em>
      </button>;
    })}</div>
  </section>;
}

function ChemicalTrainGraphic({ plant, chemical, name, tag, color, injectionPoint, dose, flow }) {
  const bulk = value(plant, `${chemical}_bulk_tank_level_pct`);
  const day = value(plant, `${chemical}_day_tank_level_pct`);
  const transferOpen = value(plant, `${chemical}_transfer_valve_position_pct`) > 2;
  const injectionOpen = value(plant, `${chemical}_injection_valve_position_pct`) > 2;
  const transferRunning = plant?.equipment?.[`${chemical}_transfer_pump`]?.running;
  return <div className="chemical-train-graphic" style={{ "--chemical-color": color }}>
    <div className="chemical-vessel bulk"><span>{tag}-B</span><strong>{name} bulk</strong><div className="chemical-level"><i style={{ height: `${bulk}%` }} /></div><small>{fmt(bulk, 0)}% · bunded tank</small></div>
    <div className={`mini-valve ${transferOpen ? "open" : "closed"}`}><i /><span>XV</span><small>{transferOpen ? "OPEN" : "CLOSED"}</small></div>
    <div className={`mini-pump ${transferRunning ? "running" : "stopped"}`}><i /><span>Transfer</span></div>
    <div className="chemical-vessel day"><span>{tag}-D</span><strong>Day tank</strong><div className="chemical-level"><i style={{ height: `${day}%` }} /></div><small>{fmt(day, 0)}% · LT</small></div>
    <div className="calibration-column"><i /><i /><i /><span>Calibration</span></div>
    <div className={`metering-pump ${injectionOpen ? "running" : "stopped"}`}><i /><span>{tag}</span><strong>{fmt(flow, 2)} L/h</strong></div>
    <div className={`mini-valve check ${injectionOpen ? "open" : "closed"}`}><i /><span>NRV</span><small>{injectionOpen ? "OPEN" : "CLOSED"}</small></div>
    <div className="injection-point"><i /><strong>{injectionPoint}</strong><small>{fmt(dose, 2)} mg/L</small></div>
  </div>;
}

function Analyzer({ tag, label, reading, unit, status = "normal" }) {
  return <div className={`inline-analyzer ${status}`}><span>{tag}</span><strong>{label}</strong><small>{reading} {unit}</small></div>;
}

function WaterProcessExpanded({ plant }) {
  return <section className="water-process-expanded">
    <div className="chemical-gallery-title"><span>Chemical storage and dosing gallery</span><small>Bulk storage → transfer isolation → day tank → calibration column → metering pump → non-return valve → injection quill</small></div>
    <div className="chemical-gallery">
      <ChemicalTrainGraphic plant={plant} chemical="alum" name="Alum" tag="P-111" color="#d7e58a" injectionPoint="Rapid mix" dose={plant?.actuators?.coagulant_dose_mg_l} flow={value(plant, "alum_solution_flow_lph")} />
      <ChemicalTrainGraphic plant={plant} chemical="naoh" name="NaOH 25%" tag="P-161" color="#efb663" injectionPoint="Post-filter" dose={value(plant, "naoh_dose_actual_mg_l")} flow={value(plant, "naoh_solution_flow_lph")} />
      <ChemicalTrainGraphic plant={plant} chemical="hypochlorite" name="Sodium hypochlorite" tag="P-171" color="#54d8c4" injectionPoint="Clearwell inlet" dose={value(plant, "chlorine_dose_actual_mg_l")} flow={value(plant, "hypochlorite_solution_flow_lph")} />
    </div>
    <div className="treatment-lane">
      <div className="process-stage source"><span>RW-01</span><strong>Raw-water source</strong><small>{fmt(value(plant, "raw_turbidity_ntu"), 1)} NTU · pH {fmt(value(plant, "raw_ph"), 2)}</small></div>
      <div className="lane-pipe active" />
      <Valve label="XV-101 intake gate" state={plant?.valves?.intake_gate} />
      <div className="lane-pipe active" />
      <Pump label="P-101 intake" state={plant?.equipment?.intake_pump} />
      <div className="lane-pipe active" />
      <div className="process-box mixer"><span>MX-111</span><strong>Rapid mix</strong><i /><small>Alum injection</small></div>
      <div className="lane-pipe active" />
      <div className="process-box floc"><span>FL-121</span><strong>Flocculation</strong><div><i /><i /><i /></div><small>3-stage slow mix</small></div>
      <div className="lane-pipe active" />
      <div className="process-box clarifier"><span>CL-131</span><strong>Clarifier</strong><div className="clarifier-basin"><i /></div><small>{fmt(value(plant, "clarified_turbidity_ntu"), 2)} NTU</small></div>
      <div className="lane-pipe active" />
      <div className="process-box filter-bank"><span>F-141 A/B</span><strong>Dual-media filters</strong><div><i /><i /></div><small>ΔP {fmt(value(plant, "filter_dp_kpa"), 1)} kPa</small></div>
      <div className="lane-pipe active" />
      <Valve label="XV-151 outlet" state={plant?.valves?.filter_outlet} />
      <div className="lane-pipe active" />
      <div className="process-box contact-basin"><span>CW-181</span><strong>Clearwell with baffles</strong><div className="baffle-lines"><i /><i /><i /><i /></div><small>{fmt(value(plant, "clearwell_level_pct"), 0)}% · T10 {fmt(value(plant, "chlorine_contact_time_min"), 0)} min</small></div>
    </div>
    <div className="analyzer-lane">
      <Analyzer tag="AIT-112" label="Coagulation pH" reading={fmt(value(plant, "coagulation_ph"), 2)} unit="pH" />
      <Analyzer tag="AIT-142" label="Filter effluent" reading={fmt(value(plant, "filtered_turbidity_ntu"), 2)} unit="NTU" status={value(plant, "filtered_turbidity_ntu") > 1 ? "critical" : "normal"} />
      <Analyzer tag="AIT-162" label="Finished pH" reading={fmt(value(plant, "finished_water_ph"), 2)} unit="pH" />
      <Analyzer tag="AIT-172" label="Free chlorine" reading={fmt(value(plant, "chlorine_residual_mg_l"), 2)} unit="mg/L" />
      <Analyzer tag="CALC-181" label="Contact CT" reading={fmt(value(plant, "chlorine_ct_mg_min_l"), 0)} unit="mg-min/L" />
    </div>
    <div className="distribution-lane">
      <Pump label="P-201 high lift" state={plant?.equipment?.high_lift_pump} />
      <div className="lane-pipe active" />
      <div className="prv-assembly"><span>PCV-211</span><i /><strong>{fmt(value(plant, "distribution_header_pressure_m"), 1)} m</strong><small>Pressure control</small></div>
      <div className="distribution-header"><span>Distribution header</span><i /></div>
      <div className="tank-branch"><div className="vertical-pipe active" /><Tank label="TK-221 elevated" level={value(plant, "elevated_tank_level_pct")} /></div>
      <div className="zone-branches">{[1, 2, 3].map((index) => <div className="zone-branch" key={index}><div className="vertical-pipe active" /><Valve label={`XV-30${index} isolation`} state={plant?.valves?.[`zone_${index}_isolation`]} compact /><div><span>ZONE {index}</span><strong>{fmt(value(plant, `zone_${index}_pressure_m`), 1)} m</strong><small>{fmt(value(plant, `zone_${index}_served_m3h`), 0)} of {fmt(value(plant, `zone_${index}_demand_m3h`), 0)} m³/h</small></div></div>)}</div>
    </div>
  </section>;
}

function Hmi({ plant, plc, onManual, onResetTrips, injections, onInject, onClearInjections }) {
  const [manualOpen, setManualOpen] = React.useState(false);
  const [manual, setManual] = React.useState({ pressure_target_m: 44, chlorine_target_mg_l: 1.15, finished_water_ph_target: 7.35, intake_gate_target_pct: 95, filter_outlet_valve_target_pct: 95, zone_1_isolation_target_pct: 100, zone_2_isolation_target_pct: 100, zone_3_isolation_target_pct: 100, backwash_request: false });
  const submit = async () => {
    const changes = {
      pressure_target_m: manual.pressure_target_m,
      chlorine_target_mg_l: manual.chlorine_target_mg_l,
      finished_water_ph_target: manual.finished_water_ph_target,
      intake_gate_target_pct: manual.intake_gate_target_pct,
      filter_outlet_valve_target_pct: manual.filter_outlet_valve_target_pct,
      zone_1_isolation_target_pct: manual.zone_1_isolation_target_pct,
      zone_2_isolation_target_pct: manual.zone_2_isolation_target_pct,
      zone_3_isolation_target_pct: manual.zone_3_isolation_target_pct,
      backwash_request: manual.backwash_request,
    };
    await onManual({ changes, confirmation: "CONFIRM" });
    setManual({ ...manual, backwash_request: false });
    setManualOpen(false);
  };
  return <main className="page hmi-page">
    <div className="page-intro compact"><div><span className="eyebrow">Operator station 01</span><h1>Water treatment and distribution</h1></div><div className="hmi-run-clock"><span>{plant?.running ? "RUN" : "HOLD"}</span><strong>{elapsedClock(plant?.elapsed_minutes)}</strong><small>{plant?.simulation_speed || 10}x simulated time</small></div><button className="secondary-button" onClick={() => setManualOpen(!manualOpen)}>Direct controls</button></div>
    <FaultInjectionPanel definitions={injections} active={plant?.active_injections || []} onInject={onInject} onClear={onClearInjections} />
    <div className="hmi-layout">
      <WaterProcessExpanded plant={plant} />
      <aside className="hmi-sidebar">
        <ControlLogicPanel plc={plc} onResetTrips={onResetTrips} />
        <div className="hmi-panel"><h2>Process readings</h2>{[
          ["Influent flow", value(plant, "raw_flow_m3h"), "m³/h"],
          ["Filtered turbidity", value(plant, "filtered_turbidity_ntu"), "NTU"],
          ["Chlorine residual", value(plant, "chlorine_residual_mg_l"), "mg/L"],
          ["Chlorine model estimate", value(plant, "chlorine_model_estimate_mg_l"), "mg/L"],
          ["Clearwell reported level", value(plant, "clearwell_level_pct"), "%"],
          ["Clearwell model level", value(plant, "clearwell_level_model_pct"), "%"],
          ["Clearwell overflow", value(plant, "clearwell_overflow_m3h"), "m³/h"],
          ["Raw pH", value(plant, "raw_ph"), "pH"],
          ["Coagulation pH", value(plant, "coagulation_ph"), "pH"],
          ["Finished-water pH", value(plant, "finished_water_ph"), "pH"],
          ["Finished alkalinity", value(plant, "finished_alkalinity_mg_l_caco3"), "mg/L CaCO3"],
          ["Distribution flow", value(plant, "distribution_flow_m3h"), "m³/h"],
          ["Pump discharge", value(plant, "pump_discharge_pressure_m"), "m head"],
          ["Deadhead pressure", value(plant, "pump_deadhead_pressure_kpa"), "kPa"],
          ["PRV header", value(plant, "distribution_header_pressure_m"), "m head"],
          ["Leak estimate", value(plant, "leak_flow_m3h"), "m³/h"],
        ].map(([label, reading, unit]) => <div className="reading-row" key={label}><span>{label}</span><strong>{fmt(reading, unit === "mg/L" ? 2 : 1)} <small>{unit}</small></strong></div>)}</div>
        <TwinValidationPanel plant={plant} />
        <ChemicalPanel plant={plant} />
        <CheckpointPanel plant={plant} />
        <div className="hmi-panel alarms"><h2>Active alarms <span>{plant?.active_alarms?.length || 0}</span></h2>{plant?.active_alarms?.length ? plant.active_alarms.map((alarm) => <div className={`alarm-item ${alarm.severity}`} key={`${alarm.code}-${alarm.started_at}`}><Icon name="alert" size={16} /><div><strong>{alarm.code}</strong><p>{alarm.message}</p></div></div>) : <div className="no-alarms"><Icon name="shield" /><span>No active process alarms</span></div>}</div>
      </aside>
    </div>
    <OperationsPanel domain="water" />
    {manualOpen && <div className="modal-backdrop" onMouseDown={() => setManualOpen(false)}><div className="modal direct-control-modal" onMouseDown={(event) => event.stopPropagation()}><span className="section-kicker">Confirmed operator action</span><h2>Direct supervisory controls</h2><div className="direct-control-columns"><div><h3>Process targets</h3><label>Pressure target <span>{manual.pressure_target_m} m</span><input type="range" min="35" max="55" step="1" value={manual.pressure_target_m} onChange={(e) => setManual({ ...manual, pressure_target_m: Number(e.target.value) })} /></label><label>Chlorine residual target <span>{manual.chlorine_target_mg_l} mg/L</span><input type="range" min="0.5" max="2" step="0.05" value={manual.chlorine_target_mg_l} onChange={(e) => setManual({ ...manual, chlorine_target_mg_l: Number(e.target.value) })} /></label><label>Finished-water pH target <span>{manual.finished_water_ph_target}</span><input type="range" min="7" max="8.8" step="0.05" value={manual.finished_water_ph_target} onChange={(e) => setManual({ ...manual, finished_water_ph_target: Number(e.target.value) })} /></label><label className="sequence-request"><input type="checkbox" checked={manual.backwash_request} onChange={(e) => setManual({ ...manual, backwash_request: e.target.checked })} /><span><strong>Request filter backwash</strong><small>The sequencer checks storage, differential pressure, valve feedback, and sensor quality before starting.</small></span></label></div><div><h3>Direct valve targets</h3>{[["intake_gate_target_pct", "XV-101 intake gate", 30], ["filter_outlet_valve_target_pct", "XV-151 filter outlet", 30], ["zone_1_isolation_target_pct", "XV-301 Zone 1", 50], ["zone_2_isolation_target_pct", "XV-302 Zone 2", 50], ["zone_3_isolation_target_pct", "XV-303 Zone 3", 50]].map(([name, title, min]) => <label key={name}>{title} <span>{manual[name]}%</span><input type="range" min={min} max="100" step="5" value={manual[name]} onChange={(e) => setManual({ ...manual, [name]: Number(e.target.value) })} /></label>)}</div></div><p>Valve targets remain rate-limited and safety-gated. The operator selects a pH target, while the PLC calculates the bounded NaOH dose.</p><div className="modal-actions"><button className="text-button" onClick={() => setManualOpen(false)}>Cancel</button><button className="primary-button" onClick={submit}>Confirm and apply</button></div></div></div>}
  </main>;
}

function Experiments({ scenarios, runs, config, setConfig, activeRunId, onCreateStart, onAction, error }) {
  const activeRun = runs.find((run) => run.id === activeRunId);
  return <main className="page experiments-page">
    <div className="page-intro"><div><span className="eyebrow">Repeatable evaluation</span><h1>Experiment runner</h1><p>Compare the baseline and AI modes with identical scenarios and random seeds.</p></div></div>
    <div className="experiment-layout">
      <form className="run-builder" onSubmit={(event) => { event.preventDefault(); onCreateStart(); }}>
        <div className="section-heading"><div><span className="section-kicker">Run configuration</span><h2>New experiment</h2></div></div>
        <label>Scenario<select value={config.scenario} onChange={(e) => setConfig({ ...config, scenario: e.target.value })}>{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label>
        <div className="form-row"><label>Random seed<input type="number" value={config.seed} min="0" onChange={(e) => setConfig({ ...config, seed: Number(e.target.value) })} /></label><label>Duration<input type="number" value={config.duration_hours} min="1" max="168" onChange={(e) => setConfig({ ...config, duration_hours: Number(e.target.value) })} /><span className="input-unit">hours</span></label></div>
        <label>Controller mode<div className="segmented-control">{["baseline", "advisory", "shadow", "gated_auto"].map((mode) => <button type="button" className={config.controller_mode === mode ? "active" : ""} key={mode} onClick={() => setConfig({ ...config, controller_mode: mode })}>{titleCase(mode)}</button>)}</div></label>
        <div className="form-row"><label>Simulation speed<select value={config.speed} onChange={(e) => setConfig({ ...config, speed: Number(e.target.value) })}><option value="1">1x</option><option value="10">10x</option><option value="60">60x</option></select></label><label>AI interval<select value={config.ai_decision_interval_minutes} onChange={(e) => setConfig({ ...config, ai_decision_interval_minutes: Number(e.target.value) })}><option value="5">5 minutes</option><option value="10">10 minutes</option><option value="15">15 minutes</option></select></label></div>
        <label>{HOSTED ? "Hosted model" : "Ollama model"}<input readOnly={HOSTED} value={config.model} onChange={(e) => setConfig({ ...config, model: e.target.value })} /></label>
        <div className="memory-config"><label className="check-option"><input type="checkbox" checked={config.memory_enabled} onChange={(e) => setConfig({ ...config, memory_enabled: e.target.checked })} /><span>Use audited decision memory</span></label><label>Memory episodes<select disabled={!config.memory_enabled} value={config.memory_window} onChange={(e) => setConfig({ ...config, memory_window: Number(e.target.value) })}><option value="2">2</option><option value="4">4</option><option value="6">6</option><option value="8">8</option></select></label></div>
        {error && <div className="form-error">{error}</div>}
        <button className="primary-button run-button" type="submit"><Icon name="play" />Create and start run</button>
        {activeRun && <div className="active-run-controls"><button type="button" onClick={() => onAction("pause")}><Icon name="pause" />Pause</button><button type="button" onClick={() => onAction("step", { minutes: 1 })}>+1 minute</button><button type="button" onClick={() => onAction("reset")}><Icon name="reset" />Reset</button></div>}
      </form>
      <section className="run-history">
        <div className="section-heading"><div><span className="section-kicker">Audit history</span><h2>Recent runs</h2></div><span className="run-count">{runs.length} runs</span></div>
        <div className="run-table"><div className="run-table-head"><span>Scenario</span><span>Mode</span><span>Seed</span><span>Status</span><span>Export</span></div>{runs.length ? runs.map((run) => <div className={`run-table-row ${run.id === activeRunId ? "selected" : ""}`} key={run.id}><span><strong>{titleCase(run.config.scenario)}</strong><small>{run.id.slice(0, 8)}</small></span><span>{titleCase(run.config.controller_mode)}</span><span>{run.config.seed}</span><span><StatusPill state={run.status === "running" ? "normal" : run.status === "completed" ? "idle" : "warning"}>{titleCase(run.status)}</StatusPill></span><span className="export-actions"><a href={`/api/v1/runs/${run.id}/export?format=csv`} title="Export CSV"><Icon name="download" size={16} />CSV</a><a href={`/api/v1/runs/${run.id}/export?format=json`} title="Export JSON">JSON</a></span></div>) : <div className="empty-table">No experiments yet. Configure the first run on the left.</div>}</div>
      </section>
    </div>
  </main>;
}

export default function App() {
  const [activeTab, setActiveTab] = React.useState("walkthrough");
  const [walkDomain, setWalkDomain] = React.useState("water");
  const [chapter, setChapter] = React.useState(0);
  const [walkEvidence, setWalkEvidence] = React.useState({});
  const [trainingDomain, setTrainingDomain] = React.useState("water");
  const [agentDomain, setAgentDomain] = React.useState("water");
  const [agentRecordId, setAgentRecordId] = React.useState(null);
  const [data, setData] = React.useState(null);
  const [connection, setConnection] = React.useState("connecting");
  const [scenarios, setScenarios] = React.useState([]);
  const [injections, setInjections] = React.useState([]);
  const [infrastructure, setInfrastructure] = React.useState({ nuclear: null, grid: null });
  const [infraConnection, setInfraConnection] = React.useState("connecting");
  const [infrastructureScenarios, setInfrastructureScenarios] = React.useState({ nuclear: [], grid: [] });
  const [runs, setRuns] = React.useState([]);
  const [config, setConfig] = React.useState(INITIAL_CONFIG);
  const [error, setError] = React.useState("");

  const refreshRuns = React.useCallback(() => api("/api/v1/runs").then(setRuns).catch(() => {}), []);
  React.useEffect(() => {
    api("/api/v1/state").then(setData).catch(() => {});
    api("/api/v1/scenarios").then(setScenarios).catch(() => {});
    api("/api/v1/injections").then((result) => setInjections(result.definitions || [])).catch(() => {});
    refreshRuns();
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    let stopped = false;
    let socket;
    const connect = () => {
      socket = new WebSocket(`${protocol}://${window.location.host}/api/v1/live`);
      socket.onopen = () => setConnection("live");
      socket.onmessage = (event) => {
        const next = JSON.parse(event.data);
        if (!next.error) setData((current) => ({ ...current, ...next }));
      };
      socket.onclose = () => { setConnection("reconnecting"); if (!stopped) window.setTimeout(connect, 1500); };
      socket.onerror = () => socket.close();
    };
    connect();
    const timer = window.setInterval(refreshRuns, 5000);
    return () => { stopped = true; window.clearInterval(timer); socket?.close(); };
  }, [refreshRuns]);

  const refreshInfrastructure = React.useCallback(() => api("/api/v1/infrastructure/state").then((next) => { setInfrastructure(next); setInfraConnection("live"); }).catch(() => setInfraConnection("reconnecting")), []);
  React.useEffect(() => {
    refreshInfrastructure();
    api("/api/v1/infrastructure/scenarios").then(setInfrastructureScenarios).catch(() => {});
    const timer = window.setInterval(refreshInfrastructure, 1000);
    return () => window.clearInterval(timer);
  }, [refreshInfrastructure]);

  const createStart = async () => {
    setError("");
    try {
      const created = await api("/api/v1/runs", { method: "POST", body: JSON.stringify(config) });
      await api(`/api/v1/runs/${created.id}/start`, { method: "POST" });
      await refreshRuns();
    } catch (problem) {
      setError(problem.message);
    }
  };
  const runAction = async (action, body) => {
    if (!data?.active_run_id) return;
    await api(`/api/v1/runs/${data.active_run_id}/${action}`, { method: "POST", body: body ? JSON.stringify(body) : undefined });
    refreshRuns();
  };
  const manual = async (body) => api("/api/v1/control/manual", { method: "POST", body: JSON.stringify(body) });
  const resetTrips = async () => api("/api/v1/control/interlocks/reset", { method: "POST" });
  const emergencyStop = async () => {
    await api("/api/v1/emergency-stop", { method: "POST" });
    setConfig({ ...config, controller_mode: "baseline" });
  };
  const injectFault = async (injectionId, durationMinutes) => {
    setError("");
    try {
      await api(`/api/v1/injections/${injectionId}`, { method: "POST", body: JSON.stringify({ duration_minutes: durationMinutes }) });
    } catch (problem) {
      setError(problem.message);
    }
  };
  const clearInjections = async () => {
    setError("");
    try { await api("/api/v1/injections", { method: "DELETE" }); } catch (problem) { setError(problem.message); }
  };
  const infrastructureCommand = async (domain, action, options = {}) => {
    const result = await api(`/api/v1/infrastructure/${domain}/command`, { method: "POST", body: JSON.stringify({ action, minutes: 1, ...options }) });
    setInfrastructure((current) => ({ ...current, [domain]: result }));
  };
  const infrastructureManual = async (domain, changes) => {
    const result = await api(`/api/v1/infrastructure/${domain}/manual`, { method: "POST", body: JSON.stringify({ changes, confirmation: "CONFIRM" }) });
    setInfrastructure((current) => ({ ...current, [domain]: result.plant }));
    setError(result.gate?.status === "rejected" ? `Command rejected: ${result.gate.reasons.join("; ")}` : "");
  };
  const infrastructureAi = async (domain) => {
    const result = await api(`/api/v1/infrastructure/${domain}/ai`, { method: "POST" });
    setInfrastructure((current) => ({ ...current, [domain]: result.plant }));
  };
  const infrastructureTuning = async (settings) => {
    const result = await api("/api/v1/infrastructure/nuclear/tuning", { method: "PUT", body: JSON.stringify(settings) });
    setInfrastructure((current) => ({ ...current, nuclear: result }));
  };

  const trainingWaterAction = async (action, options) => {
    if (action === "configure" || !data?.active_run_id) {
      const next = { ...config, ...options };
      const created = await api("/api/v1/runs", { method: "POST", body: JSON.stringify(next) });
      await api(`/api/v1/runs/${created.id}/reset`, { method: "POST" });
      setConfig(next);
      if (action === "start" || action === "step") await api(`/api/v1/runs/${created.id}/${action}`, { method: "POST", body: action === "step" ? JSON.stringify(options) : undefined });
    } else {
      await api(`/api/v1/runs/${data.active_run_id}/${action}`, { method: "POST", body: action === "step" ? JSON.stringify(options) : undefined });
    }
    setData(await api("/api/v1/state"));
    await refreshRuns();
  };

  const uiAction = (fn) => (...args) => Promise.resolve().then(() => fn(...args)).catch((problem) => setError(problem.message));

  const openWorkspace = (tab, domain, recordId = null) => { if(tab === "agents") { setAgentDomain(domain); setAgentRecordId(recordId); } if(tab === "training") setTrainingDomain(domain); setActiveTab(tab); window.scrollTo(0,0); };
  const displayedDomain = activeTab === "walkthrough" ? walkDomain : activeTab === "agents" ? agentDomain : activeTab === "training" ? trainingDomain : activeTab;
  const activePlant = displayedDomain === "nuclear" ? infrastructure.nuclear : displayedDomain === "grid" ? infrastructure.grid : data?.plant;
  const isWaterRoom = !["nuclear", "grid"].includes(displayedDomain);

  return <div className="app-shell">
    <Header plant={activePlant} activeTab={activeTab} setActiveTab={setActiveTab} connection={["nuclear", "grid"].includes(displayedDomain) ? infraConnection : connection} />
    {error && activeTab !== "research" && <div className="training-error" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
    {activeTab === "walkthrough" && <Walkthrough domain={walkDomain} setDomain={setWalkDomain} chapter={chapter} setChapter={setChapter} evidence={walkEvidence} setEvidence={setWalkEvidence} water={data?.plant} infrastructure={infrastructure} onOpen={openWorkspace} onWaterAction={trainingWaterAction} onInfrastructureCommand={infrastructureCommand} />}
    {activeTab === "research" && <ResearchDashboard />}
    {activeTab === "agents" && <AgentResearchRoom domain={agentDomain} setDomain={next=>{setAgentDomain(next);setAgentRecordId(null);}} initialRecordId={agentRecordId} plant={activePlant} />}
    {activeTab === "training" && <TrainingRoom domain={trainingDomain} onDomainChange={setTrainingDomain} water={data?.plant} infrastructure={infrastructure} scenarios={scenarios} infrastructureScenarios={infrastructureScenarios} onOpenRoom={setActiveTab} onWaterAction={trainingWaterAction} onInfrastructureCommand={infrastructureCommand} />}
    {activeTab === "overview" && <Overview data={data} />}
    {activeTab === "hmi" && <Hmi plant={data?.plant} plc={data?.plc} onManual={manual} onResetTrips={resetTrips} injections={injections} onInject={injectFault} onClearInjections={clearInjections} />}
    {activeTab === "nuclear" && <NuclearRoom state={infrastructure.nuclear} scenarios={infrastructureScenarios.nuclear} onCommand={uiAction((action, options) => infrastructureCommand("nuclear", action, options))} onManual={uiAction(infrastructureManual)} onAi={uiAction(infrastructureAi)} onTune={uiAction(infrastructureTuning)} />}
    {activeTab === "grid" && <GridRoom state={infrastructure.grid} scenarios={infrastructureScenarios.grid} onCommand={uiAction((action, options) => infrastructureCommand("grid", action, options))} onManual={uiAction(infrastructureManual)} onAi={uiAction(infrastructureAi)} />}
    {activeTab === "experiments" && <Experiments scenarios={scenarios} runs={runs} config={config} setConfig={setConfig} activeRunId={data?.active_run_id} onCreateStart={createStart} onAction={runAction} error={error} />}
    {isWaterRoom && activeTab !== "research" && <button className="emergency-button" onClick={uiAction(emergencyStop)}><span>STOP</span><small>Emergency return to baseline</small></button>}
  </div>;
}
