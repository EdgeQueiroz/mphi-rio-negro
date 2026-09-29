/* Independent weather context: no access to MPHI model, score or projections. */
(()=>{
  'use strict';
  const el=id=>document.getElementById(id);
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const value=(n,unit='',digits=0)=>typeof n==='number'&&Number.isFinite(n)?n.toLocaleString('pt-BR',{maximumFractionDigits:digits})+unit:'—';
  const time=s=>s&&Number.isFinite(Date.parse(s))?new Date(s).toLocaleString('pt-BR',{timeZone:'America/Manaus',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' (Manaus)':'não disponível';
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const icon=condition=>{
    const s=(condition||'').toLowerCase();
    const cloud='<path d="M7 28h23a7 7 0 0 0 0-14 10 10 0 0 0-19-2 8 8 0 0 0-4 16Z"/>';
    const sun='<circle cx="20" cy="19" r="7"/><path d="M20 5V2m0 34v-3M6 19H3m34 0h-3M10 9 8 7m24 24-2-2M30 9l2-2M10 29l-2 2"/>';
    const rain='<path d="m12 32-2 4m11-4-2 4m11-4-2 4"/>';
    const drawing=/trovo|tempest|raio/.test(s)?cloud+'<path d="m21 25-5 7h6l-4 7"/>':/chuva|pancada|garoa/.test(s)?cloud+rain:/sol|limpo/.test(s)?sun:cloud;
    return '<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+drawing+'</svg>';
  };
  let snapshot=null,status=null,observation=null,observationStatus=null,busy=false,failed=false,observationFailed=false;
  const age=s=>s&&Number.isFinite(Date.parse(s))?(Date.now()-Date.parse(s))/36e5:Infinity;
  function render(){
    const c=observation?.current,f=snapshot?.forecast,day=today();
    const limit=status?.stale_after_hours||12;
    const observationOld=!c||age(c.observed_at)>(observationStatus?.stale_after_hours||2)||age(c.observed_at)<-.25;
    const forecastOld=f&&(age(f.collected_at)>limit||age(status?.checked_at)>limit);
    let state=failed?'unavailable':status?.state||'unavailable';
    if(forecastOld&&state==='ok')state='stale';
    const station=observation?.location?.station_name||'Manaus';
    const stationProblem=observationFailed||observationStatus?.state!=='ok'||observationOld;
    if(!c){
      el('weatherStatus').textContent='Medição em estação temporariamente indisponível. A previsão dos próximos dias permanece separada.';
    }else if(stationProblem){
      el('weatherStatus').textContent='Medição em estação temporariamente indisponível. Último registro de '+station+' preservado.';
    }else{
      el('weatherStatus').textContent='Medição em '+station+' · '+time(c.observed_at)+(state==='ok'?' · previsão disponível':' · previsão em atualização');
    }
    el('weatherStatus').dataset.state=stationProblem?'stale':state;
    el('weatherNowLabel').textContent=!c?'Sem medição recente':stationProblem?'Última medição disponível':'Temperatura observada';
    el('weatherTemp').textContent=value(c?.temperature_c,'',1);
    el('weatherFeels').textContent='Sensação térmica: '+value(c?.feels_like_c,' °C',1);
    el('weatherCondition').textContent=c?.condition||'Aguardando a primeira atualização válida';
    el('weatherIcon').innerHTML=icon(c?.condition);
    el('weatherHumidityLabel').textContent='Umidade estimada';
    el('weatherHumidity').textContent=value(c?.humidity_pct,' %');
    el('weatherWind').textContent=value(c?.wind_kmh,' km/h',1)+(c?.wind_direction?' · '+c.wind_direction:'');
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
    el('weatherObserved').textContent='Medição na estação '+station+' (Manaus): '+time(c?.observed_at)+'. O valor pode diferir de outros pontos da cidade e do Uiara.';
    el('weatherCollected').textContent='Medição recebida pelo MPHI: '+time(c?.collected_at)+'. Consulta programada a cada hora; não é uma transmissão em tempo real.';
    el('weatherForecastTime').textContent=(f?.collected_at?'Previsão recebida em '+time(f.collected_at)+'.':'Previsão ainda não recebida.')+(f?.issued_at?' Modelo emitido em '+time(f.issued_at)+'.':' Horário de emissão não informado.')+(model?' Chuva de hoje é estimada somente para o período restante; chuva diária futura agrega intervalos modelados.':' Chuva prevista é total diário estimado; não é chuva observada.');
    el('weatherAccumulated').textContent='Precipitação acumulada observada: '+(c?.precipitation_accumulated_mm!=null?value(c.precipitation_accumulated_mm,' mm',1)+' · '+(c.precipitation_accumulation_period||'período não informado'):'não fornecida pelo produto atual')+'.';
    if(model)el('weatherCredit').innerHTML='Temperatura e vento observados: NOAA Aviation Weather Center / METAR. Umidade estimada a partir do ponto de orvalho. Previsão dos próximos dias: MET Norway, adaptada pelo MPHI (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0 ↗</a>). A chuva prevista não é chuva medida; probabilidade e sensação térmica não são fornecidas.';
    else el('weatherCredit').textContent='Medição: NOAA Aviation Weather Center / METAR. Umidade calculada a partir do ponto de orvalho. Previsão: '+(snapshot?.source||'não disponível')+'.';
    const link=el('weatherSourceLink');
    link.textContent='NOAA · METAR ↗';
    link.href='https://aviationweather.gov/data/metar/?id=SBMN';
  }
  async function json(path){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{const r=await fetch(path+'?v='+Date.now(),{cache:'no-store',signal:controller.signal});if(!r.ok)throw new Error('weather_unavailable');return await r.json();}finally{clearTimeout(timer);}
  }
  async function load(){
    if(busy)return;busy=true;
    try{
      const results=await Promise.allSettled([json('data/weather_latest.json'),json('data/weather_status.json'),json('data/weather_observation_latest.json'),json('data/weather_observation_status.json')]);
      failed=results.slice(0,2).some(r=>r.status==='rejected');
      observationFailed=results.slice(2).some(r=>r.status==='rejected');
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
      render();
    }catch{failed=true;el('weatherStatus').textContent='Dados meteorológicos temporariamente indisponíveis. Última atualização válida preservada.';el('weatherStatus').dataset.state='unavailable';}
    finally{busy=false;}
  }
  if(!el('weatherTitle'))return;
  load();
  setInterval(()=>{if(!document.hidden)load();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();
