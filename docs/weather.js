/* Independent weather context: no access to MPHI model, score or projections. */
(()=>{
  'use strict';
  const el=id=>document.getElementById(id);
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const value=(n,unit='',digits=0)=>typeof n==='number'&&Number.isFinite(n)?n.toLocaleString('pt-BR',{maximumFractionDigits:digits})+unit:'—';
  const time=s=>s&&Number.isFinite(Date.parse(s))?new Date(s).toLocaleString('pt-BR',{timeZone:'America/Manaus',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' (Manaus)':'não disponível';
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const LIVE_URL='https://api.open-meteo.com/v1/forecast?latitude=-3.146&longitude=-59.986&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure&timezone=UTC';
  const liveCondition=code=>({0:'Céu limpo',1:'Predominantemente limpo',2:'Parcialmente nublado',3:'Nublado',45:'Neblina',48:'Neblina',51:'Garoa',53:'Garoa',55:'Garoa',56:'Garoa congelante',57:'Garoa congelante',61:'Chuva fraca',63:'Chuva',65:'Chuva forte',66:'Chuva congelante',67:'Chuva congelante',71:'Neve',73:'Neve',75:'Neve forte',77:'Granizo',80:'Pancadas fracas',81:'Pancadas',82:'Pancadas fortes',85:'Pancadas de neve',86:'Pancadas de neve',95:'Trovoadas',96:'Trovoadas com granizo',99:'Trovoadas com granizo'})[code]||'Condição não informada';
  const liveDirection=degrees=>typeof degrees==='number'&&Number.isFinite(degrees)?['N','NE','L','SE','S','SO','O','NO'][Math.round(degrees/45)%8]:'—';
  const normalizeLive=payload=>{
    const c=payload?.current,t=typeof c?.time==='string'?(/[zZ]|[+-]\d\d:?\d\d$/.test(c.time)?c.time:c.time+'Z'):null;
    if(!t||!Number.isFinite(Date.parse(t))||!Number.isFinite(c?.temperature_2m)||age(t)>1.5||age(t)<-.25)return null;
    return {data_type:'model_current',observed_at:t,collected_at:new Date().toISOString(),temperature_c:c.temperature_2m,feels_like_c:c.apparent_temperature,condition:liveCondition(c.weather_code),humidity_pct:c.relative_humidity_2m,wind_kmh:c.wind_speed_10m,wind_direction:liveDirection(c.wind_direction_10m),pressure_hpa:c.surface_pressure};
  };
  const icon=condition=>{
    const s=(condition||'').toLowerCase();
    const cloud='<path d="M7 28h23a7 7 0 0 0 0-14 10 10 0 0 0-19-2 8 8 0 0 0-4 16Z"/>';
    const sun='<circle cx="20" cy="19" r="7"/><path d="M20 5V2m0 34v-3M6 19H3m34 0h-3M10 9 8 7m24 24-2-2M30 9l2-2M10 29l-2 2"/>';
    const rain='<path d="m12 32-2 4m11-4-2 4m11-4-2 4"/>';
    const drawing=/trovo|tempest|raio/.test(s)?cloud+'<path d="m21 25-5 7h6l-4 7"/>':/chuva|pancada|garoa/.test(s)?cloud+rain:/sol|limpo/.test(s)?sun:cloud;
    return '<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+drawing+'</svg>';
  };
  let snapshot=null,status=null,observation=null,observationStatus=null,live=null,busy=false,failed=false,observationFailed=false,liveFailed=false;
  const age=s=>s&&Number.isFinite(Date.parse(s))?(Date.now()-Date.parse(s))/36e5:Infinity;
  function render(){
    const c=observation?.current,f=snapshot?.forecast,day=today();
    const limit=status?.stale_after_hours||12;
    const observationOld=!c||age(c.observed_at)>(observationStatus?.stale_after_hours||2)||age(c.observed_at)<-.25;
    const liveCurrent=live?.current||null;
    const liveMode=Boolean(liveCurrent&&observationOld);
    const shown=liveMode?liveCurrent:c;
    const forecastOld=f&&(age(f.collected_at)>limit||age(status?.checked_at)>limit);
    let state=failed?'unavailable':status?.state||'unavailable';
    if(forecastOld&&state==='ok')state='stale';
    const station=observation?.location?.station_name||'Manaus';
    const stationProblem=observationFailed||observationStatus?.state!=='ok'||observationOld;
    if(liveMode){
      el('weatherStatus').textContent='Estimativa atual modelada · Open-Meteo · '+time(liveCurrent.observed_at)+' · última medição de '+station+' preservada';
    }else if(!c){
      el('weatherStatus').textContent='Medição em estação temporariamente indisponível. A previsão dos próximos dias permanece separada.';
    }else if(stationProblem){
      el('weatherStatus').textContent='Medição em estação temporariamente indisponível. Último registro de '+station+' preservado.';
    }else{
      el('weatherStatus').textContent='Medição em '+station+' · '+time(c.observed_at)+(state==='ok'?' · previsão disponível':' · previsão em atualização');
    }
    el('weatherStatus').dataset.state=liveMode?'partial':stationProblem?'stale':state;
    el('weatherNowLabel').textContent=liveMode?'Estimativa atual · modelo':!c?'Sem medição recente':stationProblem?'Última medição disponível':'Temperatura observada';
    el('weatherTemp').textContent=value(shown?.temperature_c,'',1);
    el('weatherFeels').textContent='Sensação térmica: '+value(shown?.feels_like_c,' °C',1)+(liveMode?' · estimada':'');
    el('weatherCondition').textContent=shown?.condition||'Aguardando a primeira atualização válida';
    el('weatherIcon').innerHTML=icon(shown?.condition);
    el('weatherHumidityLabel').textContent='Umidade estimada';
    el('weatherHumidity').textContent=value(shown?.humidity_pct,' %');
    el('weatherWind').textContent=value(shown?.wind_kmh,' km/h',1)+(shown?.wind_direction?' · '+shown.wind_direction:'');
    const model=f?.data_type==='model_forecast';
    el('weatherRainLabel').textContent=model?'Chuva restante · hoje':'Chuva prevista · hoje';
    const days=Array.isArray(f?.days)?f.days.filter(d=>d.date>=day).slice(0,5):[];
    const currentDay=days.find(d=>d.date===day);
    el('weatherRain').textContent=value(currentDay?.precipitation_mm,' mm',1);
    el('weatherProbability').textContent=value(currentDay?.rain_probability_pct,' %');
    el('weatherDays').innerHTML=days.length?days.map(d=>{
      const label=d.date===day?'Hoje':new Date(d.date+'T12:00:00Z').toLocaleDateString('pt-BR',{timeZone:'America/Manaus',weekday:'short',day:'2-digit'});
      return `<article class="weather-day"><div class="weather-day-head"><h3>${escape(label)}</h3>${icon(d.condition)}</div><strong>${value(d.max_c,'°')} <small>/ ${value(d.min_c,'°')}</small></strong><p>Chuva ${value(d.precipitation_mm,' mm',1)} · Prob. ${value(d.rain_probability_pct,'%')}</p><p class="day-condition">${escape(d.condition||'Condição não informada')}</p></article>`;
    }).join(''):'<p class="footnote">Previsão curta ainda não disponível para os próximos dias.</p>';
    el('weatherObserved').textContent=c?'Medição na estação '+station+' (Manaus): '+time(c.observed_at)+'. O valor pode diferir de outros pontos da cidade e do Uiara.':liveMode?'Nenhuma observação METAR recente disponível. A temperatura exibida é uma estimativa de modelo para a abertura da página.':'Observação de estação: não disponível.';
    el('weatherCollected').textContent=liveMode?'Estimativa Open-Meteo consultada ao abrir o site: '+time(liveCurrent.collected_at)+'. Não é observação de estação e não é gravada no histórico.':c?'Medição recebida pelo MPHI: '+time(c.collected_at)+'. Consulta programada a cada hora; não é uma transmissão em tempo real.':'Última coleta válida: não disponível.';
    el('weatherForecastTime').textContent=(f?.collected_at?'Previsão recebida em '+time(f.collected_at)+'.':'Previsão ainda não recebida.')+(f?.issued_at?' Modelo emitido em '+time(f.issued_at)+'.':' Horário de emissão não informado.')+(model?' Chuva de hoje é estimada somente para o período restante; chuva diária futura agrega intervalos modelados.':' Chuva prevista é total diário estimado; não é chuva observada.');
    el('weatherAccumulated').textContent='Precipitação acumulada observada: '+(c?.precipitation_accumulated_mm!=null?value(c.precipitation_accumulated_mm,' mm',1)+' · '+(c.precipitation_accumulation_period||'período não informado'):'não fornecida pelo produto atual')+'.';
    if(model)el('weatherCredit').innerHTML=(liveMode?'Estimativa atual ao abrir: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (modelo, não estação). ':'Temperatura e vento observados: NOAA Aviation Weather Center / METAR. ')+(liveMode?'Última observação METAR preservada no histórico. ':'Umidade estimada a partir do ponto de orvalho. ')+'Previsão dos próximos dias: MET Norway, adaptada pelo MPHI (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0 ↗</a>). A chuva prevista não é chuva medida; probabilidade e sensação térmica não são fornecidas.';
    else el('weatherCredit').innerHTML=(liveMode?'Estimativa atual ao abrir: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (modelo, não estação). ':'Medição: NOAA Aviation Weather Center / METAR. ')+(liveMode?'Última observação METAR preservada no histórico. ':'Umidade calculada a partir do ponto de orvalho. ')+'Previsão: '+(snapshot?.source||'não disponível')+'.';
    const link=el('weatherSourceLink');
    link.textContent='NOAA · METAR ↗';
    link.href='https://aviationweather.gov/data/metar/?id=SBMN';
  }
  async function json(path){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{const sep=path.includes('?')?'&':'?';const r=await fetch(path+sep+'v='+Date.now(),{cache:'no-store',signal:controller.signal});if(!r.ok)throw new Error('weather_unavailable');return await r.json();}finally{clearTimeout(timer);}
  }
  async function load(){
    if(busy)return;busy=true;
    try{
      const results=await Promise.allSettled([json('data/weather_latest.json'),json('data/weather_status.json'),json('data/weather_observation_latest.json'),json('data/weather_observation_status.json'),json(LIVE_URL)]);
      failed=results.slice(0,2).some(r=>r.status==='rejected');
      observationFailed=results.slice(2,4).some(r=>r.status==='rejected');
      liveFailed=results[4].status==='rejected';
      if(results[0].status==='fulfilled'){
        const next=results[0].value;
        if(next?.schema!=='mphi-weather-v1'||(next.current!==null&&typeof next.current!=='object')||(next.forecast!==null&&!Array.isArray(next.forecast?.days)))failed=true;
        else snapshot=next;
      }
      if(results[1].status==='fulfilled')status=results[1].value;
      if(results[2].status==='fulfilled'){
        const next=results[2].value;
        if(next?.schema!=='mphi-weather-observation-v1'||!['SBMN','SBEG'].includes(next?.location?.station_id)||next?.current?.data_type!=='station_observation'||!Number.isFinite(next?.current?.temperature_c)||!Number.isFinite(Date.parse(next?.current?.observed_at)))observationFailed=true;
        else observation=next;
      }
      if(results[3].status==='fulfilled')observationStatus=results[3].value;
      live=results[4].status==='fulfilled'?{current:normalizeLive(results[4].value)}:null;
      render();
    }catch{failed=true;el('weatherStatus').textContent='Dados meteorológicos temporariamente indisponíveis. Última atualização válida preservada.';el('weatherStatus').dataset.state='unavailable';}
    finally{busy=false;}
  }
  if(!el('weatherTitle'))return;
  load();
  setInterval(()=>{if(!document.hidden)load();},300000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();
