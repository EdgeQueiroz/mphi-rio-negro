'use strict';
const fmt=(n,d=2)=>n==null||!Number.isFinite(Number(n))?'—':Number(n).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtDate=s=>s?new Date(s+'T12:00:00Z').toLocaleDateString('pt-BR',{timeZone:'America/Manaus'}):'—';
const fmtTime=s=>s?new Date(s).toLocaleString('pt-BR',{timeZone:'America/Manaus',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' (Manaus)':'não disponível';
const localDate=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const signed=(n,d=0)=>n==null?'—':(n>0?'+':'')+fmt(n,d);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let model=null,validationData=null,collectionStatus=null,chartRange='all',loading=false;
const $=id=>document.getElementById(id);
async function fetchJSON(path,required=true){
  const r=await fetch(path+'?v='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(!r.ok){if(!required)return null;throw new Error('HTTP '+r.status);}
  return r.json();
}
async function load(){
  if(loading)return;loading=true;
  try{
    const [next,validation,status]=await Promise.all([fetchJSON('data/latest.json'),fetchJSON('data/validation.json',false).catch(()=>null),fetchJSON('data/status.json',false).catch(()=>null)]);
    if(!next?.current?.date||!Number.isFinite(next.current.level)||!Array.isArray(next.series))throw new Error('Dados inválidos');
    model=next;validationData=validation;collectionStatus=status;
    $('loadError').hidden=true;render();
  }catch(e){
    $('loadError').hidden=false;
    $('loadErrorText').textContent=model?'Não foi possível consultar a publicação agora. Os últimos dados carregados permanecem visíveis.':'Não foi possível carregar os dados. Consulte a fonte oficial ou tente novamente.';
    if(!model){$('phase').textContent='Dados indisponíveis';$('observationInfo').textContent='Nenhuma medição carregada.';$('freshnessLabel').textContent='Publicação indisponível';}
  }finally{loading=false;}
}
function renderFreshness(){
  const c=model.current,s=collectionStatus;
  $('updatedAt').textContent='Dados atualizados em '+fmtTime(model.meta.updated_at);
  $('checkedAt').textContent='Última consulta ao Porto: '+fmtTime(s?.checked_at);
  const today=localDate();
  const checkIsToday=s?.checked_at&&new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(s.checked_at))===today;
  let label,note,kind;
  if(s?.state==='error'){
    label='Falha na consulta ao Porto';note='Última medição válida preservada. Novas tentativas automáticas programadas.';kind='error';
  }else if(c.date===today){
    label='Medição de hoje disponível';note='Coletada em '+fmtTime(model.meta.updated_at);kind='ok';
  }else if(checkIsToday){
    label='Aguardando nova medição';note='Porto consultado hoje; última medição disponível em '+fmtDate(c.date)+'.';kind='waiting';
  }else{
    label='Última medição: '+fmtDate(c.date);note='A consulta de hoje ainda não está confirmada. Agenda diária: 08:00 de Manaus.';kind='waiting';
  }
  $('freshnessLabel').textContent=label;$('freshnessNote').textContent=note;$('updateDot').className='update-dot '+kind;
}
function render(){
  const c=model.current;
  $('level').textContent=fmt(c.level);$('delta24').textContent=signed(c.delta_cm)+' cm';
  const observed=model.series.filter(x=>Number.isFinite(x.level));
  const previous=observed.filter(x=>x.date<c.date).at(-1);
  const dayGap=previous?(Date.parse(c.date)-Date.parse(previous.date))/86400000:null;
  $('deltaPeriod').textContent=dayGap===1?'variação diária informada pelo Porto':'variação informada pelo Porto; intervalo sem leitura diária contínua';
  $('phase').textContent=c.phase;$('peak').textContent=fmt(c.peak)+' m';$('peakDate').textContent=fmtDate(c.peak_date);
  $('drawdown').textContent=fmt(c.drawdown)+' m';$('persistDays').textContent=c.persistence_days;
  $('observationInfo').textContent='Medição de '+fmtDate(c.date)+' · Porto de Manaus';
  $('projectionBase').textContent='Calculada a partir da medição de '+fmtDate(c.date)+'. Os prazos partem dessa data.';
  $('statusBadge').textContent=c.status;$('statusBadge').className='status '+(c.status==='NORMAL'?'normal':c.status==='ALTO'?'high':'attention');
  document.querySelector('.outlook-panel').dataset.status=c.status;
  $('score').textContent=c.score;$('scoreStatus').textContent=c.status;
  $('scoreMeter').innerHTML=Array.from({length:12},(_,i)=>`<i class="${i<c.score?'active':''}" aria-hidden="true"></i>`).join('');
  $('scoreMeter').setAttribute('aria-label',`Pontuação ${c.score} de 12. ${c.status}.`);
  const descriptions={NORMAL:'Os indicadores estão na faixa normal do modelo. Acompanhe a evolução das próximas medições.',ATENÇÃO:'A dinâmica do rio exige acompanhamento. O sinal é preditivo e não confirma seca severa.',ALTO:'Os indicadores atingiram a faixa alta do modelo. O sinal exige atenção e não confirma seca severa.'};
  $('outlookText').textContent=descriptions[c.status]||'Consulte os critérios que compõem a leitura.';
  $('sourceNote').textContent=model.meta.source_note;
  $('ratesGrid').innerHTML=[['3 leituras',c.avg3],['7 leituras',c.avg7],['15 leituras',c.avg15],['30 leituras',c.avg30]].map(([n,v])=>`<div class="rate ${v<0?'negative':''}"><span>Média · ${n}</span><b>${signed(v,2)} <small>cm/dia</small></b></div>`).join('');
  const sea=model.seasonal[c.date.slice(5,7)]||{},pk=model.june_peak_reference;
  const comps=[['Posição sazonal',sea.q1&&c.level<sea.q1?2:sea.median&&c.level<sea.median?1:0],['Ritmo recente · 7 leituras',c.avg7<=-12?2:c.avg7<=-8?1:0],['Aceleração · 7 × 15',c.accel_7_15<=-2?2:c.accel_7_15<=-.5?1:0],['Pico antecedente',c.peak<pk.q1?2:c.peak<pk.median?1:0],['Queda desde o pico',c.drawdown>=4?2:c.drawdown>=3?1:0],['Persistência',c.persistence_points??(c.persistence_days>=7?2:0)]];
  $('scoreComponents').innerHTML=comps.map(([n,p])=>`<div class="component"><span>${n}</span><span class="component-meter" aria-hidden="true"><i class="${p>=1?'active':''}"></i><i class="${p>=2?'active':''}"></i></span><b>${p}/2</b></div>`).join('');
  $('projectionRows').innerHTML=Object.entries(model.projections).map(([days,p])=>{
    const date=new Date(c.date+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+Number(days));
    return `<article class="proj"><div class="proj-head"><b>Em ${esc(days)} dias</b><small>${fmtDate(date.toISOString().slice(0,10))}</small></div><div class="central">${fmt(p.central)}<small>m</small></div><span class="proj-label">Cenário central</span><div class="scenario-pair"><div><span>Suave</span><b>${fmt(p.soft)} m</b></div><div><span>Estresse</span><b>${fmt(p.stress)} m</b></div></div><p class="confidence">Confiança indicativa: ${esc(p.confidence.toLowerCase())}</p></article>`;
  }).join('');
  $('seasonCards').innerHTML=Object.entries(model.seasonal).map(([m,s])=>`<div class="season-card ${m===c.date.slice(5,7)?'current':''}"><b>${new Date('2026-'+m+'-15T12:00:00Z').toLocaleDateString('pt-BR',{month:'long'})}</b>${m===c.date.slice(5,7)?'<small>MÊS DA ÚLTIMA MEDIÇÃO</small>':''}<p>1º quartil · ${fmt(s.q1)} m<br>Mediana · ${fmt(s.median)} m</p></div>`).join('');
  renderFreshness();renderValidation();drawChart();
}
function renderValidation(){
  const panel=document.querySelector('.panel.validation');
  const projectionGrid=panel?.querySelector('#projectionValidationGrid');
  const alertGrid=panel?.querySelector('#alertValidationGrid');
  if(!panel||!projectionGrid||!alertGrid)return;
  if(!validationData){
    projectionGrid.innerHTML='<div><span>Validação</span><b>indisponível</b><small>dados de controle não carregados</small></div>';
    alertGrid.innerHTML='<div><span>Alertas</span><b>em coleta</b><small>aguardando base independente</small></div>';
    return;
  }
  const h7=validationData.by_horizon?.['7']||{n:0};
  const h15=validationData.by_horizon?.['15']||{n:0};
  const h30=validationData.by_horizon?.['30']||{n:0};
  const metric=h=>h.n?`${fmt(h.mae_m*100,1)} cm`:'em coleta';
  const coverage=h=>h.n?`${fmt(h.envelope_coverage_pct,1)}%`:'em coleta';
  const lead=validationData.alert_validation?.lead_time?.value_days;
  const falseAlerts=validationData.alert_validation?.false_alerts?.count;
  const missedAlerts=validationData.alert_validation?.missed_alerts?.count;

  projectionGrid.innerHTML=`
    <div><span>Previsões preservadas</span><b>${validationData.forecast_count??0}</b><small>${validationData.current_model_version||''}</small></div>
    <div><span>Aferições concluídas</span><b>${validationData.matured_records??0}</b><small>comparações de 7, 15 e 30 dias</small></div>
    <div><span>Próxima comparação</span><b>${fmtDate(validationData.next_due)}</b><small>primeira projeção pendente</small></div>
    <div><span>Erro médio · 7 dias</span><b>${metric(h7)}</b><small>erro absoluto médio · ${h7.n||0} comparações</small></div>
    <div><span>Erro médio · 15 dias</span><b>${metric(h15)}</b><small>erro absoluto médio · ${h15.n||0} comparações</small></div>
    <div><span>Erro médio · 30 dias</span><b>${metric(h30)}</b><small>erro absoluto médio · ${h30.n||0} comparações</small></div>
    <div><span>Dentro da faixa · 7 dias</span><b>${coverage(h7)}</b><small>entre os cenários suave e estresse</small></div>`;

  alertGrid.innerHTML=`
    <div><span>Antecedência</span><b>${lead==null?'em coleta':fmt(lead,0)+' dias'}</b><small>lead time do sinal</small></div>
    <div><span>Falsos alertas</span><b>${falseAlerts==null?'em coleta':falseAlerts}</b><small>sinal sem evento observado</small></div>
    <div><span>Alertas perdidos</span><b>${missedAlerts==null?'em coleta':missedAlerts}</b><small>evento sem sinal prévio</small></div>`;

  let history=panel.querySelector('.validation-history');
  if(!history){
    history=document.createElement('div');
    history.className='validation-history';
    panel.insertBefore(history,panel.querySelector('.validation-section.alerts'));
  }
  const records=(validationData.latest_records||[]).slice(0,5);
  if(!records.length){
    history.innerHTML=`<div class="validation-history-head"><b>Histórico auditável</b><span>aguardando a primeira data-alvo</span></div><p class="validation-empty">As projeções já estão preservadas. A primeira comparação automática está prevista para <b>${fmtDate(validationData.next_due)}</b>.</p>`;
  }else{
    history.innerHTML=`<div class="validation-history-head"><b>Histórico auditável</b><span>comparações mais recentes</span></div><div class="validation-list">${records.map(r=>`<div class="validation-row"><span>${fmtDate(r.forecast_date)} · ${r.horizon_days}d · alvo ${fmtDate(r.target_date)}</span><span>projeção <b>${fmt(r.forecast_central_m)} m</b></span><span>observado <b>${fmt(r.observed_m)} m</b></span><span>erro <b>${fmt(r.absolute_error_m*100,1)} cm</b></span><span class="${r.inside_envelope?'inside':'outside'}">${r.inside_envelope?'dentro':'fora'} da faixa</span></div>`).join('')}</div>`;
  }
}

function drawChart(){
  const canvas=$('riverChart'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  if(!rect.width||!rect.height)return;
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height,pad={l:44,r:20,t:27,b:28};
  let pts=model.series.filter(x=>Number.isFinite(x.level));
  if(chartRange!=='all'){const cutoff=Date.parse(model.current.date)-Number(chartRange)*86400000;pts=pts.filter(p=>Date.parse(p.date)>=cutoff);}
  if(!pts.length){$('chartSummary').textContent='Não há medições disponíveis neste período.';return;}
  const sea=model.seasonal[model.current.date.slice(5,7)],values=pts.map(p=>p.level);
  if(sea)values.push(sea.q1,sea.median);
  const min=Math.floor(Math.min(...values)-.5),max=Math.ceil(Math.max(...values)+.5);
  const first=Date.parse(pts[0].date),last=Date.parse(pts.at(-1).date),span=Math.max(last-first,86400000);
  const x=date=>pad.l+(Date.parse(date)-first)*(W-pad.l-pad.r)/span,y=v=>pad.t+(max-v)*(H-pad.t-pad.b)/(max-min);
  ctx.clearRect(0,0,W,H);ctx.font='10px system-ui';ctx.fillStyle='#60716b';ctx.strokeStyle='#e4e8df';ctx.lineWidth=1;
  const step=Math.max(1,Math.ceil((max-min)/5));
  for(let v=min;v<=max;v+=step){ctx.beginPath();ctx.moveTo(pad.l,y(v));ctx.lineTo(W-pad.r,y(v));ctx.stroke();ctx.fillText(v+' m',2,y(v)+3);}
  if(sea){[['q1','#a07543'],['median','#87958c']].forEach(([key,color])=>{ctx.setLineDash([4,5]);ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(pad.l,y(sea[key]));ctx.lineTo(W-pad.r,y(sea[key]));ctx.stroke();});ctx.setLineDash([]);}
  ctx.beginPath();ctx.moveTo(x(pts[0].date),y(pts[0].level));pts.slice(1).forEach(p=>ctx.lineTo(x(p.date),y(p.level)));ctx.lineTo(x(pts.at(-1).date),H-pad.b);ctx.lineTo(x(pts[0].date),H-pad.b);ctx.closePath();ctx.fillStyle='rgba(25,119,106,.045)';ctx.fill();
  ctx.lineWidth=2.5;ctx.strokeStyle='#19776a';
  // Dashed segments indicate gaps; no synthetic observations are inserted.
  for(let i=1;i<pts.length;i++){ctx.setLineDash(Date.parse(pts[i].date)-Date.parse(pts[i-1].date)>86400000?[4,4]:[]);ctx.beginPath();ctx.moveTo(x(pts[i-1].date),y(pts[i-1].level));ctx.lineTo(x(pts[i].date),y(pts[i].level));ctx.stroke();}ctx.setLineDash([]);
  const end=pts.at(-1);ctx.fillStyle='#19776a';ctx.beginPath();ctx.arc(x(end.date),y(end.level),4,0,Math.PI*2);ctx.fill();ctx.font='600 11px system-ui';ctx.fillStyle='#203c37';ctx.textAlign='right';ctx.fillText(fmt(end.level)+' m',x(end.date),y(end.level)-12);
  const ticks=W<500?3:5;ctx.fillStyle='#60716b';ctx.font='9px system-ui';ctx.textAlign='center';
  for(let i=0;i<ticks;i++){const p=pts[Math.round(i*(pts.length-1)/(ticks-1))];ctx.fillText(fmtDate(p.date).slice(0,5),x(p.date),H-5);}
  const summary=`${pts.length} medições de ${fmtDate(pts[0].date)} a ${fmtDate(end.date)}. Última cota: ${fmt(end.level)} m. Trechos pontilhados indicam intervalos sem medição.`;
  $('chartSummary').textContent=summary;canvas.setAttribute('aria-label',summary);
}
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>model&&drawChart(),120);});
document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{chartRange=button.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));if(model)drawChart();}));
$('retryBtn').addEventListener('click',load);
// Reads the already-published snapshot; never manufactures a collection timestamp.
setInterval(()=>{if(!document.hidden)load();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
load();
