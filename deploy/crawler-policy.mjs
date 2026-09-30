// Site-scoped, self-identified crawler blocking. This is NOT Cloudflare's
// managed bot detection: a scraper can evade it by changing its User-Agent.
// Source: https://developers.cloudflare.com/ai-crawl-control/reference/bots/
const AI_AGENTS = [
 'GPTBot','ChatGPT-User','OAI-SearchBot','ClaudeBot','Claude-SearchBot',
 'Claude-User','PerplexityBot','Perplexity-User','Google-CloudVertexBot',
 'Bytespider','CCBot','meta-externalagent','meta-externalfetcher','FacebookBot',
 'Amazonbot','DuckAssistBot','MistralAI-User',
];
// These opt-out tokens do not identify separate HTTP crawlers. They preserve
// ordinary Google/Apple search crawling while expressing AI-use preferences.
const ROBOTS_AGENTS = [...AI_AGENTS,'Google-Extended','Applebot-Extended'];
const aiAgent = new RegExp(`(?:^|[^a-z0-9_-])(?:${AI_AGENTS.join('|')})(?=$|[^a-z0-9_-])`,'i');
const HOME='securecritcticalinfra.dev';
const LAB='ot-aigent-simulation.night-zone.com';

export function crawlerResponse(request){
 const url=new URL(request.url);
 if(![HOME,LAB].includes(url.hostname))return null;
 if(url.pathname==='/robots.txt'){
  if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405,headers:{Allow:'GET, HEAD'}});
  const general=url.hostname===HOME
   ? 'User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://securecritcticalinfra.dev/sitemap.xml\n'
   : 'User-agent: *\nDisallow: /\n';
  const body=general+'\n'+ROBOTS_AGENTS.map(agent=>`User-agent: ${agent}\nDisallow: /\n`).join('\n');
  return new Response(request.method==='HEAD'?null:body,{headers:{
   'Content-Type':'text/plain; charset=utf-8','Cache-Control':'public, max-age=3600','X-Content-Type-Options':'nosniff',
  }});
 }
 if(aiAgent.test(request.headers.get('User-Agent')||''))return new Response(request.method==='HEAD'?null:'Automated AI collection is not permitted.',{status:403,headers:{
  'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','Vary':'User-Agent','X-Content-Type-Options':'nosniff',
 }});
 return null;
}
