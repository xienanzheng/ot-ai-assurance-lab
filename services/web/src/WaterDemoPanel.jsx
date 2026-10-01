import React from 'react';
import {freshReading,feedbackView} from './waterControlView.mjs';
const number=value=>Number.isFinite(value)?value.toFixed(3):'—';
export default function WaterDemoPanel({plant,plc,loop,record,scenarios=[],onOpenHmi}) {
  const exercise=scenarios.find(s=>s.id===plant?.scenario)?.objective;
  if(!exercise)return null;
  const value=freshReading(plant.sensors?.[exercise.signal],plant.simulation_time);
  const monitor=feedbackView(loop,plant,plc),currentLoop=monitor.loop;
  const decision=record?.before?.plc?.controller_generation===plc?.controller_generation?record:null;
  const rows=(currentLoop?.process_history||[]).map(r=>({...r,value:freshReading({value:r.value,quality:r.quality,timestamp:r.timestamp},r.simulation_time)}));
  const points=rows.filter(r=>Number.isFinite(r.value));
  const [low,high]=exercise.operating_band;
  const chartBand=exercise.optimization_band||exercise.operating_band;
  const min=Math.min(chartBand[0],...points.map(r=>r.value))-.05,max=Math.max(chartBand[1],...points.map(r=>r.value))+.1;
  const x=m=>20+(m-(rows[0]?.minute||0))/Math.max(1,(rows.at(-1)?.minute||0)-(rows[0]?.minute||0))*580;
  const y=v=>130-(v-min)/(max-min)*110;
  const state=value==null?'Measurement unavailable':value>high||value<low?'Outside operating limits':'Within operating limits';
  const proposed=decision?.proposal?.changes?.[exercise.target];
  const applied=decision?.applied?(decision.gate?.applied_values?.[exercise.target]??proposed):null;
  return <section className="water-demo-panel" aria-label="Live water objective">
    <div className="water-demo-heading"><div><span className="eyebrow">Water · minute {plant.elapsed_minutes} · {plant.running?'Running':'Paused'}</span><h2>{exercise.name}</h2></div><button onClick={onOpenHmi}>Open water HMI →</button></div>
    <div className="water-demo-metrics">
      <div><span>{exercise.measurement}</span><strong>{number(value)} <small>{exercise.unit}</small></strong><em>{state}</em></div>
      <div><span>Operating limits</span><strong>{low.toFixed(2)}–{high.toFixed(2)} <small>{exercise.unit}</small></strong><em>Plant safety state: {plant.safety_state}</em></div>
      <div><span>{exercise.target_label}</span><strong>{number(plc?.setpoints?.[exercise.target])} <small>{exercise.target_unit}</small></strong><em>{plc?.control_state?.setpoint_lease_expires?'AI control lease active':'Baseline / operator control'}</em></div>
    </div>
    <p className="water-objective-note">{exercise.optimization_band&&<strong>Efficiency goal: {exercise.optimization_band.map(v=>v.toFixed(2)).join('–')} {exercise.unit}. </strong>}{!exercise.optimization_band&&exercise.note}</p>
    <div className="water-demo-response">
      <div>{points.length<2?<p className="training-empty">Start monitoring to record the measured response.</p>:<><svg viewBox="0 0 620 158" role="img" aria-label={`${exercise.measurement} over simulated time; shaded ${exercise.optimization_band?'efficiency goal':'operating range'}`}>
        <rect x="20" y={y(chartBand[1])} width="580" height={y(chartBand[0])-y(chartBand[1])} fill="#244e42"/>
        {chartBand.map(v=><g key={v}><line x1="20" x2="600" y1={y(v)} y2={y(v)} stroke="#6fbe9b" strokeDasharray="4 5"/><text x="25" y={y(v)-5} fill="#b8dcca" fontSize="11">{v.toFixed(2)}</text></g>)}
        {rows.map((r,i)=>i>0&&Number.isFinite(r.value)&&Number.isFinite(rows[i-1].value)?<line key={r.minute} x1={x(rows[i-1].minute)} y1={y(rows[i-1].value)} x2={x(r.minute)} y2={y(r.value)} stroke="#f2c476" strokeWidth="2.5"/>:null)}
        <text x="20" y="154" fill="#a6bec6" fontSize="11">{rows[0]?.minute} min</text><text x="600" y="154" textAnchor="end" fill="#a6bec6" fontSize="11">{rows.at(-1)?.minute} min</text>
      </svg><small>Measured response · shaded {exercise.optimization_band?'efficiency goal':'operating range'}.</small></>}</div>
      <dl><div><dt>Selected proposal</dt><dd>{!decision?'No analysis selected':proposed==null?'Hold · no target change':`${number(proposed)} ${exercise.target_unit}`}</dd></div><div><dt>Applied target</dt><dd>{applied==null?'None':`${number(applied)} ${exercise.target_unit}`}</dd></div><div role="status"><dt>Monitoring</dt><dd>{monitor.label}</dd><small>{monitor.detail}</small>{currentLoop&&<small> · {currentLoop.calls_used}/{currentLoop.max_calls} AI calls</small>}</div></dl>
    </div>
  </section>;
}
