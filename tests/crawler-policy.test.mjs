import test from 'node:test';
import assert from 'node:assert/strict';
import { crawlerResponse } from '../deploy/crawler-policy.mjs';
import home from '../deploy/cloudflare-home/worker.mjs';

const homepage='https://securecritcticalinfra.dev';
const lab='https://ot-aigent-simulation.night-zone.com';
const request=(origin,path,ua,method='GET')=>new Request(origin+path,{method,headers:{'User-Agent':ua}});

test('known AI crawlers are denied on pages and APIs before any paid work',()=>{
 for(const origin of [homepage,lab])for(const path of ['/','/assets/app.js','/api/session','/api/v1/agents/water/cycle']){
  for(const ua of ['Mozilla/5.0 (compatible; GPTBot/1.2)','claudebot/1.0','PerplexityBot','OAI-SearchBot/1.0','CCBot/2.0']){
   const result=crawlerResponse(request(origin,path,ua,path.startsWith('/api/')?'POST':'GET'));
   assert.equal(result.status,403);
   assert.equal(result.headers.get('Cache-Control'),'no-store');
  }
 }
});

test('human browsers and ordinary search engines are unaffected',()=>{
 for(const ua of ['Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36','Googlebot/2.1','bingbot/2.0','DuckDuckBot/1.1','Applebot/0.1','', 'NotGPTBot']){
  assert.equal(crawlerResponse(request(homepage,'/',ua)),null);
  assert.equal(crawlerResponse(request(lab,'/api/session',ua,'POST')),null);
 }
 assert.equal(crawlerResponse(new Request(homepage,{headers:{Referer:'https://chatgpt.com/'}})),null);
});

test('policy never affects other night-zone services',()=>{
 assert.equal(crawlerResponse(request('https://night-zone.com','/','GPTBot')),null);
 assert.equal(crawlerResponse(request('https://another.night-zone.com','/robots.txt','GPTBot')),null);
});

test('robots is readable by blocked crawlers, with distinct homepage and lab policies',async()=>{
 for(const origin of [homepage,lab]){
  const result=crawlerResponse(request(origin,'/robots.txt','GPTBot'));
  assert.equal(result.status,200);
  assert.match(result.headers.get('Content-Type'),/^text\/plain/);
  const text=await result.text();
  assert.match(text,/User-agent: GPTBot\nDisallow: \//);
  assert.match(text,/User-agent: Google-Extended\nDisallow: \//);
  assert.match(text,/User-agent: Applebot-Extended\nDisallow: \//);
  assert.match(text,origin===homepage?/User-agent: \*\nAllow: \//:/User-agent: \*\nDisallow: \//);
  assert.equal(await crawlerResponse(request(origin,'/robots.txt','GPTBot','HEAD')).text(),'');
  assert.equal(crawlerResponse(request(origin,'/robots.txt','GPTBot','POST')).status,405);
 }
});

test('homepage integration blocks crawlers without fetching assets; normal page still works',async()=>{
 const env={ASSETS:{fetch:async()=>new Response('home page')}};
 assert.equal((await home.fetch(request(homepage,'/','GPTBot'),{})).status,403);
 assert.equal(await (await home.fetch(request(homepage,'/','Mozilla/5.0'),env)).text(),'home page');
 assert.match(await (await home.fetch(request(homepage,'/robots.txt','Googlebot'),{})).text(),/Sitemap: https:\/\/securecritcticalinfra.dev\/sitemap.xml/);
});
