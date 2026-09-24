export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405,headers:{Allow:'GET, HEAD'}});
  if(url.pathname==='/robots.txt')return new Response('User-agent: *\nAllow: /\nSitemap: https://securecritcticalinfra.dev/sitemap.xml\n',{headers:{'Content-Type':'text/plain'}});
  if(url.pathname==='/sitemap.xml')return new Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://securecritcticalinfra.dev/</loc></url></urlset>',{headers:{'Content-Type':'application/xml'}});
  if(url.pathname!=='/'&&url.pathname!=='/home.html'&&!url.pathname.startsWith('/assets/'))return new Response('Not found',{status:404});
  if(url.pathname==='/home.html')return Response.redirect(new URL('/',url),301);
  const asset=await env.ASSETS.fetch(url.pathname==='/'?new Request(new URL('/home.html',url),request):request);
  const response=new Response(asset.body,asset);
  response.headers.set('Content-Security-Policy',"default-src 'self'; script-src 'self' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://cloudflareinsights.com; frame-ancestors 'none'; object-src 'none'; base-uri 'self'");
  response.headers.set('X-Content-Type-Options','nosniff');
  response.headers.set('Referrer-Policy','strict-origin-when-cross-origin');
  return response;
 }
};
