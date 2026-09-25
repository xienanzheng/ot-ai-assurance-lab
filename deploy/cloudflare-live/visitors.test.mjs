import test from 'node:test';
import assert from 'node:assert/strict';
import {validateVisitor,visitors,registered} from './visitors.mjs';
const input={email:' visitor@example.com ',name:' Visitor ',industry:'Academia & research',contactConsent:false};
test('normalizes required fields and preserves declined contact consent',()=>{assert.deepEqual(validateVisitor(input),{...input,email:'visitor@example.com',name:'Visitor'});});
test('rejects invalid input, unsupported industries and implicit consent',()=>{for(const value of [null,{}, {...input,email:'invalid'}, {...input,name:' '},{...input,industry:'invented'},{...input,contactConsent:'false'}])assert.throws(()=>validateVisitor(value));});
test('stores contact separately and issues a validated opaque receipt',async()=>{
 const rows=new Map();let saved;
 const env={VISITOR_LIMIT:{limit:async()=>({success:true})},VISITORS:{prepare(sql){return{bind(...args){return{run:async()=>{saved=args;rows.set(args[0],args);},first:async()=>rows.has(args[0])&&rows.get(args[0])[7]>Date.now()?{'1':1}:null};}}}}};
 const response=await visitors(new Request('https://test/api/visitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)}),env);
 assert.equal(response.status,201);assert.equal(saved[4],0);assert.equal(saved[1],'visitor@example.com');
 const cookie=response.headers.get('Set-Cookie');assert.match(cookie,/HttpOnly; SameSite=Strict/);assert.ok(!cookie.includes(input.email.trim()));
 assert.equal(await registered(new Request('https://test',{headers:{Cookie:cookie}}),env),true);
 assert.equal(await registered(new Request('https://test',{headers:{Cookie:'__Host-ot_visitor='+'a'.repeat(64)}}),env),false);
 assert.equal((await visitors(new Request('https://test/api/visitors'),env)).status,200);
 assert.equal((await visitors(new Request('https://test/api/visitors',{method:'PUT'}),env)).status,405);
});
test('limits abuse and fails closed if storage unavailable',async()=>{
 const request=()=>new Request('https://test/api/visitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});
 assert.equal((await visitors(request(),{VISITOR_LIMIT:{limit:async()=>({success:false})}})).status,429);
 assert.equal((await visitors(request(),{VISITOR_LIMIT:{limit:async()=>({success:true})}})).status,503);
});
test('legacy name-only requests cannot bypass required contact fields',()=>{
 assert.throws(()=>validateVisitor({mode:'name_only',name:'Alex'}));
 assert.throws(()=>validateVisitor({...input,mode:'name_only',email:null}));
 assert.throws(()=>validateVisitor({...input,mode:'name_only',industry:null}));
});
