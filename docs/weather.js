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
  let snapshot=null,status=null,busy=false,failed=false;
  const age=s=>s&&Number.isFinite(Date.parse(s))?(Date.now()-Date.parse(s))/36e5:Infinity;
  function render(){
    const c=snapshot?.current,f=snapshot?.forecast,day=today();
    const limit=status?.stale_after_hours||12;
    const observationOld=c?.observed_at?age(c.observed_at)>limit:c?.source_time?.slice(0,10)<day;
    const stale=(c&&(age(c.collected_at)>limit||observationOld))||(f&&age(f.collected_at)>limit)||((c||f)&&age(status?.checked_at)>limit);
    let state=failed?'unavailable':status?.state||'unavailable';
    if(stale&&state==='ok')state='stale';
    const source=snapshot?.source||status?.source||'fonte meteorológica';
    const model=c?.data_type==='model_forecast';
    const messages={ok:source+' · previsão meteorológica atualizada',not_configured:'Integração preparada · aguardando ativação da Climatempo.',unavailable:'Dados meteorológicos temporariamente indisponíveis. Última atualização válida preservada.',partial:'Atualização parcial de '+source+'. Dados anteriores preservados onde necessário.',stale:'Última atualização meteorológica disponível · nova coleta em atraso.'};
    el('weatherStatus').textContent=messages[state]||messages.unavailable;
    el('weatherStatus').dataset.state=state;
    el('weatherNowLabel').textContent=!c?'Clima atual · sem dados':model?(observationOld||age(c.collected_at)>limit?'Última estimativa horária':'Estimativa horária'):(observationOld||age(c.collected_at)>limit?'Última condição disponível':'Clima agora');
    el('weatherTemp').textContent=value(c?.temperature_c,'',1);
    el('weatherFeels').textContent='Sensação térmica: '+value(c?.feels_like_c,' °C',1);
    el('weatherCondition').textContent=c?.condition||'Aguardando a primeira atualização válida';
    el('weatherIcon').innerHTML=icon(c?.condition);
    el('weatherHumidity').textContent=value(c?.humidity_pct,' %');
    el('weatherWind').textContent=value(c?.wind_kmh,' km/h',1)+(c?.wind_direction?' · '+c.wind_direction:'');
    el('weatherRainLabel').textContent=model?'Chuva restante · hoje':'Chuva prevista · hoje';
    const days=Array.isArray(f?.days)?f.days.filter(d=>d.date>=day).slice(0,5):[];
    const currentDay=days.find(d=>d.date===day);
    el('weatherRain').textContent=value(currentDay?.precipitation_mm,' mm',1);
    el('weatherProbability').textContent=value(currentDay?.rain_probability_pct,' %');
    el('weatherDays').innerHTML=days.length?days.map(d=>{
      const label=d.date===day?'Hoje':new Date(d.date+'T12:00:00Z').toLocaleDateString('pt-BR',{timeZone:'America/Manaus',weekday:'short',day:'2-digit'});
      return `<article class="weather-day"><div class="weather-day-head"><h3>${escape(label)}</h3>${icon(d.condition)}</div><strong>${value(d.max_c,'°')} <small>/ ${value(d.min_c,'°')}</small></strong><p>Chuva ${value(d.precipitation_mm,' mm',1)} · Prob. ${value(d.rain_probability_pct,'%')}</p><p class="day-condition">${escape(d.condition||'Condição não informada')}</p></article>`;
    }).join(''):'<p class="footnote">Previsão curta ainda não disponível para os próximos dias.</p>';
    el('weatherObserved').textContent=model?'Horário da estimativa do modelo: '+time(c?.valid_at)+'. Não é medição em estação local.':'Horário da observação: '+(c?.observed_at?time(c.observed_at):c?.source_time?c.source_time+' (fuso não informado pela fonte)': 'não disponível')+'.';
    el('weatherCollected').textContent='Última coleta meteorológica válida: '+time(c?.collected_at)+'. Coleta programada a cada seis horas; não é uma transmissão em tempo real.';
    el('weatherForecastTime').textContent=(f?.collected_at?'Previsão recebida em '+time(f.collected_at)+'.':'Previsão ainda não recebida.')+(f?.issued_at?' Modelo emitido em '+time(f.issued_at)+'.':' Horário de emissão não informado.')+(model?' Chuva de hoje é estimada somente para o período restante; chuva diária futura agrega intervalos modelados.':' Chuva prevista é total diário estimado; não é chuva observada.');
    el('weatherAccumulated').textContent='Precipitação acumulada observada: '+(c?.precipitation_accumulated_mm!=null?value(c.precipitation_accumulated_mm,' mm',1)+' · '+(c.precipitation_accumulation_period||'período não informado'):'não fornecida pelo produto atual')+'.';
    if(model)el('weatherCredit').innerHTML='Dados de MET Norway, adaptados e agregados pelo MPHI. <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">Licença CC BY 4.0 ↗</a>. Modelo global, não é medição no Uiara. Probabilidade de chuva e sensação térmica não fornecidas para Manaus.';
    else el('weatherCredit').textContent='Fonte: '+source+'.';
    const link=el('weatherSourceLink');
    link.textContent=model?'MET Norway · API ↗':'Climatempo Advisor ↗';
    link.href=model?'https://api.met.no/weatherapi/locationforecast/2.0/documentation':'https://advisor.climatempo.com.br/';
  }
  async function json(path){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{const r=await fetch(path+'?v='+Date.now(),{cache:'no-store',signal:controller.signal});if(!r.ok)throw new Error('weather_unavailable');return await r.json();}finally{clearTimeout(timer);}
  }
  async function load(){
    if(busy)return;busy=true;
    try{
      const results=await Promise.allSettled([json('data/weather_latest.json'),json('data/weather_status.json')]);
      failed=results.some(r=>r.status==='rejected');
      if(results[0].status==='fulfilled'){
        const next=results[0].value;
        if(next?.schema!=='mphi-weather-v1'||(next.current!==null&&typeof next.current!=='object')||(next.forecast!==null&&!Array.isArray(next.forecast?.days)))throw new Error('invalid_weather');
        snapshot=next;
      }
      if(results[1].status==='fulfilled')status=results[1].value;
      render();
    }catch{failed=true;el('weatherStatus').textContent='Dados meteorológicos temporariamente indisponíveis. Última atualização válida preservada.';el('weatherStatus').dataset.state='unavailable';}
    finally{busy=false;}
  }
  if(!el('weatherTitle'))return;
  load();
  setInterval(()=>{if(!document.hidden)load();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();
