"""Contracts for the prospective basin-oriented MPHI challenger."""
from datetime import date, timedelta
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hydrologic_v2 as hydro


def day(start, offset):
    return (start + timedelta(days=offset)).isoformat()


class HydrologicV2Contracts(unittest.TestCase):
    def test_parser_and_daily_aggregation(self):
        xml = '''<?xml version="1.0"?>
        <DataTable><DocumentElement>
          <DadosHidrometereologicos><CodEstacao>14100000</CodEstacao><DataHora>2026-09-01 00:00:00 </DataHora><Nivel>1200.00</Nivel></DadosHidrometereologicos>
          <DadosHidrometereologicos><CodEstacao>14100000</CodEstacao><DataHora>2026-09-01 12:00:00 </DataHora><Nivel>1210.00</Nivel></DadosHidrometereologicos>
          <DadosHidrometereologicos><CodEstacao>14100000</CodEstacao><DataHora>2026-09-02 00:00:00 </DataHora><Nivel>1190.00</Nivel></DadosHidrometereologicos>
        </DocumentElement></DataTable>'''
        observations = hydro.parse_telemetry_xml(xml, '14100000')
        daily = hydro.aggregate_daily(observations)
        self.assertEqual(len(observations), 3)
        self.assertEqual(daily[0], {'date': '2026-09-01', 'level_m': 12.05, 'samples': 2})
        self.assertEqual(daily[1]['level_m'], 11.9)

    def test_lead_lag_audit_recovers_known_delay(self):
        start = date(2026, 1, 1)
        station = {}
        manaus = {}
        station_level = 10.0
        manaus_level = 20.0
        changes = [math.sin(i / 3) * 0.05 + math.cos(i / 7) * 0.02 for i in range(90)]
        for i in range(90):
            station_level += changes[i]
            if i >= 4:
                manaus_level += changes[i - 4]
            station[day(start, i)] = station_level
            manaus[day(start, i)] = manaus_level
        audit = hydro.lead_lag_audit(station, manaus, max_lag=10)
        self.assertEqual(audit['best_lag_days'], 4)
        self.assertGreater(audit['correlation'], 0.95)

    def test_analog_forecast_uses_only_prior_dates(self):
        start = date(2026, 1, 1)
        manaus = {}
        stations = {code: {} for code in hydro.STATIONS}
        manaus_level = 25.0
        station_levels = {code: 10.0 + index for index, code in enumerate(stations)}
        for i in range(150):
            movement = -0.015 + math.sin(i / 8) * 0.008
            manaus_level += movement
            current_day = day(start, i)
            manaus[current_day] = manaus_level
            for index, code in enumerate(stations):
                station_levels[code] += movement * (0.8 + index * 0.05) + math.cos(i / 11) * 0.001
                stations[code][current_day] = station_levels[code]
        issue = day(start, 149)
        result = hydro.analog_projection(issue, 15, manaus, stations)
        self.assertGreaterEqual(result['training_n'], hydro.MIN_TRAINING_SAMPLES)
        self.assertTrue(all(candidate < issue for candidate in result['neighbor_dates']))
        self.assertLess(result['change_m'], 0)

    def test_build_forecast_keeps_public_baseline_separate(self):
        start = date(2026, 1, 1)
        series = []
        station_payloads = []
        manaus_level = 26.0
        station_levels = {code: 12.0 + index for index, code in enumerate(hydro.STATIONS)}
        station_rows = {code: [] for code in hydro.STATIONS}
        for i in range(150):
            movement = -0.012 + math.sin(i / 9) * 0.006
            manaus_level += movement
            current_day = day(start, i)
            series.append({'date': current_day, 'level': round(manaus_level, 3), 'delta_cm': round(movement * 100, 2)})
            for index, code in enumerate(hydro.STATIONS):
                station_levels[code] += movement * (0.75 + index * 0.05)
                station_rows[code].append({'date': current_day, 'level_m': station_levels[code], 'samples': 24})
        issue = series[-1]['date']
        data = {
            'current': {'date': issue, 'level': series[-1]['level']},
            'series': series,
            'projections': {
                '7': {'soft': 24.3, 'central': 24.2, 'stress': 24.1},
                '15': {'soft': 23.4, 'central': 23.2, 'stress': 23.0},
                '30': {'soft': 22.0, 'central': 21.7, 'stress': 21.4},
            },
            'meta': {'model': 'MPHI v1.0'},
        }
        for code, config in hydro.STATIONS.items():
            station_payloads.append({
                'code': code,
                **config,
                'latest_timestamp': issue + 'T12:00',
                'daily': station_rows[code],
            })
        forecast = hydro.build_forecast(data, station_payloads, {'entries': []}, issue + 'T12:00:00-04:00')
        self.assertEqual(forecast['forecast_date'], issue)
        self.assertEqual(forecast['station_count'], 5)
        self.assertEqual(set(forecast['projections']), {'7', '15', '30'})
        self.assertTrue(forecast['uses_future_information'] is False)
        for projection in forecast['projections'].values():
            self.assertLessEqual(projection['stress'], projection['central'])
            self.assertGreaterEqual(projection['soft'], projection['central'])


if __name__ == '__main__':
    unittest.main()
