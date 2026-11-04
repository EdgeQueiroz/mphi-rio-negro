(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const set = (id, value) => { const element = byId(id); if (element) element.textContent = value; };
  const levelFormat = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const changeFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
  let loading = false;
  let hasData = false;

  function validDay(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const time = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
  }

  function todayInManaus() {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Manaus', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date());
    const item = type => parts.find(part => part.type === type).value;
    return `${item('year')}-${item('month')}-${item('day')}`;
  }

  function formatDay(value) {
    if (!validDay(value)) return '—';
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  function formatCheck(value) {
    if (!value || !Number.isFinite(Date.parse(value))) return '';
    return new Intl.DateTimeFormat('pt-BR', {
      timeZone: 'America/Manaus', day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    }).format(new Date(value));
  }

  function showChange(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return `${value > 0 ? '+' : ''}${changeFormat.format(value)} cm`;
  }

  function render(data) {
    if (!data || data.schema !== 'mphi-tabatinga-observation-v1' ||
        data.station?.code !== '10100000') throw new Error('Dados incompatíveis');
    const latest = data.latest;
    const hasLatest = latest && validDay(latest.date) &&
      typeof latest.level_m === 'number' && Number.isFinite(latest.level_m);
    set('tabatingaLevel', hasLatest ? levelFormat.format(latest.level_m) : '—');
    set('tabatingaDate', hasLatest ? formatDay(latest.date) : '—');
    set('tabatingaSamples', hasLatest && Number.isInteger(latest.samples) && latest.samples > 0
      ? `${latest.samples} ${latest.samples === 1 ? 'leitura disponível' : 'leituras disponíveis'}` : 'Aguardando leituras');
    set('tabatingaChange3', showChange(data.changes_cm?.['3d']));
    set('tabatingaChange7', showChange(data.changes_cm?.['7d']));
    const status = byId('tabatingaStatus');
    if (!status) return;
    const check = formatCheck(data.checked_at);
    const observationAge = hasLatest
      ? (Date.parse(todayInManaus() + 'T00:00:00Z') - Date.parse(latest.date + 'T00:00:00Z')) / 86400000
      : null;
    const checkAge = data.checked_at ? Date.now() - Date.parse(data.checked_at) : Infinity;
    let message;
    let warning = true;
    if (data.source_status === 'unavailable') {
      message = hasLatest ? 'Fonte indisponível na última consulta; última medição preservada.'
        : 'Fonte indisponível na última consulta; ainda não há medição válida.';
    } else if (data.source_status === 'invalid') {
      message = hasLatest ? 'A fonte retornou dados inconsistentes; última medição válida preservada.'
        : 'A fonte não retornou uma medição válida.';
    } else if (!hasLatest) {
      message = 'Ainda não há medição válida disponível.';
    } else if (data.source_status === 'stale' || observationAge > 3 || observationAge < 0) {
      message = 'Última medição desatualizada; consulte a data antes de utilizá-la.';
    } else if (!Number.isFinite(checkAge) || checkAge > 48 * 3600000 || checkAge < -300000) {
      message = 'Consulta à fonte desatualizada; confira a data da última medição.';
    } else if (data.source_status === 'received') {
      message = 'Medição disponível.';
      warning = false;
    } else {
      message = 'Estado da fonte não confirmado; consulte a última medição.';
    }
    status.dataset.state = warning ? 'warning' : 'ok';
    status.textContent = check ? `${message} Última consulta: ${check} (Manaus).` : message;
    hasData = hasLatest;
  }

  async function load() {
    if (loading || !byId('tabatingaStatus')) return;
    loading = true;
    try {
      const response = await fetch('data/tabatinga.json?v=' + Date.now(), {
        cache: 'no-store', signal: AbortSignal.timeout(15000)
      });
      if (!response.ok) throw new Error('Fonte indisponível');
      render(await response.json());
    } catch (_) {
      const status = byId('tabatingaStatus');
      status.dataset.state = 'warning';
      status.textContent = hasData
        ? 'Não foi possível consultar a publicação; a última leitura carregada permanece visível.'
        : 'Dados de Tabatinga indisponíveis no momento.';
    } finally {
      loading = false;
    }
  }

  setInterval(() => { if (!document.hidden) load(); }, 300000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  load();
})();
