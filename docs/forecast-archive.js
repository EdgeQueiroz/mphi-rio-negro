/* Read-only display of the original append-only ledger. No model calculations. */
(()=>{
  'use strict';
  const archive=document.getElementById('previsoes-preservadas');
  if(!archive)return;
  const status=document.getElementById('forecastArchiveStatus');
  const entries=document.getElementById('forecastArchiveEntries');
  const summary=archive.querySelector('summary');
  const escape=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=s=>/^\d{4}-\d{2}-\d{2}$/.test(s||'')?s.split('-').reverse().join('/'):'—';
  const level=n=>Number.isFinite(n)?n.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+' m':'—';
  let loaded=false,busy=false;
  async function load(){
    if(loaded||busy)return;
    busy=true;status.textContent='Consultando as previsões preservadas…';
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch('data/forecast_ledger.json?v='+Date.now(),{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error('unavailable');
      const ledger=await response.json();
      if(ledger?.schema!=='mphi-forecast-ledger-v1'||!Array.isArray(ledger.entries))throw new Error('invalid');
      const records=ledger.entries.filter(r=>r.model_version==='MPHI v1.0').sort((a,b)=>String(b.forecast_date).localeCompare(String(a.forecast_date)));
      entries.innerHTML=records.map(r=>`<details class="archive-entry"><summary><span>Emissão de ${date(r.forecast_date)}</span><span>${level(r.observed_level_at_issue)} · ${escape(r.status)}</span></summary><p class="archive-reference">${escape(r.model_version)} · cota na emissão: ${level(r.observed_level_at_issue)} · score: ${escape(r.score)} · fase: ${escape(r.phase)}</p><div class="archive-horizons">${['7','15','30'].map(h=>{const p=r.projections?.[h]||{};return `<article><h3>+${h} dias <small>Alvo: ${date(p.target_date)}</small></h3><dl><div><dt>Cenário central</dt><dd>${level(p.central)}</dd></div><div><dt>Suave</dt><dd>${level(p.soft)}</dd></div><div><dt>Estresse</dt><dd>${level(p.stress)}</dd></div></dl><p>Confiança indicativa: ${escape(p.confidence)}</p></article>`;}).join('')}</div></details>`).join('');
      status.textContent=records.length?records.length+' emissões preservadas · mais recentes primeiro. Selecione uma data para ver os horizontes.':'Nenhuma previsão registrada ainda.';
      loaded=true;
    }catch{
      status.textContent='Histórico temporariamente indisponível. Feche e abra novamente para tentar outra vez. O painel continua disponível.';
    }finally{clearTimeout(timeout);busy=false;}
  }
  archive.addEventListener('toggle',()=>{if(archive.open)load();});
  const openFromHash=()=>{if(location.hash==='#previsoes-preservadas'){archive.open=true;load();}};
  window.addEventListener('hashchange',openFromHash);
  // Delegation also handles the link dynamically rendered by app.js.
  document.addEventListener('click',event=>{
    if(event.target.closest('a[href="#previsoes-preservadas"]')){archive.open=true;load();}
  });
  document.getElementById('closeForecastArchive').addEventListener('click',()=>{
    archive.open=false;
    location.hash='confiabilidade';
    summary.focus({preventScroll:true});
  });
  openFromHash();
})();
