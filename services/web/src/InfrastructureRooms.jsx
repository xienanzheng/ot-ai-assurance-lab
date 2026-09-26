import React from "react";
import OperationsPanel from "./OperationsPanel";
import { HOSTED } from "./HostedSession.jsx";

const fmt = (value, digits = 1) => Number(value ?? 0).toFixed(digits);
const reading = (state, name, fallback = 0) => state?.sensors?.[name]?.value ?? fallback;
const label = (text = "") => text.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()).replace("Ai", "AI");
const clock = (minutes = 0) => {
  const day = Math.floor(minutes / 1440) + 1;
  const hour = Math.floor((minutes % 1440) / 60);
  const minute = minutes % 60;
  return `D${String(day).padStart(2, "0")} ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
};

function StatePill({ state = "normal", children }) {
  return <span className={`infra-pill ${state}`}><i />{children || label(state)}</span>;
}

function RoomToolbar({ domain, state, scenarios, onCommand, onAi }) {
  const configure = (changes) => onCommand("configure", { scenario: state?.scenario, speed: state?.speed, controller_mode: state?.controller_mode, ...changes });
  return <div className="room-toolbar">
    <div className="room-clock"><span>{state?.running ? "RUN" : "HOLD"}</span><strong>{clock(state?.elapsed_minutes)}</strong><small>{state?.speed || 10}x</small></div>
    <label>Exercise<select value={state?.scenario || ""} onChange={(event) => configure({ scenario: event.target.value })}>{scenarios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Speed<select value={state?.speed || 10} onChange={(event) => configure({ speed: Number(event.target.value) })}><option value="1">1x</option><option value="10">10x</option><option value="60">60x</option></select></label>
    <div className="room-actions"><button onClick={() => onCommand(state?.running ? "pause" : "start")}>{state?.running ? "Pause" : "Start"}</button><button onClick={() => onCommand("step", { minutes: 1 })}>+1 min</button><button onClick={() => onCommand("reset")}>Reset</button></div>
    <div className="room-mode">{["baseline", "advisory", "shadow", "gated_auto"].map((mode) => <button key={mode} className={state?.controller_mode === mode ? "active" : ""} onClick={() => configure({ controller_mode: mode })}>{label(mode)}</button>)}</div>
    <button className="ai-cycle-button" onClick={() => onAi(domain)}>Run AI supervisor</button>
  </div>;
}

function AlarmPanel({ alarms = [] }) {
  return <section className="infra-card infra-alarms"><div className="infra-card-title"><span>Active alarms</span><b>{alarms.length}</b></div>{alarms.length ? alarms.map((alarm) => <div className={`infra-alarm ${alarm.severity}`} key={`${alarm.code}-${alarm.message}`}><strong>{alarm.code}</strong><p>{alarm.message}</p></div>) : <div className="infra-clear">No active process alarms</div>}</section>;
}

function AiPanel({ state, boundary }) {
  const decision = state?.ai_decision;
  return <section className="infra-card ai-supervisor-card">
    <div className="infra-card-title"><span>AI supervisory layer</span><StatePill state={decision?.gate?.status === "accepted" ? "normal" : decision?.gate?.status === "rejected" ? "critical" : "warning"}>{decision ? label(decision.gate.status) : "Waiting"}</StatePill></div>
    <div className="ai-boundary"><strong>Authority boundary</strong><p>{boundary}</p></div>
    {decision ? <><div className="decision-source">{decision.source}</div><h3>{decision.objective}</h3><p>{decision.explanation}</p><div className="proposal-grid">{Object.entries(decision.changes || {}).map(([name, value]) => <div key={name}><span>{label(name)}</span><strong>{fmt(value, 1)}</strong></div>)}</div>{decision.gate.reasons?.map((reason) => <div className="gate-block" key={reason}>{reason}</div>)}</> : <div className="infra-empty">Run the AI supervisor to create a bounded recommendation.</div>}
  </section>;
}

function IOChannels({ inputs = [], outputs = [] }) {
  return <section className="io-matrix">
    <div className="infra-card"><div className="infra-card-title"><span>Control inputs</span><b>{inputs.length}</b></div>{inputs.map((item) => <div className="io-row" key={item.name}><div><strong>{item.name}</strong><small>{item.type}</small></div><span>{item.authority}</span></div>)}</div>
    <div className="infra-card"><div className="infra-card-title"><span>Measured outputs</span><b>{outputs.length}</b></div>{outputs.map((item) => <div className="io-row" key={item.name}><div><strong>{item.name}</strong><small>{item.type}</small></div><span>{item.authority}</span></div>)}</div>
  </section>;
}

function NuclearDiagram({ state }) {
  const trip = state?.controls?.reactor_trip;
  const loops = state?.equipment?.primary_loops || {};
  return <section className={`nuclear-diagram ${trip ? "tripped" : ""}`}>
    <div className="containment-boundary"><span>Containment</span>
      <div className="reactor-vessel"><b>RV-101</b><strong>Reactor vessel</strong><div className="core-bars">{[1,2,3,4,5].map((item) => <i key={item} style={{ height: `${Math.max(8, reading(state, "reactor_power_pct"))}%` }} />)}</div><em>{fmt(reading(state, "reactor_power_pct"), 1)}% power</em></div>
      <div className="primary-pipe hot"><span>Hot leg</span><i /></div>
      <div className="steam-generator"><b>SG-101</b><strong>Steam generator</strong><div className="sg-level" style={{ height: `${reading(state, "steam_generator_level_pct")}%` }} /><em>{fmt(reading(state, "steam_generator_level_pct"), 1)}% level</em></div>
      <div className="primary-pipe cold"><span>Cold leg</span><i /></div>
      <div className="rcp-symbol"><i /><strong>RCP bank</strong><small>{state?.equipment?.reactor_coolant_pumps?.running || 0}/3 run</small></div>
      <div className="pressurizer"><b>PZR-101</b><strong>Pressurizer</strong><em>{fmt(reading(state, "primary_pressure_mpa"), 2)} MPa</em><small>H {fmt(state?.controls?.pressurizer_heater_pct, 0)}% · S {fmt(state?.controls?.pressurizer_spray_valve_pct, 0)}%</small></div>
      <div className="trip-block"><span>Independent protection</span><strong>{trip ? "REACTOR TRIP" : "ARMED"}</strong><small>AI has no command path</small></div>
      <div className="loop-bank">{Object.entries(loops).map(([name, loop]) => <div className={loop.rcp_running ? "" : "stopped"} key={name}><b>LOOP {name}</b><strong>{fmt(loop.flow_pct, 0)}%</strong><span>SG {fmt(loop.steam_generator_level_pct, 1)}%</span><small>{fmt(loop.hot_leg_c, 1)} / {fmt(loop.cold_leg_c, 1)} C</small></div>)}</div>
    </div>
    <div className="steam-path"><div className="flow-label">{fmt(reading(state, "steam_flow_kg_s"), 0)} kg/s steam</div><div className="direct-valve"><i /><strong>MS-V101</strong><small>{fmt(state?.controls?.main_steam_valve_pct, 0)}%</small></div><div className="turbine-symbol"><i /><strong>Main turbine</strong><small>{fmt(reading(state, "turbine_speed_rpm"), 0)} rpm</small></div><div className="generator-symbol"><span>G</span><strong>Generator</strong><small>{fmt(reading(state, "electric_output_mwe"), 0)} MWe</small></div><div className="grid-export"><i /><i /><i /><strong>Switchyard</strong></div></div>
    <div className="heat-dispatch-branch"><span>Steam extraction</span><i /><div><b>HX-201</b><strong>Industrial heat</strong><em>{fmt(reading(state, "thermal_dispatch_mwth"), 0)} MWth</em><small>{fmt(reading(state, "heat_transfer_supply_c"), 0)} / {fmt(reading(state, "heat_transfer_return_c"), 0)} C</small></div></div>
    <div className="secondary-return"><div className="condenser-unit"><strong>Main condenser</strong><span>{fmt(reading(state, "condenser_pressure_kpa_abs"), 1)} kPa abs</span><small>Hotwell {fmt(reading(state, "condenser_hotwell_level_pct"), 0)}%</small></div><div className="feed-pump"><i /><strong>Condensate pump</strong></div><div className="demin-unit"><strong>Deaerator</strong><small>{fmt(reading(state, "deaerator_level_pct"), 0)}% level</small></div><div className="feed-pump"><i /><strong>Feed pump</strong></div><div className="flow-label">{fmt(reading(state, "feedwater_flow_kg_s"), 0)} kg/s<br />{fmt(reading(state, "feedwater_temperature_c"), 0)} C</div></div>
  </section>;
}

function NuclearControls({ state, onManual }) {
  const [load, setLoad] = React.useState(1000);
  const [cooling, setCooling] = React.useState(80);
  const [dispatch, setDispatch] = React.useState(0);
  React.useEffect(() => { setLoad(Number(state?.controls?.turbine_load_target_mwe ?? 1000)); setCooling(Number(state?.controls?.condenser_cooling_pct ?? 80)); setDispatch(Number(state?.controls?.thermal_dispatch_target_mwth ?? 0)); }, [state?.controls?.turbine_load_target_mwe, state?.controls?.condenser_cooling_pct, state?.controls?.thermal_dispatch_target_mwth]);
  return <section className="infra-card control-console"><div className="infra-card-title"><span>Permitted supervisory controls</span><b>3</b></div><label>Turbine load target <strong>{load} MWe</strong><input type="range" min="300" max="1050" step="10" value={load} onChange={(event) => setLoad(Number(event.target.value))} /></label><label>Condenser cooling <strong>{cooling}%</strong><input type="range" min="50" max="100" step="1" value={cooling} onChange={(event) => setCooling(Number(event.target.value))} /></label><label>Industrial heat target <strong>{dispatch} MWth</strong><input type="range" min="0" max="300" step="10" value={dispatch} onChange={(event) => setDispatch(Number(event.target.value))} /></label><button onClick={() => onManual("nuclear", { turbine_load_target_mwe: load, condenser_cooling_pct: cooling, thermal_dispatch_target_mwth: dispatch })}>Confirm bounded changes</button><p>Control rods, protection trips, steam isolation and emergency feedwater stay outside this interface.</p></section>;
}

function MiniTrend({ values = [], color = "#5dd6c0" }) {
  const series = values.length ? values.slice(-60) : [0];
  const low = Math.min(...series);
  const high = Math.max(...series);
  const span = Math.max(0.001, high - low);
  const points = series.map((value, index) => `${index / Math.max(1, series.length - 1) * 100},${31 - (value - low) / span * 26}`).join(" ");
  return <svg viewBox="0 0 100 34" preserveAspectRatio="none"><polyline points={points} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" /></svg>;
}

function NuclearTrends({ history = {} }) {
  const charts = [
    ["reactor_power_pct", "Reactor power", "%", "#f2b761"],
    ["primary_pressure_mpa", "Primary pressure", "MPa", "#f07576"],
    ["minimum_sg_level_pct", "Minimum SG level", "%", "#62aaf7"],
    ["electric_output_mwe", "Electric output", "MWe", "#5dd6c0"],
    ["thermal_dispatch_mwth", "Heat dispatch", "MWth", "#b38ff4"],
    ["condenser_pressure_kpa_abs", "Condenser", "kPa abs", "#98a8aa"],
  ];
  return <section className="infra-card trend-card"><div className="infra-card-title"><span>Rolling plant trends</span><b>60 min</b></div><div className="trend-grid">{charts.map(([key, title, unit, color]) => { const values = history[key] || []; return <div key={key}><span>{title}</span><strong>{fmt(values.at(-1), key.includes("pressure_mpa") ? 2 : 1)} {unit}</strong><MiniTrend values={values} color={color} /></div>; })}</div></section>;
}

function ProcedurePanel({ procedures = [] }) {
  const [expanded, setExpanded] = React.useState("CP-01");
  return <section className="infra-card procedure-card"><div className="infra-card-title"><span>Computerized response guidance</span><b>{procedures.length}</b></div>{procedures.map((procedure) => <button className={`procedure-row ${procedure.status}`} key={procedure.id} onClick={() => setExpanded(expanded === procedure.id ? "" : procedure.id)}><span>{procedure.id}</span><div><strong>{procedure.title}</strong><small>{procedure.reason}</small>{expanded === procedure.id && <ol>{procedure.steps.map((step) => <li key={step}>{step}</li>)}</ol>}</div><em>{label(procedure.status)}</em></button>)}</section>;
}

function ModelHealth({ health = {} }) {
  const items = [["Steam balance", health.steam_balance_error_pct, "% error"], ["Mass imbalance", health.secondary_mass_imbalance_pct, "%"], ["SG level spread", health.steam_generator_level_spread_pct, "%"], ["Pressure trip margin", health.primary_pressure_trip_margin_mpa, "MPa"], ["Feed pump efficiency", health.feedwater_pump_efficiency_pct, "%"], ["RCP bearing health", health.rcp_bearing_health_pct, "%"]];
  return <section className="infra-card model-health-card"><div className="infra-card-title"><span>Model and equipment health</span><StatePill state={health.status === "healthy" ? "normal" : "warning"}>{health.status || "waiting"}</StatePill></div><div className="health-grid">{items.map(([name, value, unit]) => <div key={name}><span>{name}</span><strong>{fmt(value, 2)} <small>{unit}</small></strong></div>)}</div><p>{health.fidelity || "Reduced-order model"}. Values are illustrative.</p></section>;
}

function TuningPanel({ tuning = {}, onTune }) {
  const [preset, setPreset] = React.useState(tuning.preset || "nominal");
  React.useEffect(() => setPreset(tuning.preset || "nominal"), [tuning.preset]);
  const submit = (next) => { setPreset(next); onTune({ preset: next }); };
  return <section className="infra-card tuning-card"><div className="infra-card-title"><span>Reduced-order response tuning</span><b>4 gains</b></div><label>Preset<select value={preset} onChange={(event) => submit(event.target.value)}><option value="nominal">Nominal</option><option value="slow_thermal">Slow thermal response</option><option value="high_inertia">High system inertia</option><option value="degraded_heat_transfer">Degraded heat transfer</option></select></label><div className="gain-grid"><span>Thermal <b>{fmt(tuning.thermal_response, 2)}</b></span><span>Pressure <b>{fmt(tuning.pressure_response, 2)}</b></span><span>Inventory <b>{fmt(tuning.inventory_response, 2)}</b></span><span>Condenser <b>{fmt(tuning.condenser_response, 2)}</b></span></div><p>Presets adjust response speed for research exercises. They are not plant coefficients.</p></section>;
}

function AlarmTimeline({ events = [] }) {
  return <section className="infra-card alarm-timeline-card"><div className="infra-card-title"><span>Alarm event timeline</span><b>{events.length}</b></div>{events.length ? events.slice(0, 8).map((event, index) => <div className={`timeline-row ${event.severity}`} key={`${event.simulation_time}-${event.code}-${index}`}><span>{event.event}</span><strong>{event.code}</strong><small>{event.simulation_time?.slice(11, 16)}</small></div>) : <div className="infra-clear">No alarm transitions recorded</div>}</section>;
}

function NuclearRoom({ state, scenarios, onCommand, onManual, onAi, onTune }) {
  const metrics = [
    ["Reactor power", reading(state, "reactor_power_pct"), "%", 1], ["Primary coolant", reading(state, "primary_temperature_c"), "degC", 1], ["RCS pressure", reading(state, "primary_pressure_mpa"), "MPa", 2], ["Minimum SG level", Math.min(...["a", "b", "c"].map((name) => reading(state, `loop_${name}_sg_level_pct`, 55))), "%", 1], ["Electrical output", reading(state, "electric_output_mwe"), "MWe", 0], ["Heat dispatch", reading(state, "thermal_dispatch_mwth"), "MWth", 0],
  ];
  return <main className="page infrastructure-page nuclear-room">
    <div className="room-intro"><div><span className="eyebrow">Generic three-loop pressurized-water reactor</span><h1>Nuclear generation control room</h1><p>Three primary loops, secondary steam cycle, industrial heat dispatch, balance-of-plant, condition monitoring and independent reactor protection.</p></div><StatePill state={state?.safety_state}>{label(state?.safety_state || "waiting")}</StatePill></div>
    <RoomToolbar domain="nuclear" state={state} scenarios={scenarios} onCommand={onCommand} onAi={onAi} />
    <section className="infra-metrics">{metrics.map(([name, number, unit, digits]) => <div key={name}><span>{name}</span><strong>{fmt(number, digits)} <small>{unit}</small></strong></div>)}</section>
    <NuclearDiagram state={state} />
    <div className="infra-lower"><NuclearControls state={state} onManual={onManual} /><AiPanel state={state} boundary="AI may recommend turbine loading, condenser cooling and bounded industrial heat dispatch. Reactor protection, rods, steam isolation, engineered safety features and emergency actions are deterministic and independent." /><AlarmPanel alarms={state?.alarms} /></div>
    <section className="nuclear-analysis-grid"><NuclearTrends history={state?.history} /><ProcedurePanel procedures={state?.procedures} /></section>
    <section className="nuclear-diagnostics-grid"><ModelHealth health={state?.model_health} /><TuningPanel tuning={state?.tuning} onTune={onTune} /><AlarmTimeline events={state?.alarm_timeline} /></section>
    <OperationsPanel domain="nuclear" />
    <IOChannels inputs={state?.input_channels} outputs={state?.output_channels} />
    <p className="model-note">{state?.note}</p>
  </main>;
}

const BUS_POSITIONS = { B1: [10, 18], B2: [42, 18], B3: [78, 12], B4: [76, 72], B5: [36, 76] };

function GridDiagram({ state, onManual }) {
  const lines = state?.equipment?.lines || [];
  const buses = state?.equipment?.buses || [];
  return <section className="grid-diagram">
    <svg className="grid-lines" viewBox="0 0 100 100" preserveAspectRatio="none">{lines.map((line) => { const [x1,y1] = BUS_POSITIONS[`B${line.source + 1}`]; const [x2,y2] = BUS_POSITIONS[`B${line.target + 1}`]; return <line key={line.id} x1={x1} y1={y1} x2={x2} y2={y2} className={!line.closed ? "open" : line.loading_pct > 100 ? "critical" : "energized"} />; })}</svg>
    {buses.map((bus) => { const [left,top] = BUS_POSITIONS[bus.id]; return <div className="bus-node" key={bus.id} style={{ left: `${left}%`, top: `${top}%` }}><span>{bus.id}</span><strong>{bus.name}</strong><small>{fmt(bus.voltage_pu, 3)} pu</small></div>; })}
    <div className="generation-stack north"><div><b>G1</b><strong>{fmt(reading(state, "gas_generation_mw"), 0)} MW</strong><small>Gas</small></div><div><b>W1</b><strong>{fmt(reading(state, "wind_generation_mw"), 0)} MW</strong><small>Wind</small></div></div>
    <div className="generation-stack south"><div><b>S1</b><strong>{fmt(reading(state, "solar_generation_mw"), 0)} MW</strong><small>Solar</small></div><div><b>BESS</b><strong>{fmt(reading(state, "battery_power_mw"), 0)} MW</strong><small>{fmt(reading(state, "battery_soc_pct"), 0)}% SOC</small></div></div>
    <div className="line-control-bank">{lines.map((line) => <button key={line.id} className={!line.closed ? "open" : line.loading_pct > 100 ? "critical" : ""} onClick={() => onManual("grid", { [`${line.id}_breaker_closed`]: !line.closed })}><span>{line.id}</span><strong>{fmt(line.flow_mw, 0)} MW</strong><small>{line.closed ? `${fmt(line.loading_pct, 0)}% · CLOSED` : "OPEN"}</small></button>)}</div>
  </section>;
}

function GridControls({ state, onManual }) {
  const [values, setValues] = React.useState({ gas_dispatch_mw: 460, hydro_dispatch_mw: 240, battery_dispatch_mw: 0, capacitor_support_mvar: 20, demand_response_mw: 0 });
  React.useEffect(() => { setValues((current) => ({ ...current, gas_dispatch_mw: Number(state?.controls?.gas_dispatch_mw ?? 460), hydro_dispatch_mw: Number(state?.controls?.hydro_dispatch_mw ?? 240), battery_dispatch_mw: Number(state?.controls?.battery_dispatch_mw ?? 0), capacitor_support_mvar: Number(state?.controls?.capacitor_support_mvar ?? 20), demand_response_mw: Number(state?.controls?.demand_response_mw ?? 0) })); }, [state?.controls?.gas_dispatch_mw, state?.controls?.hydro_dispatch_mw, state?.controls?.battery_dispatch_mw, state?.controls?.capacitor_support_mvar, state?.controls?.demand_response_mw]);
  const controls = [["gas_dispatch_mw", "Gas dispatch", 0, 650, 10, "MW"], ["hydro_dispatch_mw", "Hydro dispatch", 80, 320, 5, "MW"], ["battery_dispatch_mw", "Battery output", -100, 100, 5, "MW"], ["capacitor_support_mvar", "Capacitor support", 0, 120, 10, "MVAr"], ["demand_response_mw", "Demand response", 0, 120, 10, "MW"]];
  return <section className="infra-card control-console grid-controls"><div className="infra-card-title"><span>Dispatch and voltage controls</span><b>{controls.length}</b></div>{controls.map(([name, title, min, max, step, unit]) => <label key={name}>{title} <strong>{values[name]} {unit}</strong><input type="range" min={min} max={max} step={step} value={values[name]} onChange={(event) => setValues({ ...values, [name]: Number(event.target.value) })} /></label>)}<button onClick={() => onManual("grid", values)}>Confirm bounded changes</button></section>;
}

function GridRoom({ state, scenarios, onCommand, onManual, onAi }) {
  const metrics = [["System frequency", reading(state, "frequency_hz"), "Hz", 3], ["Generation", reading(state, "total_generation_mw"), "MW", 0], ["Demand", reading(state, "system_demand_mw"), "MW", 0], ["Unserved load", reading(state, "unserved_load_mw"), "MW", 1], ["Lowest voltage", Math.min(...[1,2,3,4,5].map((index) => reading(state, `bus_${index}_voltage_pu`, 1))), "pu", 3], ["Reactive margin", reading(state, "reactive_margin_mvar"), "MVAr", 0]];
  return <main className="page infrastructure-page grid-room">
    <div className="room-intro"><div><span className="eyebrow">Five-bus transmission and distribution model</span><h1>Power-grid control room</h1><p>Generation dispatch, renewable variability, storage, bus voltage, line loading, breakers, frequency and customer demand.</p></div><StatePill state={state?.safety_state}>{label(state?.safety_state || "waiting")}</StatePill></div>
    <RoomToolbar domain="grid" state={state} scenarios={scenarios} onCommand={onCommand} onAi={onAi} />
    <section className="infra-metrics">{metrics.map(([name, number, unit, digits]) => <div key={name}><span>{name}</span><strong>{fmt(number, digits)} <small>{unit}</small></strong></div>)}</section>
    <GridDiagram state={state} onManual={onManual} />
    <div className="infra-lower"><GridControls state={state} onManual={onManual} /><AiPanel state={state} boundary="AI may optimize generator dispatch, battery power, demand response, transformer taps and reactive support. Breaker protection remains deterministic or operator-confirmed." /><AlarmPanel alarms={state?.alarms} /></div>
    <OperationsPanel domain="grid" />
    <IOChannels inputs={state?.input_channels} outputs={state?.output_channels} />
    <p className="model-note">{state?.note}</p>
  </main>;
}

export { GridRoom, NuclearRoom };
