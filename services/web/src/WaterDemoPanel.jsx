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
  const goal=exercise.optimization_band;
  const thresholds=exercise.alarm_thresholds;
  const chartBand=goal||(exercise.signal==='chlorine_residual_mg_l'?null:exercise.operating_band);
  const range=[...(chartBand||[]),...points.map(r=>r.value)];
  const min=Math.min(...(range.length?range:[0]))-.05,max=Math.max(...(range.length?range:[1]))+.1;
  const x=m=>20+(m-(rows[0]?.minute||0))/Math.max(1,(rows.at(-1)?.minute||0)-(rows[0]?.minute||0))*580;
  const y=v=>130-(v-min)/(max-min)*110;
  const state=value==null?'Measurement unavailable':goal?(value>goal[1]?'Above goal':value<goal[0]?'Below goal':'Within goal'):`Plant status: ${plant.safety_state}`;
  const proposed=decision?.proposal?.changes?.[exercise.target];
  const applied=decision?.applied?(decision.gate?.applied_values?.[exercise.target]??proposed):null;
  return <section className="water-demo-panel" aria-label="Live water objective">
    <div className="water-demo-heading"><div><span className="eyebrow">Water · minute {plant.elapsed_minutes} · {plant.running?'Running':'Paused'}</span><h2>{exercise.name}</h2></div><button onClick={onOpenHmi}>Open water HMI →</button></div>
    <div className="water-demo-metrics">
      <div><span>{exercise.measurement}</span><strong>{number(value)} <small>{exercise.unit}</small></strong><em>{state}</em></div>
      <div><span>{goal?'Exercise goal':'Plant status'}</span><strong>{goal?<>{goal.map(v=>v.toFixed(2)).join('–')} <small>{exercise.unit}</small></>:plant.safety_state}</strong><em>{goal?`Plant status: ${plant.safety_state}`:'Live protection state'}</em></div>
      <div><span>{exercise.target_label}</span><strong>{number(plc?.setpoints?.[exercise.target])} <small>{exercise.target_unit}</small></strong><em>{plc?.control_state?.setpoint_lease_expires?'AI control lease active':'Baseline / operator control'}</em></div>
    </div>
    {thresholds&&<div className="water-alarm-thresholds" aria-label="Chlorine alarm thresholds">
      <span className="warning">PLC yellow alarm <strong>≥ {thresholds.warning_high_mg_l.toFixed(2)} mg/L</strong></span>
      <span className="critical">PLC red alarm <strong>≥ {thresholds.critical_high_mg_l.toFixed(2)} mg/L</strong></span>
    </div>}
    {!goal&&<p className="water-objective-note">{exercise.note}</p>}
    <div className="water-demo-response">
      <div>{points.length<2?<p className="training-empty">Start monitoring to record the measured response.</p>:<><svg viewBox="0 0 620 158" role="img" aria-label={`${exercise.measurement} over simulated time${chartBand?`; shaded ${goal?'exercise goal':'reference range'}`:''}`}>
        {chartBand&&<rect x="20" y={y(chartBand[1])} width="580" height={y(chartBand[0])-y(chartBand[1])} fill="#244e42"/>}
        {chartBand?.map(v=><g key={v}><line x1="20" x2="600" y1={y(v)} y2={y(v)} stroke="#6fbe9b" strokeDasharray="4 5"/><text x="25" y={y(v)-5} fill="#b8dcca" fontSize="11">{v.toFixed(2)}</text></g>)}
        {rows.map((r,i)=>i>0&&Number.isFinite(r.value)&&Number.isFinite(rows[i-1].value)?<line key={r.minute} x1={x(rows[i-1].minute)} y1={y(rows[i-1].value)} x2={x(r.minute)} y2={y(r.value)} stroke="#f2c476" strokeWidth="2.5"/>:null)}
        <text x="20" y="154" fill="#a6bec6" fontSize="11">{rows[0]?.minute} min</text><text x="600" y="154" textAnchor="end" fill="#a6bec6" fontSize="11">{rows.at(-1)?.minute} min</text>
      </svg><small>Measured response{chartBand&&` · shaded ${goal?'exercise goal':'reference range'}`}.</small></>}</div>
      <dl><div><dt>Selected proposal</dt><dd>{!decision?'No analysis selected':proposed==null?'Hold · no target change':`${number(proposed)} ${exercise.target_unit}`}</dd></div><div><dt>Applied target</dt><dd>{applied==null?'None':`${number(applied)} ${exercise.target_unit}`}</dd></div><div role="status"><dt>Monitoring</dt><dd>{monitor.label}</dd><small>{monitor.detail}</small>{currentLoop&&<small> · {currentLoop.calls_used}/{currentLoop.max_calls} AI calls</small>}</div></dl>
    </div>
  </section>;
}
