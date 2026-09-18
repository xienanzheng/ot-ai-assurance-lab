import React,{useEffect,useState} from 'react';

export const HOSTED=import.meta.env.VITE_HOSTED==='true';
export const HOSTED_MODEL='@cf/qwen/qwen3-30b-a3b-fp8';
export default function HostedSession({children}){
  const [session,setSession]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{
    if(!HOSTED)return;
    fetch('/api/session').then(r=>r.json()).then(setSession).catch(()=>setError('Unable to check the session. Please retry.'));
    const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);
  },[]);
  if(!HOSTED)return children;
  const active=session?.active&&session.expires>now;
  async function start(){
    setBusy(true);setError('');
    try{
      const response=await fetch('/api/session',{method:'POST'}),data=await response.json();
      if(!response.ok)throw new Error(data.detail||'Unable to start lab');
      // Wait for a real healthy simulator before mounting polling and WebSockets.
      for(let attempt=0;attempt<20;attempt++){
        const ready=await fetch('/api/v1/state');
        if(ready.ok){setSession(data);return;}
        if(ready.status===401||ready.status===429)throw new Error((await ready.json()).detail);
        await new Promise(resolve=>setTimeout(resolve,3000));
      }
      throw new Error('Your lab is still starting. Please retry.');
    }catch(problem){setError(problem.message);}finally{setBusy(false);}
  }
  async function end(){
    try{const response=await fetch('/api/session',{method:'DELETE'});if(!response.ok)throw new Error('Could not end session');setSession({active:false});}
    catch(problem){setError(problem.message);}
  }
  return <>
    {active?<><aside className="hosted-ribbon"><strong>Public sandbox</strong><span>Cloud AI · Qwen3 30B-A3B · {Math.ceil((session.expires-now)/60000)} min left</span><span>Temporary session · Export before leaving</span><button onClick={end}>End session</button></aside>{error&&<p role="alert">{error}</p>}{children}</>:
      <main className="hosted-entry"><span className="eyebrow">OT / AI assurance lab</span><h1>Your own control room.</h1><p>Water. Nuclear. Power grid.</p><p>Run a scenario, change controls and inspect AI decisions.</p><div className="hosted-details"><span>20-minute session</span><span>10 AI calls</span><span>Isolated simulation</span></div><button className="primary" onClick={start} disabled={busy}>{busy?'Preparing your lab…':'Start a simulation'}</button><a href="/research.html">Explore recorded findings ↗</a>{error&&<p role="alert">{error}</p>}<p className="hosted-note">Synthetic plants only. Cloudflare hosts the simulation and model API. This online session is not air-gapped. Sessions expire; export your results to keep them.</p></main>}
  </>;
}
