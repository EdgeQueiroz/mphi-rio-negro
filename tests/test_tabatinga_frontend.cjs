const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const code = fs.readFileSync(path.join(__dirname, '../docs/tabatinga.js'), 'utf8');
const ids = ['tabatingaLevel', 'tabatingaDate', 'tabatingaSamples', 'tabatingaChange3',
             'tabatingaChange7', 'tabatingaStatus'];

function dayInManaus(daysAgo = 0) {
  const instant = new Date(Date.now() - daysAgo * 86400000);
  const parts = new Intl.DateTimeFormat('en-US', {timeZone: 'America/Manaus', year: 'numeric',
    month: '2-digit', day: '2-digit'}).formatToParts(instant);
  const part = type => parts.find(item => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function snapshot(overrides = {}) {
  return {schema: 'mphi-tabatinga-observation-v1', station: {code: '10100000'},
    source_status: 'received', checked_at: new Date().toISOString(),
    latest: {date: dayInManaus(), level_m: -2.34, samples: 5},
    changes_cm: {'3d': -4, '7d': null}, ...overrides};
}

async function show(data, shouldFail = false) {
  const elements = Object.fromEntries(ids.map(id => [id, {textContent: '', dataset: {}}]));
  const context = {
    document: {hidden: false, getElementById: id => elements[id] || null, addEventListener() {}},
    fetch: async () => { if (shouldFail) throw new Error('offline'); return {ok: true, json: async () => data}; },
    setInterval() {}, Date, Intl, Number, AbortSignal, console
  };
  vm.runInNewContext(code, context);
  await new Promise(resolve => setImmediate(resolve));
  return elements;
}

test('shows valid negative gauge readings and leaves missing changes empty', async () => {
  const el = await show(snapshot());
  assert.equal(el.tabatingaLevel.textContent, '-2,34');
  assert.equal(el.tabatingaChange3.textContent, '-4 cm');
  assert.equal(el.tabatingaChange7.textContent, '—');
  assert.match(el.tabatingaStatus.textContent, /Medição disponível/);
});

test('displays preserved observation but warns about an unavailable source', async () => {
  const el = await show(snapshot({source_status: 'unavailable'}));
  assert.equal(el.tabatingaLevel.textContent, '-2,34');
  assert.match(el.tabatingaStatus.textContent, /Fonte indisponível.*preservada/);
  assert.equal(el.tabatingaStatus.dataset.state, 'warning');
});

test('identifies inconsistent source data while preserving the last reading', async () => {
  const el = await show(snapshot({source_status: 'invalid', latest: {date: dayInManaus(), level_m: -1.2, samples: 1}}));
  assert.equal(el.tabatingaLevel.textContent, '-1,20');
  assert.equal(el.tabatingaSamples.textContent, '1 leitura disponível');
  assert.match(el.tabatingaStatus.textContent, /dados inconsistentes.*preservada/);
});

test('detects stale observations even if the stored source state says received', async () => {
  const el = await show(snapshot({latest: {date: dayInManaus(8), level_m: 1.2, samples: 2}}));
  assert.match(el.tabatingaStatus.textContent, /medição desatualizada/);
});

test('does not claim a reading exists when the first fetch fails', async () => {
  const el = await show(null, true);
  assert.match(el.tabatingaStatus.textContent, /indisponíveis/);
});
