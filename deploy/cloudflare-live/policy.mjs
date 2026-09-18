export const HOSTED_MODEL='@cf/qwen/qwen3-30b-a3b-fp8';
export const SESSION_MS=20*60*1000;
export async function forwardRequest(request){
  const url=new URL(request.url),headers=new Headers(request.headers);
  for(const name of [...headers.keys()]) if(name.startsWith('cf-container-')) headers.delete(name);
  headers.delete('host');
  const target=`http://lab.internal${url.pathname}${url.search}`;
  if(request.body){
    const reader=request.body.getReader();let bytes=0;const chunks=[];
    while(true){
      const {done,value}=await reader.read();if(done)break;bytes+=value.length;
      if(bytes>65536){await reader.cancel();return Response.json({detail:'Request too large'},{status:413});}
      chunks.push(value);
    }
    return new Request(target,{method:request.method,headers,body:new Blob(chunks)});
  }
  return new Request(target,{method:request.method,headers});
}
const fail=(status,detail)=>({ok:false,status,detail});
export const emptyLedger=now=>({day:Math.floor(now/86400000),created:0,aiCalls:0,sessions:{}});
function daily(ledger,now){
  const day=Math.floor(now/86400000);
  if(ledger.day!==day){ledger.day=day;ledger.created=0;ledger.aiCalls=0;}
}
export function admit(ledger,id,containerId,now){
  daily(ledger,now);
  if(ledger.created>=20) return fail(429,'Daily demo capacity reached. Please return tomorrow (UTC).');
  // Expired containers continue occupying capacity until cleanup confirms destruction.
  if(Object.keys(ledger.sessions).length>=3) return fail(429,'All three labs are in use. Please try again shortly.');
  const session={id,containerId,expires:now+SESSION_MS,aiCalls:0,lastAI:null,window:0,requests:0};
  ledger.sessions[id]=session;ledger.created++;
  return {ok:true,session};
}
export function authorize(ledger,id,now,count=false){
  const session=Object.hasOwn(ledger.sessions,id||'')?ledger.sessions[id]:null;
  if(!session||session.expires<=now) return fail(401,'Session ended. Start a new lab.');
  if(count){
    const window=Math.floor(now/60000);
    if(session.window!==window){session.window=window;session.requests=0;}
    if(session.requests>=180) return fail(429,'Please slow down and retry in a minute.');
    session.requests++;
  }
  return {ok:true,session};
}
export function consumeAI(ledger,containerId,now){
  daily(ledger,now);
  const session=Object.values(ledger.sessions).find(s=>s.containerId===containerId&&s.expires>now);
  if(!session) return fail(401,'No active inference session.');
  if(ledger.aiCalls>=200||session.aiCalls>=10) return fail(429,'AI allowance reached. Rule-based simulation remains available.');
  if(session.lastAI!==null&&now-session.lastAI<10000) return fail(429,'Wait ten seconds between AI calls.');
  // Reserve before invoking the model: failed calls still count toward spend limits.
  ledger.aiCalls++;session.aiCalls++;session.lastAI=now;
  return {ok:true,remaining:10-session.aiCalls};
}
export function modelRequest(body){
  if(!Array.isArray(body.messages)||body.messages.length<1||body.messages.length>10) throw new Error('Invalid messages');
  if(!body.format||typeof body.format!=='object') throw new Error('A proposal schema is required');
  if(new TextEncoder().encode(JSON.stringify(body)).length>50000) throw new Error('Context exceeds hosted limit');
  const messages=body.messages.map(m=>{
    if(!['system','user','assistant'].includes(m.role)||typeof m.content!=='string') throw new Error('Invalid message');
    return {role:m.role,content:m.content};
  });
  messages.push({role:'system',content:'Return only a JSON object matching this schema. /no_think\n'+JSON.stringify(body.format)});
  return {messages,stream:false,max_tokens:2048,temperature:0,seed:42,response_format:{type:'json_object'}};
}
export function modelResponse(body){
  const message=body.choices?.[0]?.message;
  let content=message?.content??body.response;
  if(content&&typeof content==='object') content=JSON.stringify(content);
  if(typeof content!=='string'||!content.trim()) throw new Error('Model returned no proposal');
  return {model:HOSTED_MODEL,provider:'cloudflare-workers-ai',execution_location:'cloud',done:true,
    message:{role:'assistant',content,thinking:message?.reasoning_content??''},
    prompt_eval_count:body.usage?.prompt_tokens,eval_count:body.usage?.completion_tokens};
}
