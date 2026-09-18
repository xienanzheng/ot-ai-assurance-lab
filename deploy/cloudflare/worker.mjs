// Public recorded demo only. No live API, model credentials, or origin binding.
export default {
  async fetch(request, env) {
    const url=new URL(request.url);
    let path;
    try { path=decodeURIComponent(url.pathname); } catch { return new Response('Invalid path',{status:400}); }
    if(path==='/api'||path.startsWith('/api/')) return Response.json({code:'recorded_demo_only',detail:'Recorded research evidence only. Download the repository to run local simulations.'},{status:503});
    if(!['GET','HEAD'].includes(request.method)) return new Response('Read-only demo',{status:405,headers:{Allow:'GET, HEAD'}});
    if(path==='/'||path==='/index.html') return Response.redirect(new URL('/research.html',url).href,302);
    if(!(path==='/research.html'||['/assets/','/fonts/','/research/'].some(prefix=>path.startsWith(prefix)))) return new Response('Not found',{status:404});
    const asset=await env.ASSETS.fetch(request);
    const response=new Response(asset.body,asset);
    response.headers.set('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'");
    response.headers.set('X-Content-Type-Options','nosniff');
    response.headers.set('Referrer-Policy','no-referrer');
    response.headers.set('X-OT-Demo','recorded-only');
    return response;
  }
};
