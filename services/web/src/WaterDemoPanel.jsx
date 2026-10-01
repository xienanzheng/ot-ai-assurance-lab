import React from 'react';

const number=value=>Number.isFinite(value)?value.toFixed(3):'—';
export default function WaterDemoPanel({plant,plc,loop,record,onOpenHmi}) {
  if(plant?.scenario!=='chlorine_efficiency_trim')return null;
  const sensor=plant.sensors?.chlorine_residual_mg_l;
  const age=(Date.parse(plant.simulation_time)-Date.parse(sensor?.timestamp))/1000;
  const trustworthy=sensor?.quality==='good'&&age>=0&&age<=120&&Number.isFinite(sensor?.value);
  const value=trustworthy?sensor.value:null;
  const sameRun=record?.before?.run_id===loop?.run_id&&record?.before?.plc?.controller_generation===plc?.controller_generation;
  const decision=sameRun?record:null;
  const currentLoop=loop?.controller_generation===plc?.controller_generation?loop:null;
  const rows=currentLoop?.objective_history||[];
  const points=rows.filter(r=>Number.isFinite(r.residual));
  const max=Math.max(1.2,...points.map(r=>r.residual));const min=Math.min(.8,...points.map(r=>r.residual));
  const x=m=>20+(m-(rows[0]?.minute||0))/Math.max(1,(rows.at(-1)?.minute||0)-(rows[0]?.minute||0))*580;
  const y=v=>130-(v-min)/(max-min)*110;
  const band=value==null?'Measurement unavailable':value>1?'Above objective':value<.9?'Below objective':'Inside objective band';
  const proposed=decision?.proposal?.changes?.chlorine_target_mg_l;
  const applied=decision?.applied?(decision.gate?.applied_values?.chlorine_target_mg_l??proposed):null;
  return <section className="water-demo-panel" aria-label="Live water objective">
    <div className="water-demo-heading"><div><span className="eyebrow">Live water run · minute {plant.elapsed_minutes}</span><h2>Watch the decision reach the process.</h2></div><button onClick={onOpenHmi}>Open water HMI →</button></div>
    <div className="water-demo-metrics">
      <div><span>Measured residual</span><strong>{number(value)} <small>mg/L</small></strong><em>{band}</em></div>
      <div><span>Exercise objective</span><strong>0.90–1.00 <small>mg/L</small></strong><em>Safety state: {plant.safety_state}</em></div>
      <div><span>Live PLC target</span><strong>{number(plc?.setpoints?.chlorine_target_mg_l)} <small>mg/L</small></strong><em>{plc?.control_state?.setpoint_lease_expires?'Bounded AI lease active':'Baseline / operator target'}</em></div>
    </div>
    <div className="water-demo-response">
      <div><svg viewBox="0 0 620 158" role="img" aria-label="Measured chlorine residual over simulated time; shaded objective band">
        <rect x="20" y={y(1)} width="580" height={y(.9)-y(1)} fill="#244e42"/>
        {[.9,1].map(v=><g key={v}><line x1="20" x2="600" y1={y(v)} y2={y(v)} stroke="#6fbe9b" strokeDasharray="4 5"/><text x="25" y={y(v)-5} fill="#b8dcca" fontSize="11">{v.toFixed(2)}</text></g>)}
        {rows.map((r,i)=>i>0&&Number.isFinite(r.residual)&&Number.isFinite(rows[i-1].residual)?<line key={r.minute} x1={x(rows[i-1].minute)} y1={y(rows[i-1].residual)} x2={x(r.minute)} y2={y(r.residual)} stroke="#f2c476" strokeWidth="2.5"/>:null)}
        <text x="20" y="154" fill="#a6bec6" fontSize="11">{rows[0]?.minute??plant.elapsed_minutes} min</text><text x="600" y="154" textAnchor="end" fill="#a6bec6" fontSize="11">{rows.at(-1)?.minute??plant.elapsed_minutes} min</text>
      </svg><small>Measured response · shaded objective band. A reading inside the band does not establish sustained recovery.</small></div>
      <dl><div><dt>Selected exchange proposal</dt><dd>{proposed==null?'No change':`${number(proposed)} mg/L`}</dd></div><div><dt>Applied in that exchange</dt><dd>{applied==null?'None':`${number(applied)} mg/L`}</dd></div><div><dt>Monitoring</dt><dd>{currentLoop?.status==='stopped'?'Stopped':currentLoop?.observation_only?'Read-only · no further actuation':currentLoop?.status||'Not started'}{currentLoop?.status!=='stopped'&&currentLoop?.next_review_minute!=null?` · review at minute ${currentLoop.next_review_minute}`:''}</dd></div></dl>
    </div>
  </section>;
}
