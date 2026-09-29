#!/usr/bin/env python3
"""Hourly Manaus station observations, isolated from the hydrological model."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import math
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from update_weather import DATA_DIR, number, read, write

URL = 'https://aviationweather.gov/api/data/metar'
SOURCE = 'NOAA Aviation Weather Center · METAR'
USER_AGENT = 'MPHI-Rio-Negro/1.0 (https://github.com/EdgeQueiroz/mphi-rio-negro)'
SCHEMA = 'mphi-weather-observation-v1'
STATIONS = {
    'SBMN': {'name': 'Ponta Pelada', 'latitude': -3.146, 'longitude': -59.986},
    'SBEG': {'name': 'Eduardo Gomes', 'latitude': -3.039, 'longitude': -60.050},
}


def condition(row):
    code = (row.get('wxString') or '').upper()
    if 'TS' in code:
        return 'Trovoadas'
    if 'RA' in code or 'DZ' in code:
        return 'Chuva'
    return {'CLR': 'Céu limpo', 'SKC': 'Céu limpo', 'FEW': 'Poucas nuvens',
            'SCT': 'Parcialmente nublado', 'BKN': 'Nublado', 'OVC': 'Nublado'}.get(row.get('cover'))


def humidity(temperature, dewpoint):
    if dewpoint is None:
        return None
    # Magnus formula: derived relative humidity, not a station humidity sensor.
    value = 100 * math.exp((17.625 * dewpoint / (243.04 + dewpoint)) -
                           (17.625 * temperature / (243.04 + temperature)))
    return round(min(100, max(0, value)))


def direction(angle):
    if angle == 'VRB':
        return 'variável'
    if angle is None:
        return None
    degrees = number(angle, 0, 360)
    return ('N', 'NE', 'L', 'SE', 'S', 'SO', 'O', 'NO')[round(degrees / 45) % 8]


def normalize_row(row, now):
    if not isinstance(row, dict) or row.get('icaoId') not in STATIONS:
        raise ValueError('unexpected_station')
    station = row['icaoId']
    expected = STATIONS[station]
    if (abs(number(row.get('lat'), -90, 90) - expected['latitude']) > .03 or
            abs(number(row.get('lon'), -180, 180) - expected['longitude']) > .03):
        raise ValueError('station_location_mismatch')
    observed = datetime.fromtimestamp(number(row.get('obsTime'), 0, 4102444800), timezone.utc)
    if observed > now + timedelta(minutes=15) or observed < now - timedelta(hours=2):
        raise ValueError('observation_outside_freshness_window')
    raw = row.get('rawOb')
    if not isinstance(raw, str) or not raw.startswith(('METAR ' + station + ' ', 'SPECI ' + station + ' ')):
        raise ValueError('invalid_metar')
    temperature = number(row.get('temp'), -20, 55)
    if temperature is None:
        raise ValueError('missing_station_temperature')
    dewpoint = number(row.get('dewp'), -30, 40)
    if dewpoint is not None and dewpoint > temperature + 1:
        raise ValueError('invalid_dewpoint')
    knots = number(row.get('wspd'), 0, 200)
    location = {'name': 'Manaus', 'state': 'AM', 'country': 'BR', 'timezone': 'America/Manaus',
                'station_id': station, 'station_name': expected['name'],
                'latitude': expected['latitude'], 'longitude': expected['longitude']}
    current = {'data_type': 'station_observation', 'observed_at': observed.isoformat(),
               'temperature_c': temperature, 'dewpoint_c': dewpoint,
               'feels_like_c': None, 'humidity_pct': humidity(temperature, dewpoint),
               'humidity_method': 'Magnus, a partir do ponto de orvalho' if dewpoint is not None else None,
               'condition': condition(row), 'wind_kmh': round(knots * 1.852, 1) if knots is not None else None,
               'wind_direction': direction(row.get('wdir')), 'pressure_hpa': number(row.get('altim'), 800, 1100),
               'precipitation_accumulated_mm': None, 'raw_metar': raw[:500]}
    return location, current


def request(opener=None):
    url = URL + '?' + urlencode({'ids': 'SBMN,SBEG', 'format': 'json', 'hours': 3})
    req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with (opener or urlopen)(req, timeout=20) as response:
        final = urlsplit(response.url)
        if final.scheme != 'https' or final.hostname != 'aviationweather.gov':
            raise ValueError('unexpected_response_origin')
        if response.status != 200:
            raise ValueError('http_' + str(response.status))
        return json.load(response)


def choose(payload, now):
    if not isinstance(payload, list):
        raise ValueError('invalid_metar_payload')
    valid = []
    for row in payload:
        try:
            location, current = normalize_row(row, now)
            valid.append((datetime.fromisoformat(current['observed_at']),
                          location['station_id'] == 'SBMN', location, current))
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    if not valid:
        raise ValueError('no_recent_station_observation')
    _, _, location, current = max(valid, key=lambda item: (item[0], item[1]))
    return location, current


def update(folder=DATA_DIR, opener=None, now=None):
    now = now or datetime.now(timezone.utc)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    latest_path = folder / 'weather_observation_latest.json'
    history_path = folder / 'weather_observation_history.json'
    status_path = folder / 'weather_observation_status.json'
    stamp = now.isoformat(timespec='seconds')
    status = {'schema': SCHEMA, 'source': SOURCE, 'checked_at': stamp, 'state': 'unavailable',
              'errors': {}, 'stale_after_hours': 2, 'expected_interval_hours': 1}
    try:
        location, current = choose(request(opener), now)
        previous = read(latest_path, {})
        old = previous.get('current') or {}
        if old.get('observed_at') and datetime.fromisoformat(old['observed_at']) > datetime.fromisoformat(current['observed_at']):
            raise ValueError('observation_regression')
        current['collected_at'] = stamp
        snapshot = {'timestamp': stamp, 'source': SOURCE, 'location': location, 'current': current}
        snapshot['snapshot_id'] = hashlib.sha256((location['station_id'] + current['observed_at'] + current['raw_metar']).encode()).hexdigest()
        history = read(history_path, {'schema': SCHEMA, 'policy': 'append-only; station observation at reception', 'entries': []})
        if not any(e.get('snapshot_id') == snapshot['snapshot_id'] for e in history['entries']):
            history['entries'].append(snapshot)
            write(history_path, history)
            write(latest_path, {'schema': SCHEMA, 'source': SOURCE, 'location': location,
                                'current': current, 'updated_at': stamp})
        status.update(state='ok', observed_at=current['observed_at'], station_id=location['station_id'])
    except Exception as exc:
        # Preserve the last valid observation and all prior history on failure.
        status['errors']['collection'] = type(exc).__name__
    write(status_path, status)
    return status


if __name__ == '__main__':
    print('Observação Manaus:', update()['state'])
