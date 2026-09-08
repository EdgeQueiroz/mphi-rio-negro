"""Contract checks: time provenance, missing days, source errors and immutable forecasts."""
import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_mphi as sync
import update_mphi as core

SEED = json.loads(core.DATA.read_text())
NOW = datetime(2026, 9, 6, 8, 0, tzinfo=sync.TZ)


def html(month, year, rows):
    return f'<h2>{month} {year}</h2><table><tr><th>Dia</th><th>Cota</th><th>Variação</th></tr>' + ''.join(
        f'<tr><td>{day}</td><td>{level}</td><td>{delta}</td></tr>' for day, level, delta in rows
    ) + '</table>'


class SyncContracts(unittest.TestCase):
    def test_weekend_keeps_friday_and_rejects_future_rows(self):
        rows = sync.extract_recent_months(html('Setembro', 2026, [(4, '23,65', '-15'), (7, '23,20', '-15')]), NOW)
        self.assertEqual([r['date'] for r in rows], ['2026-09-04'])

    def test_month_boundary_without_new_table(self):
        now = datetime(2026, 10, 1, 8, tzinfo=sync.TZ)
        rows = sync.extract_recent_months(html('Setembro', 2026, [(30, '20,00', '-10')]), now)
        self.assertEqual(rows[-1]['date'], '2026-09-30')

    def test_previous_month_backfill(self):
        page = html('Agosto', 2026, [(31, '24,19', '-10')]) + html('Setembro', 2026, [(1, '24,09', '-10')])
        self.assertEqual(len(sync.extract_recent_months(page, NOW)), 2)

    def test_january_rollover(self):
        now = datetime(2027, 1, 1, 8, tzinfo=sync.TZ)
        rows = sync.extract_recent_months(html('Dezembro', 2026, [(31, '20,00', '10')]), now)
        self.assertEqual(rows[-1]['date'], '2026-12-31')

    def test_invalid_source_fails(self):
        with self.assertRaises(RuntimeError):
            sync.extract_recent_months('<h1>Site indisponível</h1>', NOW)

    def test_gap_does_not_create_observations(self):
        d = copy.deepcopy(SEED)
        d['series'] = [{'date': '2026-09-04', 'level': 23.65, 'delta_cm': -15, 'source': 'Porto de Manaus'}]
        sync.sync_month(d, [{'date': '2026-09-07', 'level': 23.2, 'delta_cm': -45, 'source': 'Porto de Manaus'}], NOW)
        self.assertEqual([r['date'] for r in d['series']], ['2026-09-04', '2026-09-07'])
        self.assertEqual(core.persistence_days(d['series'], d), 1)

    def test_anomalous_jump_rejected(self):
        d = {'series': [{'date': '2026-09-03', 'level': 23.8}]}
        with self.assertRaises(RuntimeError):
            sync.sync_month(d, [{'date': '2026-09-04', 'level': 30}], NOW)

    def run_isolated(self, rows=None, error=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = {name: folder / name for name in ('latest.json', 'forecast_ledger.json', 'validation.json', 'status.json')}
            for name in ('latest.json', 'forecast_ledger.json', 'validation.json'):
                paths[name].write_bytes((core.DATA.parent / name).read_bytes())
            before = {name: path.read_bytes() for name, path in paths.items() if path.exists()}
            with patch.object(core, 'DATA', paths['latest.json']), patch.object(core, 'LEDGER', paths['forecast_ledger.json']), patch.object(core, 'VALIDATION', paths['validation.json']), patch.object(sync, 'STATUS', paths['status.json']), patch.object(sync, 'fetch_source', side_effect=error, return_value='fixture'), patch.object(sync, 'extract_recent_months', return_value=rows):
                if error:
                    with self.assertRaises(SystemExit): sync.main()
                else:
                    sync.main()
            return before, {name: path.read_bytes() for name, path in paths.items() if path.exists()}

    def test_unchanged_source_preserves_data_timestamp_and_ledger(self):
        rows = [copy.deepcopy(r) for r in SEED['series'] if r.get('level') is not None]
        before, after = self.run_isolated(rows)
        for name in before: self.assertEqual(before[name], after[name])
        self.assertEqual(json.loads(after['status.json'])['data_updated_at'], SEED['meta']['updated_at'])
        self.assertIsNone(json.loads(after['status.json'])['source_published_at'])

    def test_source_error_only_changes_status(self):
        before, after = self.run_isolated(error=RuntimeError('Porto unavailable'))
        for name in before: self.assertEqual(before[name], after[name])
        self.assertEqual(json.loads(after['status.json'])['state'], 'error')

    def test_new_measurement_updates_snapshot_and_appends_one_forecast(self):
        rows = [copy.deepcopy(r) for r in SEED['series'] if r.get('level') is not None]
        new_date = core.add_days(SEED['current']['date'], 1)
        rows.append({'date': new_date, 'level': round(SEED['current']['level'] - .1, 2),
                     'delta_cm': -10, 'source': 'Porto de Manaus'})
        before, after = self.run_isolated(rows)
        old_ledger = json.loads(before['forecast_ledger.json'])['entries']
        new_ledger = json.loads(after['forecast_ledger.json'])['entries']
        self.assertEqual(new_ledger[:len(old_ledger)], old_ledger)
        self.assertEqual(len(new_ledger), len(old_ledger) + 1)
        self.assertEqual(json.loads(after['latest.json'])['current']['date'], new_date)
        self.assertEqual(json.loads(after['status.json'])['observation_date'], new_date)

    def test_backfill_reports_total_change_without_overwriting_daily_delta(self):
        rows = [copy.deepcopy(r) for r in SEED['series'] if r.get('level') is not None]
        start = SEED['current']['date']
        level = SEED['current']['level']
        for days, drop, delta in [(1, .15, -15), (2, .30, -15), (3, .46, -16), (4, .63, -17)]:
            rows.append({'date': core.add_days(start, days), 'level': round(level-drop, 2),
                         'delta_cm': delta, 'source': 'Porto de Manaus'})
        before, after = self.run_isolated(rows)
        result = json.loads(after['latest.json'])
        change = result['meta']['change_since_previous_publication']
        self.assertEqual(change['change_cm'], -63)
        self.assertEqual(change['elapsed_days'], 4)
        self.assertEqual(change['average_cm_per_day'], -15.75)
        self.assertEqual(result['current']['delta_cm'], -17)
        self.assertEqual(result['current']['avg3'], -16)
        old_entries = json.loads(before['forecast_ledger.json'])['entries']
        new_entries = json.loads(after['forecast_ledger.json'])['entries']
        self.assertEqual(new_entries[:len(old_entries)], old_entries)
        self.assertEqual(len(new_entries), len(old_entries)+1)

    def test_forecast_is_not_rewritten(self):
        d = copy.deepcopy(SEED); ledger = {'entries': []}
        core.freeze_forecast(d, ledger); original = copy.deepcopy(ledger)
        d['projections']['7']['central'] = 1
        self.assertFalse(core.freeze_forecast(d, ledger))
        self.assertEqual(ledger, original)


if __name__ == '__main__':
    unittest.main()
