// Independent weather renderer under real Promise/fetch contracts, without a browser dependency.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('docs/weather.js','utf8');
const date=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const stamp=new Date().toISOString();
const good={schema:'mphi-weather-v1',current:{temperature_c:29,condition:'<img src=x onerror=alert(1)>',humidity_pct:80,wind_kmh:8,collected_at:stamp,observed_at:stamp},forecast:{collected_at:stamp,days:[{date,min_c:25,max_c:34,rain_probability_pct:0,precipitation_mm:0,condition:'<b>Fixture</b>'}]}};
async function run(payload=good,state={state:'ok',checked_at:stamp},failure=false){
  const elements=new Map(),requests=[];let refresh;
  const document={hidden:false,addEventListener(){},getElementById(id){if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',dataset:{}});return elements.get(id);}};
  const ctx={document,Intl,Date,Number,String,Array,Promise,AbortController,setTimeout,clearTimeout,setInterval(fn){refresh=fn;},fetch:async(url,options)=>{requests.push({url,options});if(failure)throw new Error('offline');return {ok:true,json:async()=>url.includes('weather_latest')?payload:state};}};
  vm.runInNewContext(code,ctx);await new Promise(r=>setImmediate(r));
  return {elements,requests,ctx,refresh};
}
test('valid fixture renders zero, escapes markup, requests no-store and no provider',async()=>{
 const {elements:e,requests}=await run();assert.equal(e.get('weatherTemp').textContent,'29');assert.equal(e.get('weatherRain').textContent,'0 mm');assert.equal(e.get('weatherProbability').textContent,'0 %');assert.ok(e.get('weatherDays').innerHTML.includes('&lt;b&gt;Fixture&lt;/b&gt;'));assert.equal(requests.length,2);for(const r of requests){assert.equal(r.options.cache,'no-store');assert.match(r.url,/^data\/weather_/);assert.ok(r.options.signal);}
});
test('network failure isolated with an honest message',async()=>{const {elements:e}=await run(good,{},true);assert.match(e.get('weatherStatus').textContent,/temporariamente indisponíveis/);});
test('missing credential displays no invented temperatures',async()=>{const {elements:e}=await run({schema:'mphi-weather-v1',current:null,forecast:null},{state:'not_configured'});assert.equal(e.get('weatherTemp').textContent,'—');assert.match(e.get('weatherStatus').textContent,/aguardando ativação/);});
test('malformed weather schema remains isolated',async()=>{const {elements:e}=await run({unexpected:true});assert.match(e.get('weatherStatus').textContent,/temporariamente indisponíveis/);});
test('old observation never claims current weather',async()=>{const old=structuredClone(good);old.current.observed_at='2020-01-01T00:00:00Z';const {elements:e}=await run(old);assert.equal(e.get('weatherStatus').dataset.state,'stale');assert.equal(e.get('weatherNowLabel').textContent,'Última condição disponível');});
test('refresh failure preserves previously displayed valid temperature',async()=>{const r=await run();r.ctx.fetch=async()=>{throw new Error('offline');};r.refresh();await new Promise(done=>setImmediate(done));assert.equal(r.elements.get('weatherTemp').textContent,'29');assert.match(r.elements.get('weatherStatus').textContent,/temporariamente indisponíveis/);});
