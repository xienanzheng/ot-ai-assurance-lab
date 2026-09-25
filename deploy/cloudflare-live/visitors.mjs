import industries from '../../shared/visitor-industries.json' with {type:'json'};
export const NOTICE_VERSION='2026-09-24-v2';
const json=(data,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const token=request=>request.headers.get('Cookie')?.match(/(?:^|;\s*)__Host-ot_visitor=([a-f0-9]{64})(?:;|$)/)?.[1];
const digest=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');
export function validateVisitor(value){
 if(!value||typeof value!=='object')throw new Error('Please complete the form.');
 const {email,name,industry,contactConsent}=value;
 if(typeof name!=='string'||!name.trim()||name.length>100||/[\x00-\x1f]/.test(name))throw new Error('Enter your name (up to 100 characters).');
 if(value.mode==='name_only')return {email:null,name:name.trim(),industry:null,contactConsent:false};
 if(typeof email!=='string'||email.length>254||! /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))throw new Error('Enter a valid email address.');
 if(!industries.includes(industry))throw new Error('Choose your industry.');
 if(typeof contactConsent!=='boolean')throw new Error('Invalid contact preference.');
 return {email:email.trim(),name:name.trim(),industry,contactConsent};
}
export async function registered(request,env){
 const access=token(request);if(!access)return false;
 return !!await env.VISITORS.prepare('SELECT 1 FROM visitors WHERE id = ? AND access_expires > ?').bind(await digest(access),Date.now()).first();
}
export async function visitors(request,env){
 try{
  if(request.method==='GET')return json({registered:await registered(request,env)});
  if(request.method!=='POST')return json({detail:'Method not allowed'},405);
  const {success}=await env.VISITOR_LIMIT.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'});
  if(!success)return json({detail:'Too many attempts. Please wait a minute and retry.'},429);
  if(!request.headers.get('Content-Type')?.includes('application/json'))return json({detail:'JSON required'},415);
  const reader=request.body?.getReader();if(!reader)return json({detail:'Please complete the form.'},400);
  let bytes=0,chunks=[];
  while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.length;if(bytes>4096){await reader.cancel();return json({detail:'Form is too large'},413);}chunks.push(value);}
  let value;
  try{value=validateVisitor(JSON.parse(await new Blob(chunks).text()));}catch(error){return json({detail:error instanceof SyntaxError?'Invalid form data.':error.message},400);}
  if(await registered(request,env))return json({registered:true});
  const access=Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
  const now=Date.now();
  await env.VISITORS.prepare('INSERT INTO visitors (id,email,name,industry,contact_consent,notice_version,created_at,access_expires) VALUES (?,?,?,?,?,?,?,?)').bind(await digest(access),value.email,value.name,value.industry,Number(value.contactConsent),NOTICE_VERSION,now,now+30*86400000).run();
  const response=json({registered:true},201);
  response.headers.set('Set-Cookie',`__Host-ot_visitor=${access}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=2592000`);
  return response;
 }catch{return json({detail:'We could not save your details. Please try again.'},503);}
}
