const fmt=(n,d=2)=>Number(n).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtDate=s=>s?new Date(s+'T12:00:00').toLocaleDateString('pt-BR'):'—';
let model=null,validationData=null;

async function load(){
  const ts=Date.now();
  const r=await fetch('data/latest.json?ts='+ts);
  model=await r.json();
  try{
    const vr=await fetch('data/validation.json?ts='+ts);
    if(vr.ok) validationData=await vr.json();
  }catch(_){validationData=null;}
  const manual=localStorage.getItem('mphi_manual');
  if(manual){
    const m=JSON.parse(manual);
    if(m.date>=model.current.date){
      model.meta.source_status='manual';
      model.meta.updated_at=m.date+'T08:00:00-04:00';
      model.current.date=m.date;
      model.current.level=Number(m.level);
      model.meta.source_note='Valor manual local aplicado neste navegador. Recalcular o MPHI no fluxo oficial antes de publicar.';
    }
  }
  render();
}

function render(){
  const c=model.current;
  document.getElementById('level').textContent=fmt(c.level);
  document.getElementById('delta24').textContent=(c.delta_cm>0?'+':'')+fmt(c.delta_cm,0)+' cm';
  document.getElementById('phase').textContent=c.phase;
  document.getElementById('peak').textContent=fmt(c.peak)+' m';
  document.getElementById('peakDate').textContent=fmtDate(c.peak_date);
  document.getElementById('drawdown').textContent=fmt(c.drawdown)+' m';
  document.getElementById('persistDays').textContent=c.persistence_days;
  document.getElementById('updatedAt').textContent='Atualizado em '+new Date(model.meta.updated_at).toLocaleString('pt-BR',{timeZone:'America/Manaus',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
  const badge=document.getElementById('statusBadge');
  badge.textContent=c.status;
  badge.className='status '+(c.status==='NORMAL'?'normal':c.status==='ALTO'?'high':'attention');
  document.getElementById('score').textContent=c.score;
  document.getElementById('scoreStatus').textContent=c.status;
  document.getElementById('sourceNote').textContent=model.meta.source_note;

  const rates=[['3 dias',c.avg3],['7 dias',c.avg7],['15 dias',c.avg15],['30 dias',c.avg30]];
  document.getElementById('ratesGrid').innerHTML=rates.map(([k,v])=>`<div class="rate ${v<0?'negative':''}"><span>VELOCIDADE · ${k}</span><b>${v>0?'+':''}${fmt(v,2)} cm/d</b></div>`).join('');

  const m=Number(c.date.slice(5,7));
  const sea=model.seasonal[String(m).padStart(2,'0')]||{};
  const seasonalPts=sea.q1&&c.level<sea.q1?2:sea.median&&c.level<sea.median?1:0;
  const velPts=c.avg7<=-12?2:c.avg7<=-8?1:0;
  const accPts=c.accel_7_15<=-2?2:c.accel_7_15<=-.5?1:0;
  const pk=model.june_peak_reference;
  const peakPts=c.peak<pk.q1?2:c.peak<pk.median?1:0;
  const ddPts=c.drawdown>=4?2:c.drawdown>=3?1:0;
  const persPts=c.persistence_days>=7?2:0;
  const comps=[['Posição sazonal',seasonalPts],['Velocidade 7d',velPts],['Aceleração 7×15',accPts],['Pico antecedente',peakPts],['Drawdown',ddPts],['Persistência',persPts]];
  document.getElementById('scoreComponents').innerHTML=comps.map(([n,p])=>`<div class="component"><span>${n}</span><b>${p}/2</b></div>`).join('');

  document.getElementById('projectionRows').innerHTML=Object.entries(model.projections).map(([d,p])=>`<div class="proj"><b>${d} dias</b><span>suave ${fmt(p.soft)}m</span><span class="central">central ${fmt(p.central)}m</span><span>estresse ${fmt(p.stress)}m</span><span>${p.confidence}</span></div>`).join('');
  document.getElementById('seasonCards').innerHTML=Object.entries(model.seasonal).map(([m,s])=>`<div class="season-card"><b>${m==='08'?'Agosto':m==='09'?'Setembro':m}</b><p>Q1 · ${fmt(s.q1)} m<br>Mediana · ${fmt(s.median)} m</p></div>`).join('');
  renderValidation();
  drawChart();
}

function renderValidation(){
  const panel=document.querySelector('.panel.validation');
  const grid=panel?.querySelector('.validation-grid');
  if(!panel||!grid)return;
  if(!validationData){
    grid.innerHTML='<div><span>Validação</span><b>indisponível</b></div>';
    return;
  }
  const h7=validationData.by_horizon?.['7']||{n:0};
  const h15=validationData.by_horizon?.['15']||{n:0};
  const h30=validationData.by_horizon?.['30']||{n:0};
  const metric=h=>h.n?`${fmt(h.mae_m,3)} m`:'em coleta';
  const coverage=h=>h.n?`${fmt(h.envelope_coverage_pct,1)}%`:'em coleta';
  const lead=validationData.alert_validation?.lead_time?.value_days;
  const falseAlerts=validationData.alert_validation?.false_alerts?.count;
  const missedAlerts=validationData.alert_validation?.missed_alerts?.count;
  grid.innerHTML=`
    <div><span>Previsões congeladas</span><b>${validationData.forecast_count??0}</b><small>${validationData.current_model_version||''}</small></div>
    <div><span>Próxima aferição</span><b>${fmtDate(validationData.next_due)}</b><small>primeiro vencimento pendente</small></div>
    <div><span>MAE · 7 dias</span><b>${metric(h7)}</b><small>${h7.n||0} amostras maduras</small></div>
    <div><span>MAE · 15 dias</span><b>${metric(h15)}</b><small>${h15.n||0} amostras maduras</small></div>
    <div><span>MAE · 30 dias</span><b>${metric(h30)}</b><small>${h30.n||0} amostras maduras</small></div>
    <div><span>Dentro do envelope · 7d</span><b>${coverage(h7)}</b><small>suave ↔ estresse</small></div>
    <div><span>Lead time</span><b>${lead==null?'em coleta':fmt(lead,0)+' dias'}</b><small>evento observado independente</small></div>
    <div><span>Falsos alertas</span><b>${falseAlerts==null?'em coleta':falseAlerts}</b><small>sem inferência circular</small></div>
    <div><span>Alertas perdidos</span><b>${missedAlerts==null?'em coleta':missedAlerts}</b><small>sem inferência circular</small></div>
    <div><span>Aferições concluídas</span><b>${validationData.matured_records??0}</b><small>7d + 15d + 30d</small></div>`;

  let history=panel.querySelector('.validation-history');
  if(!history){
    history=document.createElement('div');
    history.className='validation-history';
    panel.appendChild(history);
  }
  const records=validationData.latest_records||[];
  if(!records.length){
    history.innerHTML=`<div class="validation-history-head"><b>Histórico auditável</b><span>aguardando primeira previsão vencer</span></div><p class="validation-empty">As previsões já estão congeladas. A primeira aferição automática está prevista para <b>${fmtDate(validationData.next_due)}</b>.</p>`;
  }else{
    history.innerHTML=`<div class="validation-history-head"><b>Histórico auditável</b><span>últimas aferições</span></div><div class="validation-list">${records.map(r=>`<div class="validation-row"><span>${fmtDate(r.forecast_date)} → ${r.horizon_days}d</span><span>prev. <b>${fmt(r.forecast_central_m)} m</b></span><span>obs. <b>${fmt(r.observed_m)} m</b></span><span>erro <b>${fmt(r.absolute_error_m,3)} m</b></span><span class="${r.inside_envelope?'inside':'outside'}">${r.inside_envelope?'dentro':'fora'} do envelope</span></div>`).join('')}</div>`;
  }
  const note=panel.querySelector('.footnote');
  if(note)note.textContent='Previsões são congeladas na emissão. A validação usa somente observações futuras; mudanças de versão permanecem separadas.';
}

function drawChart(){
  const canvas=document.getElementById('riverChart'),ctx=canvas.getContext('2d'),dpr=devicePixelRatio||1,rect=canvas.getBoundingClientRect();
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height,pad={l:48,r:18,t:18,b:32};
  const pts=model.series.filter(x=>x.level!=null),vals=pts.map(x=>x.level),min=Math.floor((Math.min(...vals)-.7)*2)/2,max=Math.ceil((Math.max(...vals)+.6)*2)/2;
  const x=i=>pad.l+i*(W-pad.l-pad.r)/(pts.length-1),y=v=>pad.t+(max-v)*(H-pad.t-pad.b)/(max-min);
  ctx.clearRect(0,0,W,H);ctx.font='10px system-ui';ctx.fillStyle='#78918f';ctx.strokeStyle='rgba(154,176,174,.10)';ctx.lineWidth=1;
  for(let v=Math.ceil(min);v<=max;v++){ctx.beginPath();ctx.moveTo(pad.l,y(v));ctx.lineTo(W-pad.r,y(v));ctx.stroke();ctx.fillText(v.toFixed(0)+'m',7,y(v)+3)}
  const sea=model.seasonal[model.current.date.slice(5,7)];
  if(sea){[['q1','#E6A23C'],['median','#8197a0']].forEach(([k,col])=>{ctx.setLineDash([5,5]);ctx.strokeStyle=col;ctx.globalAlpha=.5;ctx.beginPath();ctx.moveTo(pad.l,y(sea[k]));ctx.lineTo(W-pad.r,y(sea[k]));ctx.stroke();ctx.globalAlpha=1;ctx.setLineDash([])})}
  ctx.strokeStyle='#36C2B4';ctx.lineWidth=2.2;ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.level)):ctx.moveTo(x(i),y(p.level)));ctx.stroke();
  const last=pts.length-1;ctx.fillStyle='#36C2B4';ctx.beginPath();ctx.arc(x(last),y(pts[last].level),4,0,Math.PI*2);ctx.fill();ctx.fillStyle='#F3F6F4';ctx.font='11px system-ui';ctx.fillText(fmt(pts[last].level)+'m',Math.max(pad.l,x(last)-55),y(pts[last].level)-10);
  for(let i=0;i<pts.length;i+=Math.max(1,Math.floor(pts.length/5))){ctx.fillStyle='#78918f';ctx.font='9px system-ui';ctx.fillText(new Date(pts[i].date+'T12:00:00').toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'}),x(i)-12,H-9)}
}

window.addEventListener('resize',()=>model&&drawChart());
const dlg=document.getElementById('maintenanceDialog');
document.getElementById('maintenanceBtn').onclick=()=>{document.getElementById('manualDate').value=model.current.date;document.getElementById('manualLevel').value=model.current.level;dlg.showModal()};
document.getElementById('saveManual').onclick=()=>{const date=document.getElementById('manualDate').value,level=document.getElementById('manualLevel').value;if(!date||!level)return;localStorage.setItem('mphi_manual',JSON.stringify({date,level}));dlg.close();load()};
load();
