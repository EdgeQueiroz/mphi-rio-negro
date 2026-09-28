#!/usr/bin/env python3
"""Climatempo Advisor context. Deliberately imports no MPHI model code."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import hashlib
import json
import math
import os
import re
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'docs' / 'data'
BASE = 'https://apiadvisor.climatempo.com.br/api/v1'
SOURCE = 'Climatempo Advisor'
LOCATION = {'name': 'Manaus', 'state': 'AM', 'country': 'BR', 'timezone': 'America/Manaus'}
SCHEMA = 'mphi-weather-v1'


def read(path, fallback):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def number(value, low, high):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError('invalid_numeric_field') from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError('numeric_field_out_of_range')
    return value


def string(value):
    return value[:200] if isinstance(value, str) else None


def get(session, route, token, **params):
    # No redirects: credentials must stay on the fixed official HTTPS origin.
    response = session.get(BASE + route, params={'token': token, **params},
                           timeout=(5, 15), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError('http_' + str(response.status_code))
    payload = response.json()
    if isinstance(payload, dict) and payload.get('error'):
        raise ValueError('provider_error')
    return payload


def location_id(session, token, configured):
    if configured:
        if not re.fullmatch(r'\d+', configured):
            raise ValueError('invalid_locale_id')
        return int(configured)
    cities = get(session, '/locale/city', token, name='Manaus', state='AM', country='BR')
    matches = [x for x in cities if isinstance(x, dict) and x.get('name', '').casefold() == 'manaus'
               and x.get('state') == 'AM' and x.get('country') == 'BR'] if isinstance(cities, list) else []
    if len(matches) != 1 or not isinstance(matches[0].get('id'), int):
        raise ValueError('locale_not_resolved')
    return matches[0]['id']


def validate_location(payload, locale):
    if not isinstance(payload, dict) or str(payload.get('id')) != str(locale) or payload.get('name', '').casefold() != 'manaus' or payload.get('state') != 'AM' or payload.get('country') != 'BR':
        raise ValueError('location_mismatch')


def normalize_current(payload, locale, now, source_timezone=''):
    validate_location(payload, locale)
    d = payload['data']
    if not isinstance(d, dict):
        raise ValueError('invalid_current')
    stamp = string(d.get('date'))
    if not stamp:
        raise ValueError('missing_observation_time')
    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    # Public v1 docs do not specify the timezone of naive timestamps.
    # Never silently claim UTC/Manaus: keep original time until confirmed.
    if parsed.tzinfo is None and source_timezone:
        parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
    observed_at = parsed.isoformat() if parsed.tzinfo else None
    if parsed.tzinfo and parsed > now + timedelta(minutes=15):
        raise ValueError('future_observation')
    temperature = number(d.get('temperature'), -60, 65)
    if temperature is None:
        raise ValueError('missing_temperature')
    return {
        'collected_at': now.isoformat(timespec='seconds'),
        'source_time': stamp, 'source_timezone': source_timezone or None,
        'observed_at': observed_at,
        'temperature_c': temperature, 'feels_like_c': number(d.get('sensation'), -80, 85),
        'condition': string(d.get('condition')), 'icon': string(d.get('icon')),
        'humidity_pct': number(d.get('humidity'), 0, 100),
        'wind_kmh': number(d.get('wind_velocity'), 0, 500),
        'wind_direction': string(d.get('wind_direction')),
        'pressure_hpa': number(d.get('pressure'), 800, 1100),
        'precipitation_accumulated_mm': None,
        'precipitation_accumulation_period': None,
        'accumulation_note': 'Acumulado observado não fornecido pelo contrato current v1.'
    }


def normalize_forecast(payload, locale, now):
    validate_location(payload, locale)
    if not isinstance(payload.get('data'), list):
        raise ValueError('invalid_forecast')
    today = now.astimezone(ZoneInfo('America/Manaus')).date()
    days = {}
    for d in payload['data']:
        day = datetime.fromisoformat(d['date']).date()
        if not today <= day <= today + timedelta(days=4):
            continue
        rain, temp = d.get('rain') or {}, d.get('temperature') or {}
        icons = d.get('text_icon') or {}
        values = {
            'date': day.isoformat(),
            'min_c': number(temp.get('min'), -60, 65), 'max_c': number(temp.get('max'), -60, 65),
            'precipitation_mm': number(rain.get('precipitation'), 0, 3000),
            'rain_probability_pct': number(rain.get('probability'), 0, 100),
            'condition': string((icons.get('text') or {}).get('pt')),
            'icon': string((icons.get('icon') or {}).get('day')),
            'humidity_min_pct': number((d.get('humidity') or {}).get('min'), 0, 100),
            'humidity_max_pct': number((d.get('humidity') or {}).get('max'), 0, 100),
            'wind_avg_kmh': number((d.get('wind') or {}).get('velocity_avg'), 0, 500),
            'wind_direction': string((d.get('wind') or {}).get('direction')),
        }
        if values['min_c'] is not None and values['max_c'] is not None and values['min_c'] > values['max_c']:
            raise ValueError('inverted_temperature_range')
        if all(values[k] is None for k in ('min_c', 'max_c', 'precipitation_mm', 'rain_probability_pct')):
            raise ValueError('empty_forecast_day')
        if values['date'] in days:
            raise ValueError('duplicate_forecast_date')
        days[values['date']] = values
    if not days:
        raise ValueError('expired_or_empty_forecast')
    return {'collected_at': now.isoformat(timespec='seconds'), 'issued_at': None,
            'issue_time_note': 'Horário de emissão não fornecido; collected_at é o recebimento.',
            'days': [days[k] for k in sorted(days)]}


def update(folder=DATA_DIR, env=None, session=None, now=None):
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    stamp = now.isoformat(timespec='seconds')
    folder.mkdir(parents=True, exist_ok=True)
    latest_path, history_path, status_path = [folder / name for name in ('weather_latest.json', 'weather_history.json', 'weather_status.json')]
    status = {'schema': SCHEMA, 'source': SOURCE, 'checked_at': stamp, 'state': 'not_configured',
              'errors': {}, 'stale_after_hours': 12, 'expected_interval_hours': 6}
    token = env.get('CLIMATEMPO_TOKEN', '').strip()
    if not token:
        write(status_path, status)
        return status
    latest = read(latest_path, {'schema': SCHEMA, 'source': SOURCE, 'location': LOCATION, 'current': None, 'forecast': None})
    received = {}
    try:
        locale = location_id(session, token, env.get('CLIMATEMPO_LOCALE_ID', '').strip())
        for kind, route, normalizer in (
            ('current', f'/weather/locale/{locale}/current', lambda p: normalize_current(p, locale, now, env.get('CLIMATEMPO_SOURCE_TIMEZONE', ''))),
            ('forecast', f'/forecast/locale/{locale}/days/15', lambda p: normalize_forecast(p, locale, now)),
        ):
            try:
                part = normalizer(get(session, route, token))
                old = latest.get(kind)
                if kind == 'current' and old and part['source_time'] < old['source_time']:
                    raise ValueError('observation_regression')
                received[kind] = part
            except Exception as exc:
                # Do not serialize exception text: HTTP errors can contain a token URL.
                status['errors'][kind] = type(exc).__name__
        if received:
            snapshot = {'timestamp': stamp, 'source': SOURCE, 'location': {**LOCATION, 'locale_id': locale},
                        'current': received.get('current'), 'forecast': received.get('forecast')}
            snapshot['snapshot_id'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
            history = read(history_path, {'schema': SCHEMA, 'policy': 'append-only; snapshots at reception, no retrospective fill', 'entries': []})
            if not any(x['snapshot_id'] == snapshot['snapshot_id'] for x in history['entries']):
                history['entries'].append(snapshot)
                write(history_path, history)
            latest.update(received)
            latest['location'] = snapshot['location']
            latest['updated_at'] = stamp
            write(latest_path, latest)
    except Exception as exc:
        status['errors']['collection'] = type(exc).__name__
    status['state'] = 'ok' if len(received) == 2 and not status['errors'] else 'partial' if received else 'unavailable'
    write(status_path, status)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    try:
        result = update(args.data_dir)
        print('Meteorologia:', result['state'])
    except Exception:
        # Filesystem problems must not expose HTTP details or secrets either.
        print('Meteorologia: falha interna; último arquivo válido preservado.')
        raise SystemExit(1)
