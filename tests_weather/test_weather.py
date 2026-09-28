"""Offline provider contracts; never touch the production MPHI data."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import copy
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import update_weather as weather
import update_mphi as core
import sync_mphi as hydro

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
# Synthetic fixtures based on official Advisor v1 field contracts, not live data.
CITY = {'id': 123, 'name': 'Manaus', 'state': 'AM', 'country': 'BR'}
CURRENT = {**CITY, 'data': {'date': '2026-09-28 08:00:00', 'temperature': 29,
    'sensation': 33, 'humidity': 80, 'wind_velocity': 8, 'wind_direction': 'NE',
    'condition': 'Sol com nuvens', 'pressure': 1005, 'icon': '2'}}
FORECAST = {**CITY, 'data': [{'date': f'2026-09-{day:02d}', 'temperature': {'min': 25, 'max': 34},
    'rain': {'probability': 0 if day == 28 else 70, 'precipitation': 0 if day == 28 else 12},
    'text_icon': {'text': {'pt': 'Pancadas de chuva'}, 'icon': {'day': '4'}}} for day in (28, 29, 30)]}
ENV = {'CLIMATEMPO_TOKEN': 'fixture-secret-never-publish', 'CLIMATEMPO_LOCALE_ID': '123'}


def fake_get(session, route, token, **kwargs):
    return copy.deepcopy(CURRENT if '/weather/' in route else FORECAST if '/forecast/' in route else [CITY])


class WeatherContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def run_update(self, provider=fake_get, env=None, now=NOW):
        with patch.object(weather, 'get', side_effect=provider):
            return weather.update(self.folder, ENV if env is None else env, now=now)
    def payload(self, name):
        return json.loads((self.folder / name).read_text())
    def test_no_key_never_calls_provider(self):
        self.assertEqual(self.run_update(provider=AssertionError('should not call'), env={})['state'], 'not_configured')
        self.assertFalse((self.folder / 'weather_latest.json').exists())
    def test_official_contract_zero_missing_units_and_no_secret(self):
        self.assertEqual(self.run_update()['state'], 'ok')
        data = self.payload('weather_latest.json')
        self.assertEqual(data['current']['temperature_c'], 29)
        self.assertEqual(data['current']['wind_kmh'], 8)
        self.assertEqual(data['forecast']['days'][0]['rain_probability_pct'], 0)
        self.assertIsNone(data['current']['precipitation_accumulated_mm'])
        self.assertIsNone(data['current']['observed_at'])
        self.assertIsNone(data['forecast']['issued_at'])
        for p in self.folder.glob('*.json'):
            self.assertNotIn(ENV['CLIMATEMPO_TOKEN'], p.read_text())
    def test_total_failure_and_key_removal_preserve_valid_bytes(self):
        self.run_update()
        before = {p.name: p.read_bytes() for p in self.folder.glob('*.json') if p.name != 'weather_status.json'}
        state = self.run_update(provider=RuntimeError('https://provider?token='+ENV['CLIMATEMPO_TOKEN']))
        self.assertEqual(state['state'], 'unavailable')
        self.assertNotIn(ENV['CLIMATEMPO_TOKEN'], json.dumps(state))
        for name, data in before.items(): self.assertEqual((self.folder/name).read_bytes(), data)
        self.run_update(env={})
        for name, data in before.items(): self.assertEqual((self.folder/name).read_bytes(), data)
    def test_partial_failure_preserves_failed_section_and_logs_only_received(self):
        self.run_update()
        old = self.payload('weather_latest.json')['forecast']
        def partial(session, route, token, **kwargs):
            if '/forecast/' in route: raise TimeoutError('provider down')
            return fake_get(session, route, token)
        self.assertEqual(self.run_update(partial, now=NOW+timedelta(hours=6))['state'], 'partial')
        self.assertEqual(self.payload('weather_latest.json')['forecast'], old)
        self.assertIsNone(self.payload('weather_history.json')['entries'][-1]['forecast'])
    def test_first_collection_can_be_forecast_only(self):
        def provider(session, route, token, **kwargs):
            if '/weather/' in route: raise TimeoutError()
            return fake_get(session, route, token)
        self.assertEqual(self.run_update(provider)['state'], 'partial')
        self.assertIsNone(self.payload('weather_latest.json')['current'])
    def test_history_append_only_idempotent_and_no_backfill(self):
        self.run_update(); first = self.payload('weather_history.json')['entries']
        self.run_update(); self.assertEqual(self.payload('weather_history.json')['entries'], first)
        self.run_update(now=NOW+timedelta(hours=6))
        entries = self.payload('weather_history.json')['entries']
        self.assertEqual(entries[:len(first)], first); self.assertEqual(len(entries), 2)
    def test_city_lookup_requires_exact_manaus(self):
        self.assertEqual(self.run_update(env={'CLIMATEMPO_TOKEN': 'fixture'})['state'], 'ok')
        other = copy.deepcopy(CURRENT); other['state'] = 'SP'
        with self.assertRaises(ValueError): weather.normalize_current(other, 123, NOW)
    def test_schema_and_unrealistic_values_fail(self):
        for bad in (None, {}, {'data': []}):
            with self.assertRaises((ValueError, TypeError)): weather.normalize_current(bad, 123, NOW)
        for n in (float('nan'), -1, 101, 'bad'):
            c=copy.deepcopy(CURRENT);c['data']['humidity']=n
            with self.assertRaises(ValueError): weather.normalize_current(c, 123, NOW)
    def test_explicit_timezone_is_preserved_and_future_rejected(self):
        c=weather.normalize_current(CURRENT,123,NOW,'America/Manaus')
        self.assertEqual(c['observed_at'],'2026-09-28T08:00:00-04:00')
        data=copy.deepcopy(CURRENT);data['data']['date']='2026-09-29T08:00:00-04:00'
        with self.assertRaises(ValueError): weather.normalize_current(data,123,NOW)
    def test_regression_rejected_without_erasing_last_observation(self):
        self.run_update(); before=self.payload('weather_latest.json')['current']
        def provider(session,route,token,**kwargs):
            result=fake_get(session,route,token)
            if '/weather/' in route: result['data']['date']='2026-09-27 08:00:00'
            return result
        self.assertEqual(self.run_update(provider)['state'],'partial')
        self.assertEqual(self.payload('weather_latest.json')['current'],before)
    def test_forecast_dates_duplicates_and_empty_response(self):
        f=copy.deepcopy(FORECAST);f['data'].append(f['data'][0])
        with self.assertRaises(ValueError): weather.normalize_forecast(f,123,NOW)
        with self.assertRaises(ValueError): weather.normalize_forecast(FORECAST,123,NOW+timedelta(days=20))
    def test_requests_stay_https_bounded_and_do_not_redirect(self):
        session=Mock();session.get.return_value.status_code=200;session.get.return_value.json.return_value=CURRENT
        weather.get(session,'/weather/locale/123/current','fixture')
        args,kw=session.get.call_args
        self.assertTrue(args[0].startswith('https://apiadvisor.climatempo.com.br/api/v1/'))
        self.assertFalse(kw['allow_redirects']);self.assertEqual(kw['timeout'],(5,15))
        session.get.return_value.status_code=302
        with self.assertRaises(ValueError): weather.get(session,'/test','fixture')
    def test_weather_writes_no_hydrological_files(self):
        for name in ('latest.json','forecast_ledger.json','validation.json','hydrologic_ledger.json'):
            (self.folder/name).write_text('unchanged')
        for provider in (fake_get,TimeoutError('unavailable')):
            self.run_update(provider)
            for name in ('latest.json','forecast_ledger.json','validation.json','hydrologic_ledger.json'):
                self.assertEqual((self.folder/name).read_text(),'unchanged')
    def test_hydrological_update_works_with_weather_unavailable(self):
        # Exercise the real hydro entry point with a new observation in isolation.
        for name in ('latest.json','forecast_ledger.json','validation.json'):
            (self.folder/name).write_bytes((core.DATA.parent/name).read_bytes())
        seed=self.payload('latest.json');old_entries=self.payload('forecast_ledger.json')['entries']
        rows=copy.deepcopy(seed['series'])
        rows.append({'date':core.add_days(seed['current']['date'],1),'level':round(seed['current']['level']-.1,2),'delta_cm':-10,'source':'Porto de Manaus'})
        self.run_update(provider=TimeoutError('no weather'))
        with patch.object(core,'DATA',self.folder/'latest.json'),patch.object(core,'LEDGER',self.folder/'forecast_ledger.json'),patch.object(core,'VALIDATION',self.folder/'validation.json'),patch.object(hydro,'STATUS',self.folder/'status.json'),patch.object(hydro,'fetch_source',return_value='fixture'),patch.object(hydro,'extract_recent_months',return_value=rows):
            hydro.main()
        self.assertEqual(self.payload('latest.json')['current']['date'],rows[-1]['date'])
        self.assertEqual(self.payload('forecast_ledger.json')['entries'][:len(old_entries)],old_entries)

if __name__=='__main__': unittest.main()
