#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from math import sqrt
import json, re, sys
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'data' / 'latest.json'
LEDGER = ROOT / 'docs' / 'data' / 'forecast_ledger.json'
VALIDATION = ROOT / 'docs' / 'data' / 'validation.json'
URL = 'https://portodemanaus.com.br/nivel-do-rio-negro/'
TZ = timezone(timedelta(hours=-4))


def avg(xs, n):
    ys = [x['delta_cm'] for x in xs[-n:] if x.get('delta_cm') is not None]
    return round(sum(ys) / len(ys), 2) if ys else None


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def extract_latest(html):
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    for table in soup.find_all('table'):
        text = ' '.join(table.stripped_strings)
        if 'Cota' not in text or 'Dia' not in text:
            continue
        rows = []
        for tr in table.find_all('tr'):
            cells = [c.get_text(' ', strip=True).replace(',', '.') for c in tr.find_all(['td', 'th'])]
            if len(cells) < 2:
                continue
            try:
                day = int(re.sub(r'\D', '', cells[0]))
                level = float(re.search(r'\d+(?:\.\d+)?', cells[1]).group())
                delta = float(re.search(r'-?\d+(?:\.\d+)?', cells[2]).group()) if len(cells) > 2 and re.search(r'-?\d', cells[2]) else None
                if 1 <= day <= 31 and 5 <= level <= 35:
                    rows.append((day, level, delta))
            except Exception:
                pass
        if rows:
            candidates.append(rows)
    if not candidates:
        raise RuntimeError('Nenhuma tabela mensal reconhecida')
    now = datetime.now(TZ)
    day, level, delta = candidates[0][-1]
    return f'{now.year:04d}-{now.month:02d}-{day:02d}', level, delta


def base_score_for_prefix(valid, idx, d):
    sub = valid[:idx + 1]
    cur = sub[-1]
    level = cur['level']
    a7 = avg(sub, 7)
    a15 = avg(sub, 15)
    accel = round(a7 - a15, 2)
    sea = d.get('seasonal', {}).get(cur['date'][5:7])
    seasonal = 2 if sea and level < sea['q1'] else 1 if sea and level < sea['median'] else 0
    vel = 2 if a7 <= -12 else 1 if a7 <= -8 else 0
    acc = 2 if accel <= -2 else 1 if accel <= -.5 else 0
    peak = max(x['level'] for x in sub)
    pk = d['june_peak_reference']
    peakpts = 2 if peak < pk['q1'] else 1 if peak < pk['median'] else 0
    drawdown = peak - level
    dd = 2 if drawdown >= 4 else 1 if drawdown >= 3 else 0
    return seasonal + vel + acc + peakpts + dd


def persistence_days(valid, d):
    count = 0
    later_date = None
    for i in range(len(valid) - 1, -1, -1):
        current_date = datetime.fromisoformat(valid[i]['date']).date()
        if later_date is not None and (later_date - current_date).days != 1:
            break
        if base_score_for_prefix(valid, i, d) < 3:
            break
        count += 1
        later_date = current_date
    return count


def recalc(d):
    series = sorted(d['series'], key=lambda x: x['date'])
    valid = [x for x in series if x.get('level') is not None]
    c = d['current']
    last = valid[-1]
    c.update(date=last['date'], level=last['level'], delta_cm=last.get('delta_cm'))
    c['avg3'] = avg(valid, 3)
    c['avg7'] = avg(valid, 7)
    c['avg15'] = avg(valid, 15)
    c['avg30'] = avg(valid, 30)
    c['accel_7_15'] = round(c['avg7'] - c['avg15'], 2)
    peak = max(x['level'] for x in valid)
    peakrow = min((x for x in valid if x['level'] == peak), key=lambda x: x['date'])
    c['peak'] = peak
    c['peak_date'] = peakrow['date']
    c['drawdown'] = round(peak - c['level'], 2)
    c['phase'] = 'Vazante' if c['avg3'] < -0.5 else 'Enchente' if c['avg3'] > 0.5 else 'Estabilidade'
    base = base_score_for_prefix(valid, len(valid) - 1, d)
    c['base_score'] = base
    c['persistence_days'] = persistence_days(valid, d)
    c['persistence_points'] = 2 if c['persistence_days'] >= 7 else 0
    c['score'] = base + c['persistence_points']
    c['status'] = 'NORMAL' if c['score'] <= 2 else 'ATENÇÃO' if c['score'] <= 6 else 'ALTO'
    rates = {'soft': c['avg30'], 'central': (c['avg7'] + c['avg15']) / 2, 'stress': min(c['avg3'], c['avg7'], c['avg15'])}
    conf = {7: 'Média', 15: 'Média-baixa', 30: 'Baixa'}
    d['projections'] = {
        str(days): {
            **{k: round(c['level'] + r * days / 100, 2) for k, r in rates.items()},
            'confidence': conf[days]
        }
        for days in (7, 15, 30)
    }
    d['meta']['updated_at'] = datetime.now(TZ).isoformat(timespec='seconds')
    d['meta']['source_status'] = 'ok'
    d['meta']['last_score_date'] = c['date']
    d['series'] = series


def add_days(date_str, days):
    return (datetime.fromisoformat(date_str).date() + timedelta(days=days)).isoformat()


def freeze_forecast(d, ledger):
    version = d['meta'].get('model', 'MPHI')
    date = d['current']['date']
    forecast_id = f'{date}|{version}'
    entries = ledger.setdefault('entries', [])
    if any(e.get('forecast_id') == forecast_id for e in entries):
        return False
    snapshot = {
        'forecast_id': forecast_id,
        'forecast_date': date,
        'created_at': d['meta']['updated_at'],
        'model_version': version,
        'observed_level_at_issue': d['current']['level'],
        'score': d['current']['score'],
        'status': d['current']['status'],
        'phase': d['current']['phase'],
        'persistence_days': d['current']['persistence_days'],
        'projections': {}
    }
    for horizon, p in d['projections'].items():
        snapshot['projections'][horizon] = {
            'target_date': add_days(date, int(horizon)),
            'soft': p['soft'],
            'central': p['central'],
            'stress': p['stress'],
            'confidence': p['confidence']
        }
    entries.append(snapshot)
    entries.sort(key=lambda e: (e['forecast_date'], e['model_version']))
    return True


def summarize(records):
    if not records:
        return {'n': 0, 'mae_m': None, 'bias_m': None, 'rmse_m': None, 'envelope_coverage_pct': None}
    n = len(records)
    mae = sum(r['absolute_error_m'] for r in records) / n
    bias = sum(r['signed_error_m'] for r in records) / n
    rmse = sqrt(sum(r['signed_error_m'] ** 2 for r in records) / n)
    coverage = 100 * sum(1 for r in records if r['inside_envelope']) / n
    return {
        'n': n,
        'mae_m': round(mae, 3),
        'bias_m': round(bias, 3),
        'rmse_m': round(rmse, 3),
        'envelope_coverage_pct': round(coverage, 1)
    }


def build_validation(d, ledger):
    observations = {x['date']: x['level'] for x in d['series'] if x.get('level') is not None}
    current_version = d['meta'].get('model', 'MPHI')
    records = []
    pending = {'7': 0, '15': 0, '30': 0}
    next_due = []

    for entry in ledger.get('entries', []):
        for horizon, p in entry.get('projections', {}).items():
            target = p['target_date']
            observed = observations.get(target)
            if observed is None:
                pending[horizon] = pending.get(horizon, 0) + 1
                if target >= d['current']['date']:
                    next_due.append(target)
                continue
            low = min(p['soft'], p['stress'])
            high = max(p['soft'], p['stress'])
            signed = round(observed - p['central'], 3)
            records.append({
                'validation_id': f"{entry['forecast_id']}|{horizon}",
                'forecast_id': entry['forecast_id'],
                'forecast_date': entry['forecast_date'],
                'target_date': target,
                'horizon_days': int(horizon),
                'model_version': entry['model_version'],
                'forecast_central_m': p['central'],
                'forecast_soft_m': p['soft'],
                'forecast_stress_m': p['stress'],
                'observed_m': observed,
                'signed_error_m': signed,
                'absolute_error_m': round(abs(signed), 3),
                'inside_envelope': low <= observed <= high
            })

    current_records = [r for r in records if r['model_version'] == current_version]
    by_horizon = {
        h: summarize([r for r in current_records if r['horizon_days'] == int(h)])
        for h in ('7', '15', '30')
    }
    by_version = {}
    for version in sorted({e.get('model_version') for e in ledger.get('entries', []) if e.get('model_version')}):
        version_records = [r for r in records if r['model_version'] == version]
        by_version[version] = {
            h: summarize([r for r in version_records if r['horizon_days'] == int(h)])
            for h in ('7', '15', '30')
        }

    return {
        'schema': 'mphi-validation-v1',
        'updated_at': datetime.now(TZ).isoformat(timespec='seconds'),
        'current_model_version': current_version,
        'forecast_count': sum(1 for e in ledger.get('entries', []) if e.get('model_version') == current_version),
        'matured_records': len(current_records),
        'next_due': min(next_due) if next_due else None,
        'pending': pending,
        'by_horizon': by_horizon,
        'by_version': by_version,
        'metric_definition': {
            'mae_m': 'erro absoluto médio entre cota observada e projeção central',
            'bias_m': 'observado menos previsto; positivo significa rio acima da projeção central',
            'rmse_m': 'raiz do erro quadrático médio',
            'envelope_coverage_pct': 'percentual de observações entre os cenários suave e estresse'
        },
        'alert_validation': {
            'lead_time': {'status': 'em coleta', 'value_days': None, 'note': 'Aguardando evento observado independente do score para validação.'},
            'false_alerts': {'status': 'em coleta', 'count': None, 'note': 'Não calculado até existir critério observacional independente e janela completa.'},
            'missed_alerts': {'status': 'em coleta', 'count': None, 'note': 'Não calculado até existir critério observacional independente e janela completa.'}
        },
        'records': sorted(records, key=lambda r: (r['target_date'], r['forecast_date'], r['horizon_days'])),
        'latest_records': sorted(current_records, key=lambda r: (r['target_date'], r['forecast_date'], r['horizon_days']), reverse=True)[:10]
    }


def main():
    d = read_json(DATA, {})
    ledger = read_json(LEDGER, {
        'schema': 'mphi-forecast-ledger-v1',
        'policy': 'append-only: campos de previsão são congelados na emissão e não devem ser reescritos',
        'entries': []
    })
    try:
        response = requests.get(URL, timeout=30, headers={'User-Agent': 'MPHI-Uiara/1.0'})
        response.raise_for_status()
        date, level, delta = extract_latest(response.text)
        prev = next((x for x in reversed(d['series']) if x.get('level') is not None), None)
        if prev and date > prev['date'] and abs(level - prev['level']) > 1.0:
            raise RuntimeError(f'Salto anômalo: {prev["level"]} -> {level} m')
        found = next((x for x in d['series'] if x['date'] == date), None)
        if found:
            found.update(level=level, delta_cm=delta, source='Porto de Manaus')
        else:
            d['series'].append({'date': date, 'level': level, 'delta_cm': delta, 'source': 'Porto de Manaus'})
        recalc(d)
        d['meta']['source_note'] = 'Atualização automática concluída a partir do Porto de Manaus.'
        freeze_forecast(d, ledger)
        validation = build_validation(d, ledger)
        write_json(DATA, d)
        write_json(LEDGER, ledger)
        write_json(VALIDATION, validation)
    except Exception as e:
        d['meta']['source_status'] = 'stale'
        d['meta']['source_note'] = 'FONTE NÃO ATUALIZADA: ' + str(e)
        d['meta']['updated_at'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(DATA, d)
        if ledger.get('entries'):
            write_json(VALIDATION, build_validation(d, ledger))
        print(e, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
