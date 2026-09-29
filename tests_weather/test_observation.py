"""Station observation contract, freshness, and failure isolation."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import update_observation as obs

NOW = datetime(2026, 9, 29, 15, 40, tzinfo=timezone.utc)


def metar(station='SBMN', hour=15, temperature=30):
    spec = obs.STATIONS[station]
    return {'icaoId': station, 'obsTime': datetime(2026, 9, 29, hour, tzinfo=timezone.utc).timestamp(),
            'lat': spec['latitude'], 'lon': spec['longitude'], 'temp': temperature,
            'dewp': 23, 'wspd': 5, 'wdir': 170, 'cover': 'FEW', 'altim': 1013,
            'rawOb': f'METAR {station} 29{hour}00Z 17005KT FEW020 {temperature}/23 Q1013'}


class Response(BytesIO):
    status = 200
    url = obs.URL + '?ids=SBMN%2CSBEG&format=json&hours=3'


def opener(payload):
    def open_request(request, timeout):
        assert request.full_url.startswith(obs.URL + '?')
        assert timeout == 20
        return Response(json.dumps(payload).encode())
    return open_request


class Observation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def data(self, name):
        return json.loads((self.folder / ('weather_observation_' + name + '.json')).read_text())

    def test_station_temperature_beats_model_and_records_exact_metar(self):
        result = obs.update(self.folder, opener([metar('SBEG', 15, 30), metar('SBMN', 15, 31)]), NOW)
        self.assertEqual(result['state'], 'ok')
        latest = self.data('latest')
        self.assertEqual(latest['location']['station_id'], 'SBMN')
        self.assertEqual(latest['current']['temperature_c'], 31)
        self.assertEqual(latest['current']['observed_at'], '2026-09-29T15:00:00+00:00')
        self.assertEqual(latest['current']['data_type'], 'station_observation')
        self.assertIsNone(latest['current']['precipitation_accumulated_mm'])
        self.assertEqual(len(self.data('history')['entries']), 1)

    def test_fresher_secondary_station_wins_and_outdated_data_is_rejected(self):
        location, current = obs.choose([metar('SBMN', 14), metar('SBEG', 15, 32)], NOW)
        self.assertEqual((location['station_id'], current['temperature_c']), ('SBEG', 32))
        with self.assertRaises(ValueError):
            obs.choose([metar('SBMN', 12)], NOW)

    def test_repeat_and_outage_preserve_history_and_latest(self):
        valid = opener([metar()])
        obs.update(self.folder, valid, NOW)
        original = {name: (self.folder / ('weather_observation_' + name + '.json')).read_bytes()
                    for name in ('latest', 'history')}
        obs.update(self.folder, valid, NOW + timedelta(minutes=10))
        for name, content in original.items():
            self.assertEqual((self.folder / ('weather_observation_' + name + '.json')).read_bytes(), content)
        def offline(*_args, **_kwargs):
            raise TimeoutError('offline')
        self.assertEqual(obs.update(self.folder, offline, NOW + timedelta(hours=1))['state'], 'unavailable')
        for name, content in original.items():
            self.assertEqual((self.folder / ('weather_observation_' + name + '.json')).read_bytes(), content)

    def test_hydrological_files_are_never_touched(self):
        for name in ('latest.json', 'forecast_ledger.json', 'validation.json'):
            (self.folder / name).write_text('hydrology unchanged')
        obs.update(self.folder, opener([metar()]), NOW)
        for name in ('latest.json', 'forecast_ledger.json', 'validation.json'):
            self.assertEqual((self.folder / name).read_text(), 'hydrology unchanged')


if __name__ == '__main__':
    unittest.main()
