import React, { useEffect, useMemo, useState } from "react";
import "./research.css";
import ResearchDemo from "./ResearchDemo";

const SIGNALS = [
  ["filtered_turbidity_ntu", "Effluent turbidity", "NTU"],
  ["raw_turbidity_ntu", "Raw water turbidity", "NTU"],
  ["coagulant_dose_actual_mg_l", "Actual coagulant dose", "mg/L"],
  ["coagulation_ph", "Coagulation pH", "pH"],
  ["finished_water_ph", "Finished water pH", "pH"],
  ["chlorine_residual_mg_l", "Chlorine residual", "mg/L"],
];
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const format = (value, digits = 2) => finite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "Not recorded";
const signed = (value) => finite(value) ? `${value > 0 ? "+" : ""}${format(value, 4)}` : "Not recorded";
const readable = (value) => value == null ? "Not recorded" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
const displayName = (value) => typeof value === "string" ? value.replaceAll("_", " ") : readable(value);
const probability = (value) => !finite(value) ? "Not recorded" : value > 0 && value < 0.0001 ? `${(value * 100).toExponential(2)}%` : `${format(value * 100, 2)}%`;
const sampleValue = (sample, key) => sample?.values?.[key];
const sorted = (items = []) => [...items].filter((item) => finite(item.minute)).sort((a, b) => a.minute - b.minute);
const localUrl = (path) => {
  if (typeof path !== "string") return null;
  try {
    const url = new URL(path, `${window.location.origin}/research/`);
    return url.origin === window.location.origin ? url.pathname + url.search : null;
  } catch { return null; }
};
async function readJson(path, signal) {
  const url = localUrl(path);
  if (!url) throw new Error("The dataset must be served from this local application.");
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`Dataset unavailable (HTTP ${response.status}).`);
  try { return await response.json(); } catch { throw new Error("The dataset URL did not return valid JSON."); }
}
function useDataset(url, revision) {
  const [state, setState] = useState({ data: null, loading: false, error: "" });
  useEffect(() => {
    if (!url) { setState({ data: null, loading: false, error: "" }); return; }
    const controller = new AbortController();
    setState({ data: null, loading: true, error: "" });
    readJson(url, controller.signal).then((data) => setState({ data, loading: false, error: "" })).catch((error) => {
      if (error.name !== "AbortError") setState({ data: null, loading: false, error: error.message });
    });
    return () => controller.abort();
  }, [url, revision]);
  return state;
}
function Raw({ title, value, open = false }) {
  return <details className="rd-disclosure" open={open || undefined}><summary>{title}</summary><pre>{readable(value)}</pre></details>;
}
function Download({ url, children = "Download JSON" }) {
  const safe = localUrl(url);
  return safe ? <a className="rd-link" href={safe} download>{children} <span aria-hidden="true">↗</span></a> : null;
}
function Facts({ rows }) {
  return <dl className="rd-facts">{rows.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>;
}
function Empty({ error, loading, kind, reload }) {
  return <div className={`rd-empty ${loading ? "rd-loading" : ""}`} role="status" aria-live="polite">
    <h2>{loading ? "Loading local evidence…" : error ? "Evidence could not be loaded" : `No ${kind} exported yet`}</h2>
    <p>{error || (loading ? "Reading the saved experiment artifacts." : "This view reads saved JSON experiments. Run the study and export its artifacts, then reload to inspect measured results.")}</p>
    {!loading && <button className="rd-button" onClick={reload}>Reload</button>}
  </div>;
}
function closest(samples, minute) {
  return samples.reduce((best, sample) => !best || Math.abs(sample.minute - minute) < Math.abs(best.minute - minute) ? sample : best, null);
}
function LineChart({ baseline = [], agent = [], signal, unit, minute, threshold, onMinute }) {
  const all = [...baseline, ...agent].filter((sample) => finite(sampleValue(sample, signal)));
  if (!all.length) return <p className="rd-note">No measurements for this signal.</p>;
  const left = 58, right = 866, top = 24, bottom = 258;
  const maxMinute = Math.max(...all.map((sample) => sample.minute), 1);
  const minMinute = Math.min(...all.map((sample) => sample.minute), 0);
  const values = all.map((sample) => sampleValue(sample, signal));
  if (finite(threshold)) values.push(threshold);
  const lo = Math.min(0, ...values), hi = Math.max(...values, lo + 0.1) * 1.08;
  const x = (value) => left + ((value - minMinute) / (maxMinute - minMinute)) * (right - left);
  const y = (value) => bottom - ((value - lo) / (hi - lo)) * (bottom - top);
  const paths = [baseline, agent].map((samples) => {
    let connected = false;
    return samples.map((sample) => {
      const value = sampleValue(sample, signal);
      if (!finite(value)) { connected = false; return ""; }
      const part = `${connected ? "L" : "M"}${x(sample.minute)},${y(value)}`;
      connected = true;
      return part;
    }).join(" ");
  });
  return <div className="rd-chart-wrap">
    <svg className="rd-chart" viewBox="0 0 900 304" role="img" aria-label={`${SIGNALS.find((item) => item[0] === signal)?.[1] || signal} over simulated minutes. Baseline dashed blue; AI trial solid teal.${onMinute ? ` Selected minute ${format(minute)}. Use the minute slider for exact readings.` : finite(threshold) ? ` Display threshold ${format(threshold)} ${unit}.` : ""}`} onClick={onMinute ? (event) => { const bounds = event.currentTarget.getBoundingClientRect(); onMinute(Math.max(minMinute, Math.min(maxMinute, minMinute + (((event.clientX - bounds.left) / bounds.width * 900 - left) / (right - left)) * (maxMinute - minMinute)))); } : undefined}>
      <text x={left} y="13" className="rd-axis-title">{unit}</text>
      {[0, 1, 2, 3, 4].map((tick) => { const value = lo + ((hi - lo) * tick / 4); return <g key={tick}><line x1={left} x2={right} y1={y(value)} y2={y(value)} className="rd-grid" /><text x={left - 10} y={y(value) + 4} textAnchor="end">{format(value)}</text></g>; })}
      {[0, 1, 2, 3, 4].map((tick) => { const value = minMinute + (maxMinute - minMinute) * tick / 4; return <text key={tick} x={x(value)} y="280" textAnchor="middle">{format(value, 0)}</text>; })}
      <text x={right} y="299" textAnchor="end" className="rd-axis-title">Simulated minute</text>
      {finite(threshold) && <g><line x1={left} x2={right} y1={y(threshold)} y2={y(threshold)} className="rd-threshold" /><text x={right} y={Math.max(14, y(threshold) - 7)} textAnchor="end" className="rd-threshold-label">Display threshold {format(threshold)} {unit}</text></g>}
      {paths.map((path, index) => <path key={index} d={path} className={index ? "rd-agent-line" : "rd-baseline-line"} />)}
      {finite(minute) && <line x1={x(minute)} x2={x(minute)} y1={top} y2={bottom} className="rd-cursor" />}
      {finite(minute) && [baseline, agent].map((samples, index) => { const sample = closest(samples, minute); return sample && finite(sampleValue(sample, signal)) ? <circle key={index} cx={x(sample.minute)} cy={y(sampleValue(sample, signal))} r="4.5" fill={index ? "#48d6c4" : "#88bbff"} stroke="#071013" strokeWidth="2" /> : null; })}
    </svg>
  </div>;
}
function Legend() { return <div className="rd-legend"><span className="rd-key-baseline">Baseline</span><span className="rd-key-agent">8B AI trial</span></div>; }
function Timeline({ study, url, initialMinute = 0 }) {
  const baseline = useMemo(() => sorted(study.samples?.baseline), [study]);
  const agent = useMemo(() => sorted(study.samples?.agent), [study]);
  const exchanges = useMemo(() => sorted(study.exchanges), [study]);
  const times = useMemo(() => [...new Set([...baseline, ...agent, ...exchanges].map((item) => item.minute))].sort((a, b) => a - b), [baseline, agent, exchanges]);
  const [position, setPosition] = useState(() => Math.max(0, times.findIndex(time => time >= initialMinute)));
  const [signal, setSignal] = useState(SIGNALS[0][0]);
  const minute = times[Math.min(position, times.length - 1)] ?? 0;
  const selected = [...exchanges].reverse().find((exchange) => exchange.minute <= minute);
  const baselineSample = closest(baseline, minute), agentSample = closest(agent, minute);
  const chooseMinute = (value) => {
    const nearest = times.reduce((best, item, index) => Math.abs(item - value) < Math.abs(times[best] - value) ? index : best, 0);
    setPosition(nearest);
  };
  return <>
    <div className="rd-section-intro"><div><h2>Control timeline</h2></div><Download url={url}>Full control artifact</Download></div>
    <div className="rd-timeline-layout">
      <section className="rd-main-chart" aria-label="Treatment response">
        <div className="rd-chart-toolbar"><label>Signal<select value={signal} onChange={(event) => setSignal(event.target.value)}>{SIGNALS.map(([key, label, unit]) => <option key={key} value={key}>{label} · {unit}</option>)}</select></label><Legend /></div>
        <LineChart baseline={baseline} agent={agent} signal={signal} unit={SIGNALS.find((item) => item[0] === signal)[2]} minute={minute} onMinute={chooseMinute} />
        <div className="rd-scrubber"><div><label htmlFor="rd-minute">Selected simulated minute</label><output htmlFor="rd-minute">{format(minute, 1)}</output></div><input id="rd-minute" type="range" min="0" max={Math.max(0, times.length - 1)} step="1" value={Math.min(position, Math.max(0, times.length - 1))} disabled={times.length < 2} aria-valuetext={`Simulated minute ${format(minute)}`} onChange={(event) => setPosition(Number(event.target.value))} /><div className="rd-scrub-ends"><span>{format(times[0], 0)} min</span><span>{format(times.at(-1), 0)} min</span></div></div>
        <div className="rd-table-scroll"><table className="rd-table"><caption>Nearest recorded samples to selected minute</caption><thead><tr><th scope="col">Reading</th><th scope="col">Baseline · {format(baselineSample?.minute)} min</th><th scope="col">AI · {format(agentSample?.minute)} min</th></tr></thead><tbody>{SIGNALS.map(([key, label, unit]) => <tr key={key} className={key === signal ? "rd-selected-row" : ""}><th scope="row">{label} <small>{unit}</small></th><td>{format(sampleValue(baselineSample, key), 3)}</td><td>{format(sampleValue(agentSample, key), 3)}</td></tr>)}<tr><th scope="row">Coagulant target <small>mg/L</small></th><td>{format(baselineSample?.setpoints?.coagulant_target_mg_l)}</td><td>{format(agentSample?.setpoints?.coagulant_target_mg_l)}</td></tr></tbody></table></div>
        <Raw title="Selected samples: quality, alarms & actuators" value={{ baseline: baselineSample, agent: agentSample }} />
      </section>
      <aside className="rd-exchange" aria-label="Selected AI exchange"><div className="rd-exchange-title"><h3>AI exchange</h3><span>{selected ? `Minute ${format(selected.minute)}` : "Not yet recorded"}</span></div>
        <label className="rd-exchange-picker">Jump to a decision<select value={selected ? exchanges.indexOf(selected) : ""} onChange={(event) => chooseMinute(exchanges[Number(event.target.value)].minute)}><option value="" disabled>Select a recorded exchange</option>{exchanges.map((exchange, index) => <option value={index} key={exchange.record_id || index}>Minute {format(exchange.minute)} · {displayName(exchange.status)}</option>)}</select></label>
        {selected ? <><p className="rd-state">{displayName(selected.status)} <span>· {format(selected.latency_seconds)} s inference</span></p><p className="rd-explanation">{readable(selected.explanation)}</p>
          <Facts rows={[["History samples", format(selected.context?.sample_count, 0)], ["Prior exchanges", format(selected.context?.prior_count, 0)], ["Prompt / configured tokens", `${format(selected.context?.prompt_tokens, 0)} / ${format(selected.context?.configured_tokens, 0)}`], ["Episode status", displayName(selected.episode_status)]]} />
          <Raw title="Proposed action" value={selected.proposed} open /><Raw title="Applied action & gate result" value={{ applied: selected.applied, gate: selected.gate }} />
          <Raw title="Model-emitted reasoning text" value={selected.thinking || "No reasoning text was emitted in this record."} /><p className="rd-note">Emitted rationale · unverified</p><Download url={selected.record_url}>Original exchange</Download>
        </> : <p className="rd-note">No AI exchange is recorded at or before this minute. Move forward to inspect the first decision.</p>}
      </aside>
    </div>
    <Raw title="Control trial protocol & source provenance" value={{ model: study.model, source_sha256: study.source_sha256, protocol: study.protocol, status: study.status }} />
  </>;
}
function excursionDuration(samples, threshold, start, end) {
  let duration = 0, observed = 0;
  for (let index = 0; index < samples.length - 1; index++) {
    const value = sampleValue(samples[index], "filtered_turbidity_ntu");
    const interval = Math.max(0, Math.min(samples[index + 1].minute, end) - Math.max(samples[index].minute, start));
    if (finite(value) && samples[index].quality?.filtered_turbidity_ntu === "good") { observed += interval; if (value > threshold) duration += interval; }
  }
  return { duration, observed };
}
function Risk({ study }) {
  const originalThreshold = Number(String(study.protocol?.trigger || "").match(/>\s*([\d.]+)/)?.[1]) || 1.0;
  const [threshold, setThreshold] = useState(originalThreshold);
  const baseline = useMemo(() => sorted(study.samples?.baseline), [study]);
  const agent = useMemo(() => sorted(study.samples?.agent), [study]);
  const start = Math.max(baseline[0]?.minute ?? 0, agent[0]?.minute ?? 0);
  const end = Math.min(baseline.at(-1)?.minute ?? 0, agent.at(-1)?.minute ?? 0);
  const baselineExcursion = excursionDuration(baseline, threshold, start, end);
  const agentExcursion = excursionDuration(agent, threshold, start, end);
  const validHorizon = baseline.length > 1 && agent.length > 1 && end > start;
  const exchanges = sorted(study.exchanges);
  const latencies = exchanges.filter((item) => finite(item.latency_seconds));
  const maxLatency = Math.max(1, ...latencies.map((item) => item.latency_seconds));
  const metrics = study.metrics || {};
  const counts = [baseline, agent].map((samples) => {
    const observed = samples.filter((sample) => sample.minute > 0 && sample.minute >= start && sample.minute <= end && finite(sampleValue(sample, "filtered_turbidity_ntu")) && sample.quality?.filtered_turbidity_ntu === "good");
    const prefix = samples === baseline ? "baseline" : "agent";
    return { above: metrics[`${prefix}_excursion_samples`] ?? observed.filter((sample) => sampleValue(sample, "filtered_turbidity_ntu") > originalThreshold).length, total: metrics[`${prefix}_observed_samples`] ?? observed.length };
  });
  return <>
    <div className="rd-section-intro"><div><h2>Process risk</h2></div><span className="rd-badge rd-warning">{displayName(study.status)} · archived</span></div>
    <div className="rd-risk-layout"><section><div className="rd-chart-toolbar"><h3>Effluent response</h3><Legend /></div><LineChart baseline={baseline} agent={agent} signal="filtered_turbidity_ntu" unit="NTU" threshold={threshold} /><div className="rd-threshold-control"><label htmlFor="rd-threshold">Display threshold <strong>{format(threshold)} NTU</strong></label><input id="rd-threshold" type="range" min="0.05" max="2" step="0.05" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /><p>Display threshold only</p></div>
      <div className="rd-table-scroll"><table className="rd-table"><caption>Estimated time above display threshold · matched window {format(start)}–{format(end)} min</caption><thead><tr><th>Run</th><th>Estimated duration</th><th>Observed coverage</th></tr></thead><tbody><tr><th scope="row">Baseline</th><td>{validHorizon ? `${format(baselineExcursion.duration)} min` : "Insufficient samples"}</td><td>{validHorizon ? `${format(baselineExcursion.observed)} min` : "Not recorded"}</td></tr><tr><th scope="row">8B AI trial</th><td>{validHorizon ? `${format(agentExcursion.duration)} min` : "Insufficient samples"}</td><td>{validHorizon ? `${format(agentExcursion.observed)} min` : "Not recorded"}</td></tr></tbody></table></div><details className="rd-disclosure"><summary>Exposure method</summary><p className="rd-note">Estimated duration uses the preceding measurement until the next recorded sample (left hold), clipped to the common window. Only finite measurements marked good quality contribute. This is an estimate, not a sample count or continuous monitoring.</p></details>
      <div className="rd-table-scroll" style={{ marginTop: 24 }}><table className="rd-table"><caption>Recorded readings above the original {format(originalThreshold)} NTU bound · unchanged by the display slider</caption><thead><tr><th>Run</th><th>Above bound / good readings</th></tr></thead><tbody>{counts.map((count, index) => <tr key={index}><th scope="row">{index ? "8B AI trial" : "Baseline"}</th><td>{count.total ? `${count.above} / ${count.total}` : "No good readings"}</td></tr>)}</tbody></table></div><details className="rd-disclosure"><summary>Sampling convention</summary><p className="rd-note">Counts use recorded endpoints in the matched window, excluding minute zero. For example, 31 above-bound readings may represent 30 minutes under the left-hold estimate.</p></details>
    </section><aside className="rd-risk-notes"><h3>Recorded outcomes</h3><Facts rows={[["AI exchanges", format(metrics.total, 0)], ["Inference failures", format(metrics.failures, 0)], ["Applied exchanges", format(metrics.applied, 0)], ["Inference latency", `${format(metrics.latency_min)}–${format(metrics.latency_max)} s`], ["Baseline final effluent", `${format(typeof metrics.baseline_final === "number" ? metrics.baseline_final : metrics.baseline_final?.filtered_turbidity_ntu, 3)} NTU`], ["AI final effluent", `${format(typeof metrics.agent_final === "number" ? metrics.agent_final : metrics.agent_final?.filtered_turbidity_ntu, 3)} NTU`]]} /><h3>Study limits</h3><p>{readable(study.interpretation)}</p><details className="rd-disclosure"><summary>Scope</summary><p className="rd-note">These observations do not estimate catastrophe probability or establish a calibrated safety score. A single saved scenario does not establish performance across plants or operating conditions.</p></details><Raw title="Original run metrics" value={metrics} /></aside></div>
    <section className="rd-latencies"><div className="rd-section-intro"><div><h3>Inference latency by exchange</h3><p>Wall-clock seconds / call</p></div></div>{latencies.length ? <div className="rd-latency-list">{latencies.map((item, index) => <div className="rd-latency-row" key={item.record_id || index}><span>Minute {format(item.minute)}</span><div className="rd-latency-track"><span style={{ width: `${item.latency_seconds / maxLatency * 100}%` }} /></div><strong>{format(item.latency_seconds)} s</strong><span>{displayName(item.status)}</span></div>)}</div> : <p className="rd-note">No latency measurements have been exported.</p>}</section>
  </>;
}
function Heatmap({ activation }) {
  const layers = activation?.layers || [], tokens = activation?.tokens || [], matrix = activation?.matrix || [];
  const [selected, setSelected] = useState([0, 0]);
  if (!layers.length || !tokens.length) return <p className="rd-note">No layer-by-token activation measurements were exported.</p>;
  const maximum = Math.max(...matrix.flat().filter(finite), 0.000001);
  const [row, column] = selected;
  const selectCell = (nextRow, nextColumn, focus = false) => {
    const r = Math.max(0, Math.min(layers.length - 1, nextRow)), c = Math.max(0, Math.min(tokens.length - 1, nextColumn));
    setSelected([r, c]);
    if (focus) document.getElementById(`rd-heat-${r}-${c}`)?.focus();
  };
  return <><div className="rd-heat-readout" aria-live="polite"><span>Layer {layers[row]} · captured token {column}</span><code>{tokens[column]}</code><strong>{format(matrix[row]?.[column], 5)} relative RMS Δ</strong></div><div className="rd-heat-scroll" tabIndex="0" aria-label="Scrollable activation table"><table className="rd-heatmap"><caption>Relative RMS activation difference between the safe and alarm prompts. Columns index the captured token window, not the full prompt.</caption><thead><tr><th scope="col">Layer / token</th>{tokens.map((token, index) => <th scope="col" key={index} title={token}><span>{index}</span><code>{token}</code></th>)}</tr></thead><tbody>{layers.map((layer, layerIndex) => <tr key={layer}><th scope="row">{layer}</th>{tokens.map((token, tokenIndex) => { const value = matrix[layerIndex]?.[tokenIndex], intensity = finite(value) ? Math.sqrt(Math.max(0, value) / maximum) : 0; return <td key={tokenIndex}><button id={`rd-heat-${layerIndex}-${tokenIndex}`} tabIndex={row === layerIndex && column === tokenIndex ? 0 : -1} className={row === layerIndex && column === tokenIndex ? "rd-heat-selected" : ""} onClick={() => selectCell(layerIndex, tokenIndex)} onKeyDown={(event) => { const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }; if (moves[event.key]) { event.preventDefault(); selectCell(layerIndex + moves[event.key][0], tokenIndex + moves[event.key][1], true); } }} title={`Layer ${layer}, token ${tokenIndex} ${token}: ${format(value, 6)} relative RMS difference`} aria-label={`Layer ${layer}, token ${tokenIndex} ${token}, relative RMS difference ${format(value, 6)}`} style={{ backgroundColor: `rgba(72, 214, 196, ${0.04 + intensity * 0.7})`, color: intensity > 0.5 ? "#041614" : "#e7f0ef" }}>{finite(value) ? value.toFixed(2) : "—"}</button></td>; })}</tr>)}</tbody></table></div><details className="rd-disclosure"><summary>Heatmap scale</summary><p className="rd-note">Color is scaled to the largest measured difference in this case. Use arrow keys on a cell to inspect neighbors. Activation magnitude is not risk or evidence of a specific causal mechanism.</p></details></>;
}
function Internals({ study, url }) {
  const [caseId, setCaseId] = useState(study.cases?.[0]?.id || "");
  const selected = study.cases?.find((item) => item.id === caseId) || study.cases?.[0];
  const patches = selected?.patches || [];
  const maxEffect = Math.max(...patches.map((item) => Math.abs(item.effect)).filter(finite), 0.001);
  return <>
    <div className="rd-section-intro"><div><h2>Activation probe</h2><p>Qwen3 4B / binary threshold task</p>{study.distribution_note&&<p>{study.distribution_note}</p>}</div><div className="rd-artifact-links"><Download url={url}>Full mechanistic artifact</Download><Download url={study.activations_url}>Raw activations · NPZ</Download></div></div>
    <div className="rd-internals-context"><label>Prompt case<select value={selected?.id || ""} onChange={(event) => setCaseId(event.target.value)}>{(study.cases || []).map((item) => <option key={item.id} value={item.id}>{displayName(item.id)} · {item.swapped ? "labels swapped" : "original labels"}</option>)}</select></label><p>{study.cases?.length || 0} cases · {study.cases?.[0]?.activation_delta?.layers?.length || 0} layers · {study.cases?.reduce((total,item)=>total+(item.patches?.length||0),0) || 0} patches</p></div>
    {selected ? <><div className="rd-probability-layout"><section><h3>A/B readout</h3><div className="rd-table-scroll"><table className="rd-table"><caption>A/B scores · not plant risk</caption><thead><tr><th scope="col">Prompt</th><th scope="col">Input value</th><th scope="col">P(review | A/B)</th><th scope="col">A/B token mass</th><th scope="col">Review logit gap</th><th scope="col">Greedy token</th></tr></thead><tbody>{["safe", "alarm"].map((kind) => <tr key={kind}><th scope="row">{kind === "safe" ? "Safe input" : "Alarm input"}</th><td>{format(selected[`${kind}_value`], 3)}</td><td>{probability(selected[kind]?.review_probability)}</td><td>{probability(selected[kind]?.choice_mass)}</td><td>{signed(selected[kind]?.logit_gap)}</td><td><code>{readable(selected[kind]?.greedy_token)}</code></td></tr>)}</tbody></table></div></section><details className="rd-disclosure"><summary>Score definition</summary><p className="rd-note">{readable(study.methodology?.score_definition)} Low A/B token mass means the model may prefer a different next token.</p></details></div>
      <section className="rd-heat-section"><div className="rd-section-intro"><div><h3>Activation Δ</h3><p>Layer × token · safe versus alarm prompt</p></div></div><Heatmap key={selected.id} activation={selected.activation_delta} /></section>
      <section className="rd-patch-section"><div className="rd-section-intro"><div><h3>Patch effects</h3><p>Δ review − continue logit gap</p></div></div>{patches.length ? <div className="rd-table-scroll"><table className="rd-table rd-patch-table"><caption>Single-layer replacements</caption><thead><tr><th scope="col">Layer</th><th scope="col">Patch direction</th><th scope="col">Before gap</th><th scope="col">After gap</th><th scope="col">Signed effect</th><th scope="col">After P(review | A/B)</th></tr></thead><tbody>{patches.map((patch, index) => <tr key={index}><th scope="row">{patch.layer}</th><td>{displayName(patch.direction)}</td><td>{signed(patch.before_gap)}</td><td>{signed(patch.after_gap)}</td><td><div className="rd-effect"><div className="rd-effect-track"><span style={{ left: patch.effect < 0 ? `${50 - Math.abs(patch.effect) / maxEffect * 48}%` : "50%", width: `${Math.abs(patch.effect) / maxEffect * 48}%`, background: patch.effect < 0 ? "#f0bc5e" : "#48d6c4" }} /></div><strong>{signed(patch.effect)}</strong></div></td><td>{probability(patch.review_probability)}</td></tr>)}</tbody></table></div> : <p className="rd-note">No patch measurements are present in this case.</p>}</section>
      <section className="rd-verification"><h3>Verification & boundaries</h3><Facts rows={[["Self-patch maximum error", format(selected.self_patch?.max_error, 8)], ["Self-patch tolerance", format(selected.self_patch?.tolerance, 8)], ["NNsight trace", displayName(selected.nnsight?.status)], ["NNsight checked layer", format(selected.nnsight?.layer, 0)], ["NNsight activation difference", format(selected.nnsight?.max_abs_difference, 8)], ["NNsight logit difference", format(selected.nnsight?.max_logit_difference, 8)], ["Captured shape", readable(selected.nnsight?.captured_shape)]]} /><p className="rd-note">Self-patching checks that replacing an activation with itself preserves the output. The NNsight comparison checks the safe input at the listed layer against the reference forward pass and logits. This check does not cover every layer or the alarm input; neither check establishes that the model is safe.</p><details className="rd-disclosure"><summary>Experiment limits</summary><p className="rd-note">{readable(study.methodology?.limitations)}</p></details></section>
      <div className="rd-prompts"><Raw title="Exact safe prompt" value={selected.prompts?.safe} /><Raw title="Exact alarm prompt" value={selected.prompts?.alarm} /></div>
    </> : <p className="rd-note">This study has no exported prompt cases yet.</p>}
    <Raw title="Model, package versions & experiment provenance" value={{ id: study.id, status: study.status, model: study.model, methodology: study.methodology, source_sha256: study.source_sha256, activations_sha256: study.activations_sha256 }} />
  </>;
}
export default function ResearchDashboard({ standalone = false }) {
  const [view, setView] = useState("demo"), [revision, setRevision] = useState(0);
  const [presenting, setPresenting] = useState(false), [focusMinute, setFocusMinute] = useState(0);
  const explore = (next, minute = 0) => { setPresenting(false); setFocusMinute(minute); setView(next); };
  const [controlId, setControlId] = useState(""), [mechanisticId, setMechanisticId] = useState("");
  const index = useDataset("/research/index.json", revision);
  const controls = Array.isArray(index.data?.control_studies) ? index.data.control_studies : [];
  const mechanisms = Array.isArray(index.data?.mechanistic_studies) ? index.data.mechanistic_studies : [];
  const controlEntry = controls.find((entry) => entry.id === controlId) || controls[0];
  const mechanismEntry = mechanisms.find((entry) => entry.id === mechanisticId) || mechanisms[0];
  const control = useDataset(controlEntry?.url, revision), mechanism = useDataset(mechanismEntry?.url, revision);
  const active = view === "internals" ? mechanism : control;
  const entries = view === "internals" ? mechanisms : controls;
  const entry = view === "internals" ? mechanismEntry : controlEntry;
  const reload = () => { setPresenting(false); setRevision((value) => value + 1); };
  const tabs = [["demo", "Demo"], ["timeline", "Timeline"], ["risk", "Risk"], ["internals", "Internals"]];
  return <main className={`research-dashboard ${standalone ? "rd-standalone" : ""} ${presenting ? "rd-presenting" : ""} ${view === "demo" ? "rd-demo-view" : ""}`}>
    {standalone && <div className="rd-standalone-bar"><a href="/research.html">WaterLab / Research</a>{import.meta.env.VITE_HOSTED==='true'?<a href="/">Start a simulation ↗</a>:['localhost','127.0.0.1'].includes(window.location.hostname)?<a href="http://127.0.0.1:18780/">Live lab ↗</a>:<a href="https://github.com/xienanzheng/ot-ai-assurance-lab">Run the lab ↗</a>}<span>Recorded / read only</span></div>}
    <header className="rd-header"><div><p className="rd-kicker">WaterLab Research</p><h1>Assurance</h1><p>Control / risk / internals</p></div><div className="rd-header-actions"><span className="rd-badge">Recorded</span><button className="rd-button" onClick={reload} disabled={index.loading || active.loading}>Reload</button></div></header>
    <div className="rd-scope"><p>Qwen3 8B / control trial <span aria-hidden="true"> · </span> Qwen3 4B / activation probe</p><span>Local evidence</span></div>
    <div className="rd-tabs" role="tablist" aria-label="Research views">{tabs.map(([id, title], position) => <button key={id} id={`rd-tab-${id}`} role="tab" aria-controls={`rd-panel-${id}`} aria-selected={view === id} tabIndex={view === id ? 0 : -1} onClick={() => setView(id)} onKeyDown={(event) => { const next = event.key === "ArrowRight" ? (position + 1) % tabs.length : event.key === "ArrowLeft" ? (position + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null; if (next !== null) { event.preventDefault(); setView(tabs[next][0]); document.getElementById(`rd-tab-${tabs[next][0]}`)?.focus(); } }}><span className="rd-nav-roll"><span>{title}</span><span aria-hidden="true">{title}</span></span></button>)}</div>
    <div role="tabpanel" id={`rd-panel-${view}`} aria-labelledby={`rd-tab-${view}`} className="rd-view" tabIndex="0">
      {view !== "demo" && entries.length > 0 && <div className="rd-study-bar"><label>Study<select value={entry?.id || ""} onChange={(event) => view === "internals" ? setMechanisticId(event.target.value) : setControlId(event.target.value)}>{entries.map((item) => <option key={item.id} value={item.id}>{item.title || item.id}</option>)}</select></label><span>{view === "internals" ? "Instrumented 4B model" : "Ollama 8B control trial"} · {displayName(active.data?.status || "loading")}</span></div>}
      {index.loading || index.error || active.loading || active.error || !active.data ? <Empty loading={index.loading || active.loading} error={index.error || active.error} kind={view === "internals" ? "mechanistic studies" : "control trials"} reload={reload} /> : view === "demo" ? <ResearchDemo control={control.data} mechanism={mechanism.data} mechanismLoading={mechanism.loading} mechanismError={mechanism.error} onReload={reload} onExplore={explore} presenting={presenting} onPresenting={setPresenting} /> : view === "timeline" ? <Timeline key={`${entry.id}-${focusMinute}`} study={active.data} url={entry.url} initialMinute={focusMinute} /> : view === "risk" ? <Risk key={entry.id} study={active.data} /> : <Internals key={entry.id} study={active.data} url={entry.url} />}
    </div>
    <footer className="rd-footer"><span>Recorded / read only</span><span>Exported {index.data?.generated_at ? new Date(index.data.generated_at).toLocaleString() : "time not recorded"}</span><Download url="/research/index.json">Evidence index</Download></footer>
  </main>;
}
