"""Independent modeled-weather contract and provider switching tests."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_weather
import update_met as met

NOW = datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc)


def fixture():
    rows = []
    for n in range(5 * 24 + 1):
        when = datetime(2026, 9, 28, 14, tzinfo=timezone.utc) + timedelta(hours=n)
        rows.append({'time': when.isoformat().replace('+00:00', 'Z'), 'data': {
            'instant': {'details': {'air_temperature': 30, 'relative_humidity': 76,
                                     'wind_speed': 2, 'wind_from_direction': 90,
                                     'air_pressure_at_sea_level': 1010}},
            **({'next_1_hours': {'summary': {'symbol_code': 'rainshowers_day'},
                                 'details': {'precipitation_amount': 1.0}}} if n < 5 * 24 else {})}})
    return {'type': 'Feature', 'geometry': {'coordinates': [-60.0217, -3.119, 45]},
            'properties': {'meta': {'updated_at': '2026-09-28T13:00:00Z',
                                    'units': {'air_temperature': 'celsius', 'relative_humidity': '%',
                                              'wind_speed': 'm/s', 'wind_from_direction': 'degrees',
                                              'precipitation_amount': 'mm'}}, 'timeseries': rows}}


def response(payload=None, code=200, headers=None):
    mock = Mock(status_code=code, url=met.URL, headers=headers or {})
    mock.json.return_value = fixture() if payload is None else payload
    return mock


class ModelForecast(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.session = Mock()
        self.session.get.return_value = response()

    def tearDown(self):
        self.temp.cleanup()

    def data(self, name):
        return json.loads((self.folder / name).read_text())

    def test_no_key_collects_and_labels_modeled_source(self):
        with patch.object(met.requests, 'Session', return_value=self.session):
            state = collect_weather.collect(self.folder, env={}, now=NOW)
        self.assertEqual(state['state'], 'ok')
        latest = self.data('weather_latest.json')
        self.assertEqual(latest['source'], met.SOURCE)
        self.assertEqual(latest['current']['temperature_c'], 30)
        self.assertEqual(latest['current']['wind_kmh'], 7.2)
        self.assertEqual(latest['current']['wind_direction'], 'L')
        self.assertEqual(latest['current']['data_type'], 'model_forecast')
        self.assertIsNone(latest['current']['observed_at'])
        self.assertIsNone(latest['current']['feels_like_c'])
        self.assertIsNone(latest['current']['precipitation_accumulated_mm'])
        self.assertIsNone(latest['forecast']['days'][0]['rain_probability_pct'])
        self.assertEqual(len(latest['forecast']['days']), 5)
        args, kwargs = self.session.get.call_args
        self.assertEqual(args[0], met.URL)
        self.assertIn('github.com/EdgeQueiroz/mphi-rio-negro', kwargs['headers']['User-Agent'])
        self.assertEqual(kwargs['params'], {'lat': -3.119, 'lon': -60.0217})

    def test_failure_keeps_previous_data_and_history(self):
        met.update(self.folder, self.session, NOW)
        before = {name: (self.folder / name).read_bytes() for name in ('weather_latest.json', 'weather_history.json')}
        self.session.get.side_effect = TimeoutError('provider unavailable')
        self.assertEqual(met.update(self.folder, self.session, NOW + timedelta(hours=6))['state'], 'unavailable')
        for name, saved in before.items():
            self.assertEqual((self.folder / name).read_bytes(), saved)

    def test_304_reuses_forecast_without_append_or_request_before_expiry(self):
        headers = {'Last-Modified': 'Mon, 28 Sep 2026 13:00:00 GMT', 'Expires': 'Mon, 28 Sep 2026 16:00:00 GMT'}
        self.session.get.return_value = response(headers=headers)
        met.update(self.folder, self.session, NOW)
        before = self.data('weather_history.json')['entries']
        self.assertEqual(met.update(self.folder, self.session, NOW + timedelta(minutes=10))['state'], 'ok')
        self.assertEqual(self.session.get.call_count, 1)
        self.session.get.return_value = response(code=304, headers={'Last-Modified': headers['Last-Modified']})
        self.assertEqual(met.update(self.folder, self.session, NOW + timedelta(hours=2))['state'], 'ok')
        self.assertEqual(self.session.get.call_args.kwargs['headers']['If-Modified-Since'], headers['Last-Modified'])
        self.assertEqual(self.data('weather_history.json')['entries'], before)

    def test_mismatched_location_units_and_stale_model_are_rejected(self):
        for change in ('location', 'unit', 'stale'):
            payload = fixture()
            if change == 'location': payload['geometry']['coordinates'][0] = -59
            if change == 'unit': payload['properties']['meta']['units']['wind_speed'] = 'km/h'
            if change == 'stale': payload['properties']['meta']['updated_at'] = '2026-09-01T00:00:00Z'
            with self.assertRaises(ValueError): met.normalize(payload, NOW)

    def test_rain_periods_split_across_manaus_midnight_and_today_is_remaining(self):
        current, forecast = met.normalize(fixture(), NOW)
        self.assertLess(forecast['days'][0]['precipitation_mm'], 24)
        self.assertEqual(forecast['days'][1]['precipitation_mm'], 24)
        self.assertEqual(forecast['days'][0]['precipitation_note'], 'Total estimado desde a coleta')
        self.assertEqual(current['condition'], 'Pancadas de chuva')

    def test_climatempo_token_uses_official_source_first(self):
        with patch.object(collect_weather, 'climatempo', return_value={'state': 'ok'}) as official, patch.object(collect_weather, 'met_norway') as fallback:
            self.assertEqual(collect_weather.collect(self.folder, env={'CLIMATEMPO_TOKEN': 'synthetic'})['state'], 'ok')
        official.assert_called_once()
        fallback.assert_not_called()

    def test_climatempo_failure_uses_met_fallback(self):
        with patch.object(collect_weather, 'climatempo', return_value={'state': 'unavailable'}), patch.object(collect_weather, 'met_norway', return_value={'state': 'ok'}) as fallback:
            self.assertEqual(collect_weather.collect(self.folder, env={'CLIMATEMPO_TOKEN': 'synthetic'})['state'], 'ok')
        fallback.assert_called_once()

    def test_hydrology_untouched(self):
        for name in ('latest.json', 'forecast_ledger.json', 'validation.json'):
            (self.folder / name).write_text('hydrology preserved')
        met.update(self.folder, self.session, NOW)
        for name in ('latest.json', 'forecast_ledger.json', 'validation.json'):
            self.assertEqual((self.folder / name).read_text(), 'hydrology preserved')


if __name__ == '__main__':
    unittest.main()
