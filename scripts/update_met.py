#!/usr/bin/env python3
"""MET Norway model forecast for Manaus; independent of all hydrological code."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import requests

from update_weather import DATA_DIR, LOCATION, SCHEMA, number, read, write

SOURCE = 'MET Norway · Locationforecast'
URL = 'https://api.met.no/weatherapi/locationforecast/2.0/compact'
COORDINATES = (-3.1190, -60.0217)  # Urban Manaus; not the Uiara site or the entire basin.
USER_AGENT = 'MPHI-Rio-Negro/1.0 (https://github.com/EdgeQueiroz/mphi-rio-negro)'
MANAUS = ZoneInfo('America/Manaus')
SYMBOLS = {
    'clearsky': 'Céu limpo', 'fair': 'Poucas nuvens',
    'partlycloudy': 'Parcialmente nublado', 'cloudy': 'Nublado',
    'fog': 'Nevoeiro', 'lightrain': 'Chuva fraca', 'rain': 'Chuva',
    'heavyrain': 'Chuva forte', 'lightrainshowers': 'Pancadas fracas',
    'rainshowers': 'Pancadas de chuva', 'heavyrainshowers': 'Pancadas fortes',
    'rainandthunder': 'Chuva e trovoadas', 'rainshowersandthunder': 'Pancadas e trovoadas',
}


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone_missing')
    return parsed.astimezone(timezone.utc)


def condition(code):
    if not isinstance(code, str):
        return None
    stem = code.removesuffix('_day').removesuffix('_night').removesuffix('_polartwilight')
    if stem in SYMBOLS:
        return SYMBOLS[stem]
    if 'thunder' in stem:
        return 'Trovoadas'
    if 'rain' in stem:
        return 'Chuva prevista'
    if 'cloud' in stem:
        return 'Nublado'
    return None


def direction(value):
    angle = number(value, 0, 360)
    return None if angle is None else ('N', 'NE', 'L', 'SE', 'S', 'SO', 'O', 'NO')[round(angle / 45) % 8]


def request(session, previous=None):
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', 'Accept-Encoding': 'gzip, deflate'}
    if previous:
        headers['If-Modified-Since'] = previous
    response = session.get(URL, params={'lat': COORDINATES[0], 'lon': COORDINATES[1]},
                           headers=headers, timeout=(5, 20), allow_redirects=True)
    if response.url.split('/')[2] != 'api.met.no' or not response.url.startswith('https://'):
        raise ValueError('unexpected_redirect_origin')
    if response.status_code not in (200, 203, 304):
        raise ValueError('http_' + str(response.status_code))
    return response


def normalize(payload, now):
    if not isinstance(payload, dict) or payload.get('type') != 'Feature':
        raise ValueError('invalid_geojson')
    coords = payload.get('geometry', {}).get('coordinates', [])
    if len(coords) < 2 or abs(number(coords[0], -180, 180) - COORDINATES[1]) > .02 or abs(number(coords[1], -90, 90) - COORDINATES[0]) > .02:
        raise ValueError('location_mismatch')
    properties = payload.get('properties') or {}
    meta = properties.get('meta') or {}
    issued = utc(meta['updated_at'])
    if issued > now + timedelta(minutes=15) or issued < now - timedelta(days=3):
        raise ValueError('model_issue_time_invalid')
    units = meta.get('units') or {}
    expected = {'air_temperature': 'celsius', 'relative_humidity': '%', 'wind_speed': 'm/s',
                'wind_from_direction': 'degrees', 'precipitation_amount': 'mm'}
    if any(units.get(k) != v for k, v in expected.items()):
        raise ValueError('unexpected_units')
    rows = properties.get('timeseries')
    if not isinstance(rows, list) or len(rows) < 8:
        raise ValueError('short_forecast')
    ordered = [(utc(row['time']), row['data']) for row in rows]
    if any(a[0] >= b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('unordered_forecast')
    candidates = [(t, d) for t, d in ordered if t >= now - timedelta(hours=3)]
    if not candidates or candidates[0][0] > now + timedelta(hours=3):
        raise ValueError('current_forecast_missing')
    valid, data = candidates[0]
    instant = data['instant']['details']
    temperature = number(instant.get('air_temperature'), -60, 65)
    if temperature is None:
        raise ValueError('missing_temperature')
    symbol = (data.get('next_1_hours') or data.get('next_6_hours') or {}).get('summary', {}).get('symbol_code')
    wind = number(instant.get('wind_speed'), 0, 140)
    current = {
        'data_type': 'model_forecast', 'collected_at': now.isoformat(timespec='seconds'),
        'valid_at': valid.isoformat(), 'observed_at': None, 'source_time': valid.isoformat(),
        'temperature_c': temperature, 'feels_like_c': None,
        'condition': condition(symbol), 'icon': symbol,
        'humidity_pct': number(instant.get('relative_humidity'), 0, 100),
        'wind_kmh': round(wind * 3.6, 1) if wind is not None else None,
        'wind_direction': direction(instant.get('wind_from_direction')),
        'pressure_hpa': number(instant.get('air_pressure_at_sea_level'), 800, 1100),
        'precipitation_accumulated_mm': None, 'precipitation_accumulation_period': None,
        'accumulation_note': 'Produto de previsão; não contém chuva observada.'
    }
    today = now.astimezone(MANAUS).date()
    daily = {today + timedelta(days=n): {'temperatures': [], 'rain_mm': 0.0, 'rain_intervals': 0,
                                          'condition': None, 'condition_distance': 24} for n in range(5)}
    for when, item in ordered:
        local_day = when.astimezone(MANAUS).date()
        if when >= now - timedelta(hours=3) and local_day in daily:
            temp = number(item.get('instant', {}).get('details', {}).get('air_temperature'), -60, 65)
            if temp is not None:
                daily[local_day]['temperatures'].append(temp)
            code = (item.get('next_1_hours') or item.get('next_6_hours') or {}).get('summary', {}).get('symbol_code')
            distance = abs(when.astimezone(MANAUS).hour - 14)
            if condition(code) and distance < daily[local_day]['condition_distance']:
                daily[local_day]['condition'] = condition(code)
                daily[local_day]['condition_distance'] = distance
        # Use only the shortest non-overlapping period. At the six-hour transition
        # there is no next_1_hours; split boundary intervals proportionally by time.
        period = 'next_1_hours' if 'next_1_hours' in item else 'next_6_hours' if 'next_6_hours' in item else None
        if not period or when < now - timedelta(hours=3):
            continue
        hours = 1 if period == 'next_1_hours' else 6
        raw = item[period].get('details', {}).get('precipitation_amount')
        rain = number(raw, 0, 3000)
        if rain is None:
            continue
        start, end = max(when, now), when + timedelta(hours=hours)
        if end <= start:
            continue
        cursor = start
        while cursor < end:
            date = cursor.astimezone(MANAUS).date()
            boundary = datetime.combine(date + timedelta(days=1), datetime.min.time(), MANAUS).astimezone(timezone.utc)
            segment_end = min(end, boundary)
            if date in daily:
                daily[date]['rain_mm'] += rain * (segment_end - cursor).total_seconds() / (hours * 3600)
                daily[date]['rain_intervals'] += 1
            cursor = segment_end
    days = []
    for date, info in daily.items():
        if not info['temperatures']:
            continue
        days.append({
            'date': date.isoformat(), 'min_c': min(info['temperatures']), 'max_c': max(info['temperatures']),
            'precipitation_mm': round(info['rain_mm'], 1) if info['rain_intervals'] else None,
            'rain_probability_pct': None, 'condition': info['condition'],
            'precipitation_note': 'Total estimado desde a coleta' if date == today else 'Total modelado; períodos de seis horas repartidos no limite do dia',
        })
    if len(days) < 3:
        raise ValueError('insufficient_days')
    forecast = {'data_type': 'model_forecast', 'collected_at': now.isoformat(timespec='seconds'),
                'issued_at': issued.isoformat(), 'days': days,
                'issue_time_note': 'Emissão do modelo pelo MET Norway; agregações diárias calculadas pelo MPHI.'}
    return current, forecast


def update(folder=DATA_DIR, session=None, now=None):
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    latest_path, history_path, status_path = [folder / name for name in ('weather_latest.json', 'weather_history.json', 'weather_status.json')]
    previous = read(status_path, {})
    stamp = now.isoformat(timespec='seconds')
    status = {'schema': SCHEMA, 'source': SOURCE, 'checked_at': stamp, 'state': 'unavailable',
              'errors': {}, 'stale_after_hours': 12, 'expected_interval_hours': 6}
    try:
        cache_valid = previous.get('source') == SOURCE and read(latest_path, {}).get('source') == SOURCE
        expires = previous.get('provider_expires_at') if cache_valid else None
        if expires and utc(expires) > now:
            status.update(state='ok', provider_expires_at=expires,
                          provider_last_modified=previous.get('provider_last_modified'))
        else:
            response = request(session, previous.get('provider_last_modified') if cache_valid else None)
            if response.status_code == 304:
                if not cache_valid:
                    raise ValueError('no_cached_forecast')
                status['state'] = 'ok'
            else:
                current, forecast = normalize(response.json(), now)
                latest = read(latest_path, {})
                # Do not rewrite history or roll back a newer issued forecast.
                if latest.get('source') == SOURCE and latest.get('forecast', {}).get('issued_at') and utc(forecast['issued_at']) < utc(latest['forecast']['issued_at']):
                    raise ValueError('model_regression')
                location = {**LOCATION, 'latitude': COORDINATES[0], 'longitude': COORDINATES[1]}
                snapshot = {'timestamp': stamp, 'source': SOURCE, 'location': location,
                            'current': current, 'forecast': forecast}
                snapshot['snapshot_id'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
                history = read(history_path, {'schema': SCHEMA, 'policy': 'append-only; snapshots at reception, no retrospective fill', 'entries': []})
                if not any(entry['snapshot_id'] == snapshot['snapshot_id'] for entry in history['entries']):
                    history['entries'].append(snapshot)
                    write(history_path, history)
                latest.update(source=SOURCE, location=location, current=current, forecast=forecast, updated_at=stamp)
                write(latest_path, latest)
                status['state'] = 'ok'
            # HTTP cache metadata is only valid for this same provider.
            modified = response.headers.get('Last-Modified') or previous.get('provider_last_modified')
            if modified:
                status['provider_last_modified'] = modified
            expiry = response.headers.get('Expires')
            if expiry:
                parsed = parsedate_to_datetime(expiry).astimezone(timezone.utc)
                status['provider_expires_at'] = parsed.isoformat()
    except Exception as exc:
        # Never publish provider response text, URLs or internal error details.
        status['errors']['collection'] = type(exc).__name__
    write(status_path, status)
    return status


if __name__ == '__main__':
    print('Meteorologia:', update()['state'])
