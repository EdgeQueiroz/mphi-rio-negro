#!/usr/bin/env python3
"""MPHI v2 alpha: prospective basin-oriented hydrological challenger."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import sqrt
from pathlib import Path
from statistics import median
import json
import sys
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import update_mphi as core

ROOT = Path(__file__).resolve().parents[1]
BASIN = ROOT / 'docs' / 'data' / 'basin_signals.json'
LATEST = ROOT / 'docs' / 'data' / 'hydrologic_latest.json'
LEDGER = ROOT / 'docs' / 'data' / 'hydrologic_ledger.json'
SOURCE_URL = 'https://telemetriaws1.ana.gov.br/serviceana.asmx/DadosHidrometeorologicos'
MODEL_VERSION = 'MPHI v2.0-hydrologic-alpha'
MIN_STATIONS = 4
MIN_STATION_DAYS = 30
MIN_TRAINING_SAMPLES = 20
BLEND_WEIGHT = 0.35

STATIONS = {
    '14330000': {'name': 'Curicuriari', 'river': 'Rio Negro', 'role': 'alto curso'},
    '14420000': {'name': 'Serrinha', 'river': 'Rio Negro', 'role': 'médio curso'},
    '14480002': {'name': 'Barcelos', 'river': 'Rio Negro', 'role': 'médio curso'},
    '14840000': {'name': 'Moura', 'river': 'Rio Negro', 'role': 'baixo curso'},
    '14100000': {'name': 'Manacapuru', 'river': 'Rio Solimões-Amazonas', 'role': 'remanso'},
}


def tag_name(element):
    return element.tag.rsplit('}', 1)[-1]


def child_text(element, name):
    for child in element:
        if tag_name(child) == name:
            return (child.text or '').strip()
    return ''


def parse_telemetry_xml(text, code):
    """Return validated 15-minute observations without assuming XML namespaces."""
    root = ET.fromstring(text)
    observations = []
    for row in root.iter():
        if tag_name(row) != 'DadosHidrometereologicos':
            continue
        if child_text(row, 'CodEstacao') != code:
            continue
        timestamp = datetime.strptime(child_text(row, 'DataHora'), '%Y-%m-%d %H:%M:%S')
        raw_level = child_text(row, 'Nivel')
        if not raw_level:
            continue
        level_m = float(raw_level.replace(',', '.')) / 100
        if not 0 <= level_m <= 40:
            continue
        observations.append({'timestamp': timestamp, 'level_m': level_m})
    observations.sort(key=lambda item: item['timestamp'])
    if not observations:
        raise RuntimeError(f'Estação {code} sem cotas no período solicitado.')
    return observations


def aggregate_daily(observations):
    grouped = defaultdict(list)
    for item in observations:
        grouped[item['timestamp'].date().isoformat()].append(item['level_m'])
    daily = [
        {'date': day, 'level_m': round(float(median(values)), 3), 'samples': len(values)}
        for day, values in sorted(grouped.items())
    ]
    for previous, current in zip(daily, daily[1:]):
        gap = (date.fromisoformat(current['date']) - date.fromisoformat(previous['date'])).days
        if gap == 1 and abs(current['level_m'] - previous['level_m']) > 1.5:
            raise RuntimeError(
                f'Salto anômalo na telemetria: {previous["date"]} -> {current["date"]}'
            )
    return daily


def session_with_retries():
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET'],
        respect_retry_after_header=False,
    )
    session.mount('https://', HTTPAdapter(max_retries=retry))
    return session


def fetch_station(session, code, start, end):
    response = session.get(
        SOURCE_URL,
        params={
            'codEstacao': code,
            'dataInicio': start.strftime('%d/%m/%Y'),
            'dataFim': end.strftime('%d/%m/%Y'),
        },
        headers={'User-Agent': 'MPHI-Uiara/2.0-hydrologic-alpha'},
        timeout=(10, 45),
    )
    response.raise_for_status()
    observations = parse_telemetry_xml(response.text, code)
    return {
        **STATIONS[code],
        'code': code,
        'latest_timestamp': observations[-1]['timestamp'].isoformat(timespec='minutes'),
        'daily': aggregate_daily(observations),
    }


def as_map(rows, field):
    return {row['date']: float(row[field]) for row in rows if row.get(field) is not None}


def shift_day(day, offset):
    return (date.fromisoformat(day) + timedelta(days=offset)).isoformat()


def slope(series, day, window):
    previous = shift_day(day, -window)
    if day not in series or previous not in series:
        return None
    return (series[day] - series[previous]) / window


def feature_vector(day, manaus, stations):
    values = []
    for window in (3, 7):
        value = slope(manaus, day, window)
        if value is None:
            return None
        values.append(value)
    values.append(values[0] - values[1])
    for code in sorted(stations):
        for window in (3, 7):
            value = slope(stations[code], day, window)
            if value is None:
                return None
            values.append(value)
    return values


def weighted_quantile(values, weights, quantile):
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(weights)
    threshold = total * quantile
    cumulative = 0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def analog_projection(issue_date, horizon, manaus, stations):
    current = feature_vector(issue_date, manaus, stations)
    if current is None:
        raise RuntimeError('Histórico insuficiente para formar o vetor hidrológico atual.')
    samples = []
    for day in sorted(manaus):
        target = shift_day(day, horizon)
        if day >= issue_date or target not in manaus:
            continue
        features = feature_vector(day, manaus, stations)
        if features is None:
            continue
        samples.append({'date': day, 'features': features, 'change_m': manaus[target] - manaus[day]})
    if len(samples) < MIN_TRAINING_SAMPLES:
        raise RuntimeError(
            f'Apenas {len(samples)} amostras completas para o horizonte de {horizon} dias.'
        )

    columns = list(zip(*(sample['features'] for sample in samples)))
    means = [sum(column) / len(column) for column in columns]
    scales = []
    for column, mean in zip(columns, means):
        variance = sum((value - mean) ** 2 for value in column) / len(column)
        scales.append(sqrt(variance) or 1.0)

    ranked = []
    for sample in samples:
        distance = sqrt(sum(
            ((value - current_value) / scale) ** 2
            for value, current_value, scale in zip(sample['features'], current, scales)
        ) / len(current))
        ranked.append((distance, sample))
    ranked.sort(key=lambda item: item[0])
    k = min(12, max(5, round(sqrt(len(samples)))))
    neighbors = ranked[:k]
    weights = [1 / (distance + 0.10) for distance, _ in neighbors]
    changes = [sample['change_m'] for _, sample in neighbors]
    estimate = sum(change * weight for change, weight in zip(changes, weights)) / sum(weights)
    return {
        'change_m': estimate,
        'lower_change_m': weighted_quantile(changes, weights, 0.20),
        'upper_change_m': weighted_quantile(changes, weights, 0.80),
        'training_n': len(samples),
        'neighbors_n': k,
        'neighbor_dates': [sample['date'] for _, sample in neighbors],
    }


def correlation(xs, ys):
    if len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def lead_lag_audit(station, manaus, max_lag=20):
    station_delta = {
        day: value - station[shift_day(day, -1)]
        for day, value in station.items()
        if shift_day(day, -1) in station
    }
    manaus_delta = {
        day: value - manaus[shift_day(day, -1)]
        for day, value in manaus.items()
        if shift_day(day, -1) in manaus
    }
    candidates = []
    for lag in range(1, max_lag + 1):
        pairs = [
            (value, manaus_delta[target])
            for day, value in station_delta.items()
            if (target := shift_day(day, lag)) in manaus_delta
        ]
        if len(pairs) < 20:
            continue
        corr = correlation([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if corr is not None:
            candidates.append((corr, lag, len(pairs)))
    if not candidates:
        return {'status': 'insufficient', 'best_lag_days': None, 'correlation': None, 'sample_n': 0}
    corr, lag, sample_n = max(candidates)
    return {
        'status': 'exploratory' if corr < 0.30 else 'usable',
        'best_lag_days': lag,
        'correlation': round(corr, 3),
        'sample_n': sample_n,
    }


def current_base_forecast(data, forecast_ledger):
    issue_date = data['current']['date']
    candidates = [
        entry for entry in forecast_ledger.get('entries', [])
        if entry.get('forecast_date') == issue_date and entry.get('model_version') == core.SHADOW_VERSION
    ]
    if candidates:
        return candidates[-1]['projections'], core.SHADOW_VERSION
    return data['projections'], data['meta'].get('model', 'MPHI')


def build_forecast(data, station_payloads, forecast_ledger, created_at):
    issue_date = data['current']['date']
    manaus = as_map(data['series'], 'level')
    station_maps = {
        payload['code']: as_map(payload['daily'], 'level_m')
        for payload in station_payloads
    }
    base, base_version = current_base_forecast(data, forecast_ledger)
    current_level = float(data['current']['level'])
    projections = {}
    for horizon in (7, 15, 30):
        analog = analog_projection(issue_date, horizon, manaus, station_maps)
        base_projection = base[str(horizon)]
        base_change = float(base_projection['central']) - current_level
        blended_change = (1 - BLEND_WEIGHT) * base_change + BLEND_WEIGHT * analog['change_m']
        lower_change = (
            (1 - BLEND_WEIGHT) * (float(base_projection['stress']) - current_level)
            + BLEND_WEIGHT * analog['lower_change_m']
        )
        upper_change = (
            (1 - BLEND_WEIGHT) * (float(base_projection['soft']) - current_level)
            + BLEND_WEIGHT * analog['upper_change_m']
        )
        central = round(current_level + blended_change, 2)
        low = round(min(current_level + lower_change, current_level + upper_change, central), 2)
        high = round(max(current_level + lower_change, current_level + upper_change, central), 2)
        projections[str(horizon)] = {
            'target_date': shift_day(issue_date, horizon),
            'central': central,
            'soft': high,
            'stress': low,
            'interval80': {'low': low, 'high': high, 'status': 'experimental'},
            'training_n': analog['training_n'],
            'neighbors_n': analog['neighbors_n'],
            'neighbor_dates': analog['neighbor_dates'],
            'basin_weight': BLEND_WEIGHT,
        }
    station_audit = {}
    for payload in station_payloads:
        station_map = station_maps[payload['code']]
        station_audit[payload['code']] = {
            'name': payload['name'],
            'river': payload['river'],
            'role': payload['role'],
            'latest_timestamp': payload['latest_timestamp'],
            'daily_records': len(payload['daily']),
            'trend_7d_cm_per_day': round((slope(station_map, issue_date, 7) or 0) * 100, 2),
            'lead_lag': lead_lag_audit(station_map, manaus),
        }
    return {
        'forecast_id': f'{issue_date}|{MODEL_VERSION}',
        'forecast_date': issue_date,
        'created_at': created_at,
        'model_version': MODEL_VERSION,
        'model_status': 'experimental',
        'observed_level_at_issue': current_level,
        'base_model': base_version,
        'method': 'multivariate analogs from daily basin trends blended with the current MPHI baseline',
        'uses_future_information': False,
        'station_count': len(station_payloads),
        'stations': station_audit,
        'projections': projections,
    }


def summarize(records):
    if not records:
        return {'n': 0, 'mae_m': None, 'bias_m': None, 'interval_coverage_pct': None}
    return {
        'n': len(records),
        'mae_m': round(sum(abs(item['signed_error_m']) for item in records) / len(records), 3),
        'bias_m': round(sum(item['signed_error_m'] for item in records) / len(records), 3),
        'interval_coverage_pct': round(
            100 * sum(1 for item in records if item['inside_interval']) / len(records), 1
        ),
    }


def build_validation(data, ledger):
    observations = as_map(data['series'], 'level')
    records = []
    pending = {'7': 0, '15': 0, '30': 0}
    due = []
    for entry in ledger.get('entries', []):
        for horizon, projection in entry.get('projections', {}).items():
            target = projection['target_date']
            if target not in observations:
                pending[horizon] = pending.get(horizon, 0) + 1
                if target >= data['current']['date']:
                    due.append(target)
                continue
            observed = observations[target]
            signed = round(observed - projection['central'], 3)
            low = projection['interval80']['low']
            high = projection['interval80']['high']
            records.append({
                'forecast_id': entry['forecast_id'],
                'forecast_date': entry['forecast_date'],
                'target_date': target,
                'horizon_days': int(horizon),
                'forecast_central_m': projection['central'],
                'observed_m': observed,
                'signed_error_m': signed,
                'absolute_error_m': round(abs(signed), 3),
                'inside_interval': low <= observed <= high,
            })
    return {
        'forecast_count': len(ledger.get('entries', [])),
        'matured_records': len(records),
        'next_due': min(due) if due else None,
        'pending': pending,
        'by_horizon': {
            horizon: summarize([item for item in records if item['horizon_days'] == int(horizon)])
            for horizon in ('7', '15', '30')
        },
        'records': sorted(records, key=lambda item: (item['target_date'], item['forecast_date'])),
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    data = core.read_json(core.DATA, {})
    forecast_ledger = core.read_json(core.LEDGER, {'entries': []})
    ledger = core.read_json(LEDGER, {
        'schema': 'mphi-hydrologic-ledger-v1',
        'policy': 'append-only: previsões são congeladas na emissão',
        'entries': [],
    })
    issue_date = data['current']['date']
    forecast_id = f'{issue_date}|{MODEL_VERSION}'
    if any(entry.get('forecast_id') == forecast_id for entry in ledger.get('entries', [])):
        print(f'Sem alteração: previsão hidrológica de {issue_date} já está preservada.')
        return

    earliest = min(row['date'] for row in data['series'] if row.get('level') is not None)
    start = date.fromisoformat(earliest) - timedelta(days=8)
    end = date.fromisoformat(issue_date)
    session = session_with_retries()
    payloads = []
    errors = {}
    for code in STATIONS:
        try:
            payload = fetch_station(session, code, start, end)
            if len(payload['daily']) < MIN_STATION_DAYS:
                raise RuntimeError(f'apenas {len(payload["daily"])} dias disponíveis')
            latest_day = date.fromisoformat(payload['daily'][-1]['date'])
            if (end - latest_day).days > 1:
                raise RuntimeError(f'último dado diário em {latest_day.isoformat()}')
            payloads.append(payload)
        except Exception as exc:
            errors[code] = str(exc)
    if len(payloads) < MIN_STATIONS:
        raise RuntimeError(
            f'Apenas {len(payloads)} estações utilizáveis; mínimo {MIN_STATIONS}. Falhas: {errors}'
        )

    created_at = datetime.now(core.TZ).isoformat(timespec='seconds')
    forecast = build_forecast(data, payloads, forecast_ledger, created_at)
    previous_entries = list(ledger.get('entries', []))
    ledger.setdefault('entries', []).append(forecast)
    ledger['entries'].sort(key=lambda entry: (entry['forecast_date'], entry['model_version']))
    if ledger['entries'][:len(previous_entries)] != previous_entries:
        raise RuntimeError('A nova previsão alteraria o prefixo append-only do ledger hidrológico.')

    validation = build_validation(data, ledger)
    basin = {
        'schema': 'mphi-basin-signals-v1',
        'updated_at': created_at,
        'source': 'ANA/SGB - Serviço de dados hidrometeorológicos telemétricos',
        'source_url': SOURCE_URL,
        'issue_date': issue_date,
        'usable_station_count': len(payloads),
        'failed_stations': errors,
        'stations': {payload['code']: payload for payload in payloads},
    }
    latest = {
        'schema': 'mphi-hydrologic-latest-v1',
        'updated_at': created_at,
        'status': 'experimental',
        'forecast': forecast,
        'forecast_count': validation['forecast_count'],
        'validation': validation,
        'public_note': (
            'Projeção experimental orientada por sinais do Rio Negro e do Solimões. '
            'Ainda não substitui a projeção oficial.'
        ),
    }
    write_json(BASIN, basin)
    write_json(LEDGER, ledger)
    write_json(LATEST, latest)
    print(
        f'Previsão hidrológica emitida para {issue_date} com {len(payloads)} estações; '
        f'{len(previous_entries)} entradas anteriores preservadas.'
    )


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Falha no modelo hidrológico; último estado válido preservado: {exc}', file=sys.stderr)
        sys.exit(2)
