import React,{useEffect,useState} from 'react';

// Scripted illustration only: no model calls, session creation or actuation.
const frames=[
 {label:'Observe',level:38,pump:40,line:'Tank level falling',detail:'Level 38% · inlet pump 40%'},
 {label:'Propose',level:38,pump:40,line:'AI proposes an adjustment',detail:'{"inlet_pump_pct": 45}'},
 {label:'Check',level:38,pump:40,line:'Independent gate checks limits',detail:'Within bounds · proposal accepted'},
 {label:'Respond',level:42,pump:45,line:'Simulated response',detail:'Inlet pump 45% · level recovering'},
];
export default function VisitorPreview(){
 const [step,setStep]=useState(0),[playing,setPlaying]=useState(false);
 useEffect(()=>{const motion=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>{setPlaying(!motion.matches);setStep(motion.matches?3:0);};update();motion.addEventListener('change',update);return()=>motion.removeEventListener('change',update);},[]);
 useEffect(()=>{if(!playing)return;if(step===3){setPlaying(false);return;}const timer=setTimeout(()=>setStep(value=>value+1),2400);return()=>clearTimeout(timer);},[step,playing]);
 const frame=frames[step];
 return <section className="visitor-preview" aria-label="AI control sequence">
  <div className="preview-heading"><span>CONTROL SEQUENCE</span><span>Water / 01</span></div>
  <svg viewBox="0 0 340 156" role="img" aria-label={`Tank level ${frame.level} percent. Inlet pump ${frame.pump} percent.`}>
   <defs><pattern id="preview-water" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M0 12L12 0" stroke="#33845b" strokeOpacity=".2"/></pattern></defs>
   <path d="M14 92H114M228 112H322" fill="none" stroke="#759880" strokeWidth="3"/>
   <path d="M14 92H114" fill="none" stroke="#195b34" strokeWidth="3" strokeDasharray="5 8" className={playing?'preview-flow':''}/>
   <circle cx="61" cy="92" r="19" fill="#dff0df" stroke="#195b34" strokeWidth="2"/><path d="M54 82L71 92L54 102Z" fill="#195b34"/>
   <text x="61" y="138" textAnchor="middle">PUMP {frame.pump}%</text>
   <path d="M116 28V126Q116 132 122 132H220Q226 132 226 126V28" fill="none" stroke="#195b34" strokeWidth="2"/>
   <rect x="120" y={130-frame.level*1.8} width="102" height={frame.level*1.8} fill="#acd6b2" className="preview-water"/>
   <rect x="120" y={130-frame.level*1.8} width="102" height={frame.level*1.8} fill="url(#preview-water)"/>
   <text x="171" y="57" textAnchor="middle" className="preview-level">{frame.level}%</text>
   <path d="M265 102L285 122V102L265 122Z" fill="#dff0df" stroke="#195b34" strokeWidth="2"/>
   <text x="275" y="145" textAnchor="middle">OUTLET</text>
  </svg>
  <div className="preview-steps" role="group" aria-label="Control sequence steps">{frames.map((item,index)=><button key={item.label} type="button" aria-pressed={step===index} onClick={()=>{setPlaying(false);setStep(index);}}><span>0{index+1}</span>{item.label}</button>)}</div>
  <div className="preview-output"><strong>{frame.line}</strong><code>{frame.detail}</code></div>
  <div className="preview-footer"><span>Observe → Decide → Check → Respond</span><button type="button" onClick={()=>{if(playing)setPlaying(false);else{setStep(0);setPlaying(true);}}}>{playing?'Pause':'Replay'} <span aria-hidden="true">{playing?'Ⅱ':'↻'}</span></button></div>
 </section>;
}
