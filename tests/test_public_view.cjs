const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'docs/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'docs/styles.css'), 'utf8');
const latest = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/latest.json'), 'utf8'));

test('one public Rio Negro forecast, basin research only behind the scenes', () => {
  assert.equal((html.match(/id="projecoes"/g) || []).length, 1);
  assert.equal((html.match(/id="projectionRows"/g) || []).length, 1);
  assert.match(html, /MPHI-PUBLIC-VIEW-V2/);
  assert.match(html, /MPHI v1\.0 · PREVISÃO PÚBLICA/);
  assert.match(html, /ainda não alteram a previsão pública MPHI v1\.0/);
  for (const hidden of ['shadowProjectionBlock','shadowProjectionRows','tabatinga.js','id="tabatinga"']) {
    assert.ok(!html.includes(hidden), 'Must not expose: ' + hidden);
  }
  assert.ok(html.indexOf('id="projecoes"') < html.indexOf('id="trajetoria"'));
  assert.ok(html.indexOf('id="trajetoria"') < html.indexOf('id="meteorologia"'));
  assert.ok(!js.includes('hydrologic_latest.json'));
  assert.ok(!js.includes('shadow_models'));
  assert.ok(!js.includes('shadowCard'));
  assert.ok(!js.includes('shadowProjectionBlock'));
});
test('baseline observations remain structurally available', () => {
  assert.equal(latest.meta.model, 'MPHI v1.0');
  assert.deepEqual(Object.keys(latest.projections).sort(), ['15','30','7']);
  for (const p of Object.values(latest.projections)) {
    assert.ok(Number.isFinite(p.central));
    assert.ok(Number.isFinite(p.soft));
    assert.ok(Number.isFinite(p.stress));
  }
  for (const file of ['forecast_ledger.json','hydrologic_ledger.json','validation.json','basin_signals.json']) {
    assert.ok(fs.existsSync(path.join(root,'docs/data',file)));
  }
});
test('dynamic rendering produces one forecast in three horizons without extra feeds', async () => {
  const elements = {};
  const el = id => elements[id] ||= {
    textContent:'',innerHTML:'',dataset:{},hidden:false,className:'',
    addEventListener() {},setAttribute() {},after() {},
    getContext() {return {};},getBoundingClientRect() {return {width:0,height:0};}
  };
  const requests=[];
  const context = {
    Date,Intl,Number,Array,Object,Math,Map,Set,
    document:{
      hidden:false,getElementById:el,
      querySelector(selector){return selector==='.outlook-panel'?el('outlook-panel'):null;},
      querySelectorAll(){return [];},addEventListener(){},createElement(){return el('intervalChange');}
    },
    window:{devicePixelRatio:1,addEventListener(){}},
    fetch: async (uri)=>{
      requests.push(uri);
      if(uri.startsWith('data/latest.json'))return {ok:true,json:async()=>latest};
      return {ok:false,status:404,json:async()=>null};
    },
    setInterval(){},setTimeout(){},clearTimeout(){},
    AbortSignal, console
  };
  vm.runInNewContext(js,context,{filename:'docs/app.js'});
  await new Promise(resolve=>setImmediate(resolve));
  const cards=el('projectionRows').innerHTML;
  assert.equal((cards.match(/class="proj forecast-card"/g)||[]).length,3);
  for(const horizon of [7,15,30])assert.ok(cards.includes('Em '+horizon+' dias'));
  assert.ok(cards.includes('Ver faixa de cenários'));
  assert.ok(!cards.includes('Projeção experimental'));
  assert.equal(requests.length,3);
  assert.ok(requests.every(u=>!/hydrologic_latest|basin_signals|tabatinga/.test(u)));
  assert.equal(el('loadError').hidden,true);
});

test('water-blue theme and historical records directly after the current gauge', () => {
  assert.match(html, /MPHI-LIGHT-BLUE-V3/);
  assert.match(html, /styles\.css\?v=20261118-azul-aguas/);
  assert.match(html, /name="theme-color" content="#eaf5fb"/);
  assert.equal((html.match(/class="historic-records"/g)||[]).length, 1);
  const anchors = [
    'id="panorama"',
    'class="update-strip"',
    'class="historic-records"',
    'class="facts-strip"',
    'id="projecoes"'
  ].map(needle => html.indexOf(needle));
  assert.ok(anchors.every(n => n !== -1), 'Expected dashboard sections are present');
  assert.ok(anchors.every((n,i) => i === 0 || n > anchors[i-1]), 'Historical records must be directly below the current measurement');
  assert.match(css, /MPHI WATER-BLUE V3/);
  assert.match(css, /--bg:#eaf5fb/);
  assert.match(css, /color-scheme:light/);
  assert.match(css, /\.river-opening::before/);
  assert.match(css, /\.historic-records\{/);
  assert.match(js, /ctx\.strokeStyle='#c0dce9'/);
  assert.match(js, /ctx\.fillStyle='#547890'/);
});
