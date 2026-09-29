// Independent weather renderer under real Promise/fetch contracts, without a browser dependency.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('docs/weather.js','utf8');
const date=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const stamp=new Date().toISOString();
const good={schema:'mphi-weather-v1',source:'MET Norway · Locationforecast',current:{data_type:'model_forecast',temperature_c:25,valid_at:stamp,collected_at:stamp},forecast:{data_type:'model_forecast',collected_at:stamp,days:[{date,min_c:25,max_c:34,rain_probability_pct:0,precipitation_mm:0,condition:'<b>Fixture</b>'}]}};
const observed={schema:'mphi-weather-observation-v1',location:{station_id:'SBMN',station_name:'Ponta Pelada'},current:{data_type:'station_observation',temperature_c:30,condition:'<img src=x onerror=alert(1)>',humidity_pct:66,wind_kmh:9,observed_at:stamp,collected_at:stamp}};
const live={current:{time:stamp,temperature_2m:31.9,relative_humidity_2m:59,apparent_temperature:36.7,weather_code:1,wind_speed_10m:3.8,wind_direction_10m:183,surface_pressure:998.7}};
async function run(payload=good,state={state:'ok',checked_at:stamp},observation=observed,observationState={state:'ok'},failure=false,livePayload=live){
  const elements=new Map(),requests=[];let refresh;
  const document={hidden:false,addEventListener(){},getElementById(id){if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',dataset:{}});return elements.get(id);}};
  const ctx={document,Intl,Date,Number,String,Array,Promise,AbortController,setTimeout,clearTimeout,setInterval(fn){refresh=fn;},fetch:async(url,options)=>{requests.push({url,options});if(failure)throw new Error('offline');return {ok:true,json:async()=>url.includes('api.open-meteo.com')?livePayload:url.includes('observation_latest')?observation:url.includes('observation_status')?observationState:url.includes('weather_latest')?payload:state};}};
  vm.runInNewContext(code,ctx);await new Promise(r=>setImmediate(r));
  return {elements,requests,ctx,refresh};
}
test('observed 30 beats stale-looking modeled 25, with separate forecast and no-store',async()=>{
 const {elements:e,requests}=await run();assert.equal(e.get('weatherTemp').textContent,'30');assert.equal(e.get('weatherNowLabel').textContent,'Temperatura observada');assert.equal(e.get('weatherRain').textContent,'0 mm');assert.equal(e.get('weatherProbability').textContent,'0 %');assert.ok(e.get('weatherDays').innerHTML.includes('&lt;b&gt;Fixture&lt;/b&gt;'));assert.equal(requests.length,5);for(const r of requests){assert.equal(r.options.cache,'no-store');assert.ok(r.options.signal);}assert.match(requests.at(-1).url,/^https:\/\/api\.open-meteo\.com\/v1\/forecast\?/);
 assert.equal(e.get('weatherCondition').textContent,observed.current.condition);
});
test('missing station observation does not present a forecast as current temperature',async()=>{const {elements:e}=await run(good,{state:'ok'},null,{state:'unavailable'},false,null);assert.equal(e.get('weatherTemp').textContent,'—');assert.equal(e.get('weatherNowLabel').textContent,'Sem medição recente');});
test('old observation is explicitly labeled as last measurement when live fallback is unavailable',async()=>{const old=structuredClone(observed);old.current.observed_at='2020-01-01T00:00:00Z';const {elements:e}=await run(good,{state:'ok'},old,{state:'ok'},false,null);assert.equal(e.get('weatherStatus').dataset.state,'stale');assert.equal(e.get('weatherNowLabel').textContent,'Última medição disponível');});
test('live model estimate is used only as an explicit fallback when station data is old',async()=>{const old=structuredClone(observed);old.current.observed_at='2020-01-01T00:00:00Z';const {elements:e}=await run(good,{state:'ok'},old,{state:'ok'},false,live);assert.equal(e.get('weatherTemp').textContent,'31,9');assert.equal(e.get('weatherNowLabel').textContent,'Estimativa atual · modelo');assert.equal(e.get('weatherStatus').dataset.state,'partial');assert.match(e.get('weatherStatus').textContent,/Open-Meteo/);assert.match(e.get('weatherCredit').innerHTML,/modelo, não estação/);});
test('refresh failure preserves the last station temperature and labels failure',async()=>{const r=await run();r.ctx.fetch=async()=>{throw new Error('offline');};r.refresh();await new Promise(done=>setImmediate(done));assert.equal(r.elements.get('weatherTemp').textContent,'30');assert.match(r.elements.get('weatherStatus').textContent,/temporariamente indisponível/);});
test('model forecast fields remain forecast, with missing values visibly absent',async()=>{
 const modeled=structuredClone(good);modeled.forecast.issued_at=stamp;modeled.forecast.days[0].rain_probability_pct=null;
 const {elements:e}=await run(modeled);
 assert.equal(e.get('weatherProbability').textContent,'—');
 assert.equal(e.get('weatherFeels').textContent,'Sensação térmica: —');
 assert.match(e.get('weatherObserved').textContent,/Ponta Pelada/);
 assert.match(e.get('weatherCredit').innerHTML,/creativecommons.org\/licenses\/by\/4.0/);
 assert.equal(e.get('weatherRainLabel').textContent,'Chuva restante · hoje');
});
