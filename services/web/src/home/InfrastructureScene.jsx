import React from 'react';

function Block({x,y,w=44,d=24,h=70,tone='city'}){
 return <g className={`iso-block ${tone}`} transform={`translate(${x} ${y})`}>
  <path className="block-side" d={`M0 0 l${w} ${w/2} v${-h} l${-w} ${-w/2}z`}/>
  <path className="block-front" d={`M${w} ${w/2} l${d} ${-d/2} v${-h} l${-d} ${d/2}z`}/>
  <path className="block-roof" d={`M0 ${-h} l${d} ${-d/2} l${w} ${w/2} l${-d} ${d/2}z`}/>
  {[...Array(Math.floor(h/17))].map((_,i)=><path key={i} className="window-line" d={`M8 ${-h+15+i*17} l${w-16} ${(w-16)/2}`} />)}
 </g>;
}
function Tank({x,y}){return <g transform={`translate(${x} ${y})`} className="tank"><path d="M-27 -34v34c0 18 54 18 54 0v-34"/><ellipse cy="-34" rx="27" ry="13"/><ellipse className="tank-water" cy="-34" rx="20" ry="8"/><path d="M-27 -8c0 17 54 17 54 0"/></g>;}
function Pylon({x,y}){return <g className="pylon" transform={`translate(${x} ${y})`}><path d="M-20 0L-5-92H5L20 0M-15-20L12-44-9-65H9L-12-44 15-20ZM-34-65H34M-26-82H26M-34-65V-56M34-65V-56M-26-82V-73M26-82V-73"/></g>;}
export default function InfrastructureScene({sector}){
 return <svg className={`infrastructure-art active-${sector}`} viewBox="0 0 680 500" role="img" aria-label={`Illustrated ${sector} infrastructure connected to a city through an independent AI control gate`}>
  <defs><pattern id="isogrid" width="80" height="40" patternUnits="userSpaceOnUse"><path d="M0 0L80 40M0 40L80 0" fill="none" stroke="currentColor" strokeWidth=".6"/></pattern></defs>
  <ellipse className="island-shadow" cx="350" cy="403" rx="267" ry="61"/>
  <path className="island-edge" d="M39 265L303 127 644 301V319L381 458 39 283Z"/>
  <path className="island-top" d="M39 265L303 127 644 301 381 440Z"/>
  <path fill="url(#isogrid)" className="island-grid" d="M39 265L303 127 644 301 381 440Z"/>
  <path className="road" d="M88 286L305 171 570 306M200 338L413 224M309 388L519 278"/>
  <path className="road-centre" d="M88 286L305 171 570 306M200 338L413 224M309 388L519 278"/>
  <g className="sector-area water-area">
   <path className="sector-pad" d="M94 254L207 195 287 236 175 295Z"/>
   <Tank x={151} y={242}/><Tank x={213} y={215}/>
   <path className="pipe" d="M151 257V269L209 300 250 278"/>
   <Block x={205} y={276} w={42} d={31} h={34} tone="plant"/>
  </g>
  <g className="sector-area nuclear-area">
   <path className="sector-pad" d="M296 211L362 176 457 224 391 260Z"/>
   <g className="reactor" transform="translate(354 210)"><path d="M-25 0V-45a25 25 0 0 1 50 0V0c0 17-50 17-50 0Z"/><path d="M-25-9c0 17 50 17 50 0M-25-22c0 17 50 17 50 0"/></g>
   <Block x={386} y={237} w={39} d={29} h={40} tone="plant"/>
  </g>
  <g className="sector-area grid-area">
   <path className="sector-pad" d="M430 290L493 257 571 295 508 330Z"/>
   <Pylon x={477} y={287}/><Pylon x={552} y={318}/>
   <path className="power-wire" d="M451 205Q493 246 526 236M503 205Q540 239 578 236"/>
  </g>
  <g className="city-area">
   <Block x={279} y={328} w={37} d={28} h={84}/>
   <Block x={330} y={302} w={31} d={25} h={53}/>
   <Block x={326} y={373} w={49} d={31} h={100}/>
   <Block x={392} y={346} w={36} d={30} h={64}/>
   <Block x={418} y={388} w={42} d={25} h={48}/>
  </g>
  <g className="trees">{[[96,278],[266,357],[489,345],[458,406],[301,202],[578,323]].map(([x,y],i)=><g key={i} transform={`translate(${x} ${y})`}><path d="M0 0v-15"/><path d="M-10-14 0-39 10-14Z"/></g>)}</g>
  <path className="signal-route water-route" d="M151 222V133L290 62H411"/>
  <path className="signal-route nuclear-route" d="M355 157V112L411 83"/>
  <path className="signal-route grid-route" d="M552 225V167L484 130V83"/>
  <g className="gate-badge" transform="translate(400 39)"><rect width="147" height="49" rx="5"/><path d="M17 16h7v18h-7M37 16h-7v18h7"/><text x="49" y="23">CONTROL GATE</text><text className="gate-small" x="49" y="37">Human authority</text></g>
  <g className="scene-coordinate"><path d="M52 385v23h42M624 203v-23h-42"/><text x="55" y="427">A connected city.</text><text x="55" y="446">A clear boundary.</text></g>
 </svg>;
}
