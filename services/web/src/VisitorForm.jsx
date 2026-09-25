import React,{useEffect,useRef,useState} from 'react';
import industries from '../../../shared/visitor-industries.json';
export default function VisitorForm({onSaved,onClose}){
 const dialog=useRef(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{dialog.current.showModal();return()=>dialog.current?.close();},[]);
 async function submit(event,nameOnly=false){
  event.preventDefault();setBusy(true);setError('');
  const form=event.currentTarget.form||event.currentTarget;
  if(nameOnly&&!form.elements.name.reportValidity()){setBusy(false);return;}
  const data=new FormData(form);
  try{
   const response=await fetch('/api/visitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(nameOnly?{name:data.get('name'),mode:'name_only'}:{email:data.get('email'),name:data.get('name'),industry:data.get('industry'),contactConsent:data.get('contactConsent')==='on',mode:'full'})});
   const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not save your details.');
   onSaved();
  }catch(problem){setError(problem.message);}finally{setBusy(false);}
 }
 return <dialog ref={dialog} className="visitor-dialog" aria-labelledby="visitor-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
  <button className="visitor-close" aria-label="Close visitor form" onClick={onClose} disabled={busy}>×</button>
  <div className="visitor-intro"><span className="eyebrow">AIRGAP THE AI / OPEN LAB</span><h2 id="visitor-title">Meet the lab.<br/>Help shape what’s next.</h2><p>A little about you helps me understand who the lab is reaching.</p><p>With your permission, we may share new versions, ask for feedback or explore working together.</p><span className="visitor-note">Water · Nuclear · Power grid</span></div>
  <form onSubmit={event=>submit(event)} className="visitor-fields"><p className="visitor-required">Just your name to get started. Share more if you’d like.</p>
   <label htmlFor="visitor-name">Name<input id="visitor-name" name="name" autoComplete="name" maxLength={100} required placeholder="Your name" autoFocus/></label>
   <label htmlFor="visitor-email">Email<input id="visitor-email" name="email" type="email" autoComplete="email" maxLength={254} required placeholder="you@organisation.com"/></label>
   <label htmlFor="visitor-industry">Industry<select id="visitor-industry" name="industry" required defaultValue=""><option value="" disabled>Select your industry</option>{industries.map(value=><option key={value}>{value}</option>)}</select></label>
   <label className="visitor-consent"><input name="contactConsent" type="checkbox"/><span>I would like to be updated about new versions, feedback and potential collaboration. <small>Optional. You can withdraw by replying to any email.</small></span></label>
   <p className="visitor-privacy">Stored privately in Cloudflare by Nanzheng (Isaac) Xie. Your details are not shared with the AI model. For access or deletion requests, <a href="https://www.linkedin.com/in/nanzheng-xie" target="_blank" rel="noreferrer">contact Isaac ↗</a>.</p>
   {error&&<p className="visitor-error" role="alert">{error}</p>}
   <button className="visitor-submit" disabled={busy}>{busy?'Saving your details…':'Submit & enter lab'}<span aria-hidden="true">↗</span></button>
   <button type="button" className="visitor-skip" disabled={busy} onClick={event=>submit(event,true)}>Skip — enter with name <span aria-hidden="true">→</span></button>
  </form>
 </dialog>;
}
