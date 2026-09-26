import { visitors, registered } from './visitors.mjs';
import { Container, ContainerProxy } from '@cloudflare/containers';
import { DurableObject } from 'cloudflare:workers';
import { admit, authorize, consumeAI, emptyLedger, HOSTED_MODEL, jevRequest, modelRequest, modelResponse, forwardRequest } from './policy.mjs';
export { ContainerProxy };

const json=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store'}});
const registry=env=>env.SESSIONS.getByName('admissions');
const cookie=request=>request.headers.get('Cookie')?.match(/(?:^|;\s*)__Host-ot_session=([a-f0-9-]{36})(?:;|$)/)?.[1];

export class LabContainer extends Container {
  defaultPort=8080;
  sleepAfter='5m';
  enableInternet=false;
  allowedHosts=['inference.lab'];
  envVars={OLLAMA_BASE_URL:'http://inference.lab',OLLAMA_MODEL:HOSTED_MODEL,HOSTED_MODE:'true',LESSON_MEMORY_ENABLED:'false'};
  async fetch(request){
    // Python scientific imports and OPC UA startup exceed the SDK's short default.
    await this.startAndWaitForPorts({ports:[8080],cancellationOptions:{instanceGetTimeoutMS:90000,portReadyTimeoutMS:90000}});
    return super.fetch(request);
  }
}
LabContainer.outboundByHost={
  'inference.lab':async(request,env,ctx)=>{
    const path=new URL(request.url).pathname;
    // Report what the account can actually call. A hardcoded list here made the readiness
    // indicator unfalsifiable: a stale model id or missing quota still showed "model ready".
    if(path==='/api/tags'&&request.method==='GET'){
      const ready=await registry(env).modelReady();
      return json({models:ready?[{name:HOSTED_MODEL,model:HOSTED_MODEL,provider:'cloudflare-workers-ai',execution_location:'cloud'}]:[]});
    }
    if(path==='/api/providers'&&request.method==='GET') return json({jev:!!env.OPENROUTER_API_KEY});
    if(!['/api/chat','/api/decisions'].includes(path)||request.method!=='POST') return json({error:'Unsupported inference route'},404);
    try{
      const raw=await request.text();
      if(raw.length>50000) return json({error:'Context exceeds hosted limit'},413);
      const jev=path==='/api/decisions';
      if(jev&&!env.OPENROUTER_API_KEY) return json({error:'Jev is not configured'},503);
      const input=jev?jevRequest(JSON.parse(raw)):modelRequest(JSON.parse(raw));
      const allowance=await registry(env).reserveAI(ctx.containerId);
      if(!allowance.ok) return json({error:allowance.detail},allowance.status);
      if(jev){
        const upstream=await fetch('https://openrouter.ai/api/alpha/decisions',{
          method:'POST',headers:{Authorization:`Bearer ${env.OPENROUTER_API_KEY}`,'Content-Type':'application/json','X-Title':'OT AI Assurance Lab'},
          body:JSON.stringify(input),signal:AbortSignal.timeout(40000),redirect:'manual'
        });
        if(!upstream.ok) return json({error:'Jev provider unavailable'},502);
        const result=await upstream.json();
        return json({model:result.model,answers:result.answers,usage:result.usage});
      }
      const output=await env.AI.run(HOSTED_MODEL,input);
      return json(modelResponse(output));
    }catch(error){console.error('Hosted inference failed',error?.name);return json({error:'Hosted inference failed; baseline retains control'},502);}
  }
};

export class SessionRegistry extends DurableObject {
  async mutate(fn){
    // Serialize reservations and persist before returning permission to spend.
    return this.ctx.blockConcurrencyWhile(async()=>{
      const ledger=await this.ctx.storage.get('ledger')||emptyLedger(Date.now());
      const result=fn(ledger);
      await this.ctx.storage.put('ledger',ledger);
      return result;
    });
  }
  async create(){
    const id=crypto.randomUUID(),containerId=this.env.LABS.idFromName(id).toString();
    const result=await this.mutate(ledger=>admit(ledger,id,containerId,Date.now()));
    if(result.ok&&await this.ctx.storage.getAlarm()===null) await this.ctx.storage.setAlarm(Date.now()+60000);
    return result;
  }
  async check(id,count=false){return this.mutate(ledger=>authorize(ledger,id,Date.now(),count));}
  async modelReady(){
    // One cheap probe, cached, and deliberately outside the visitor's AI allowance.
    const cached=await this.ctx.storage.get('modelProbe');
    if(cached&&cached.expires>Date.now()) return cached.ok;
    let ok=false;
    try{ok=!!await this.env.AI.run(HOSTED_MODEL,{messages:[{role:'user',content:'ok'}],max_tokens:4});}
    catch(error){console.error('Model probe failed',error?.name);}
    // Hold a success for an hour; retry a failure soon so a fixed binding recovers quickly.
    await this.ctx.storage.put('modelProbe',{ok,expires:Date.now()+(ok?3600000:120000)});
    return ok;
  }
  async reserveAI(containerId){return this.mutate(ledger=>consumeAI(ledger,containerId,Date.now()));}
  async end(id){
    const result=await this.mutate(ledger=>{
      if(!Object.hasOwn(ledger.sessions,id)) return {ok:false};
      ledger.sessions[id].expires=0;return {ok:true};
    });
    if(result.ok) await this.ctx.storage.setAlarm(Date.now()+1);
    return result;
  }
  async alarm(){
    const ledger=await this.ctx.storage.get('ledger');
    for(const session of Object.values(ledger?.sessions||{})){
      if(session.expires>Date.now()) continue;
      try{
        await this.env.LABS.getByName(session.id).destroy();
        await this.mutate(current=>{delete current.sessions[session.id];return {ok:true};});
      }catch{console.error('Session cleanup will retry');}
    }
    const current=await this.ctx.storage.get('ledger');
    if(Object.keys(current?.sessions||{}).length) await this.ctx.storage.setAlarm(Date.now()+60000);
  }
}

export default {
  async fetch(request,env){
    const url=new URL(request.url),path=url.pathname;
    const write=!['GET','HEAD'].includes(request.method);
    if((write||request.headers.get('Upgrade')==='websocket')&&request.headers.get('Origin')!==url.origin) return json({detail:'Same-origin request required'},403);
    if(path==='/api/visitors') return visitors(request,env);
    if(path==='/api/session'){
      const id=cookie(request);
      if(request.method==='GET'){
        const result=await registry(env).check(id);
        return json(result.ok?{active:true,expires:result.session.expires,ai_remaining:10-result.session.aiCalls,model:HOSTED_MODEL}:{active:false});
      }
      if(request.method==='DELETE'){if(id) await registry(env).end(id);return json({active:false});}
      if(request.method!=='POST') return json({detail:'Method not allowed'},405);
      try{if(!await registered(request,env))return json({detail:'Please complete the visitor form before starting.',registration_required:true},403);}
      catch{return json({detail:'Registration is temporarily unavailable. Please retry.'},503);}
      const existing=await registry(env).check(id);
      const result=existing.ok?existing:await registry(env).create();
      if(!result.ok) return json({detail:result.detail},result.status);
      const response=json({active:true,expires:result.session.expires,model:HOSTED_MODEL});
      response.headers.set('Set-Cookie',`__Host-ot_session=${result.session.id}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=1200`);
      return response;
    }
    if(path.startsWith('/api/')){
      if(!path.startsWith('/api/v1/')) return json({detail:'Unknown API'},404);
      const result=await registry(env).check(cookie(request),true);
      if(!result.ok) return json({detail:result.detail},result.status);
      // Batch studies and lab-service administration are local-only.
      if(/\/study$/.test(path)) return json({detail:'Run batch research studies in the local lab.'},403);
      const forwarded=await forwardRequest(request);
      if(forwarded instanceof Response) return forwarded;
      try{
        const response=await env.LABS.getByName(result.session.id).fetch(forwarded);
        if(response.status===101) return response;
        const safe=new Response(response.body,response);safe.headers.set('Cache-Control','no-store');return safe;
      }catch{return json({detail:'Your lab is starting. Retry shortly.'},503);}
    }
    if(write) return json({detail:'Method not allowed'},405);
    const allowed=path==='/'||path==='/index.html'||path==='/research.html'||['/assets/','/fonts/','/research/'].some(p=>path.startsWith(p));
    if(!allowed) return new Response('Not found',{status:404});
    const assetRequest=path==='/'?new Request(new URL('/index.html',url),request):request;
    const asset=await env.ASSETS.fetch(assetRequest);
    const response=new Response(asset.body,asset);
    response.headers.set('Content-Security-Policy',`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' wss://${url.host}; frame-ancestors 'none'; object-src 'none'; base-uri 'self'`);
    response.headers.set('X-Content-Type-Options','nosniff');
    response.headers.set('Referrer-Policy','no-referrer');
    return response;
  }
};
