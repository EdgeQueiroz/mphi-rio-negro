"""Contratos da vigília residente e da leitura sem cache."""

from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_mphi as sync
import wait_for_porto as watcher


class ResidentWatcherContracts(unittest.TestCase):
    def test_sync_today_requires_persisted_day(self):
        now = datetime(2026, 9, 18, 8, 2, tzinfo=sync.TZ)
        with patch.object(sync, 'main') as run, patch.object(
            sync.core, 'read_json', return_value={'current': {'date': '2026-09-18'}}
        ):
            self.assertEqual(watcher.sync_today(now), (True, '2026-09-18'))
            run.assert_called_once_with()
        with patch.object(sync, 'main'), patch.object(
            sync.core, 'read_json', return_value={'current': {'date': '2026-09-17'}}
        ):
            self.assertEqual(watcher.sync_today(now), (False, '2026-09-17'))

    def test_cutoff_is_strict(self):
        before = datetime(2026, 9, 18, 12, 14, tzinfo=sync.TZ)
        at_cutoff = datetime(2026, 9, 18, 12, 15, tzinfo=sync.TZ)
        self.assertTrue(watcher.before_cutoff(before, 12, 15))
        self.assertFalse(watcher.before_cutoff(at_cutoff, 12, 15))

    def test_fetch_uses_unique_cache_buster(self):
        response = Mock(text='page')
        session = Mock()
        session.get.return_value = response
        with patch.object(sync.requests, 'Session', return_value=session), patch.object(
            sync.time, 'time_ns', return_value=123456
        ):
            self.assertEqual(sync.fetch_source(), 'page')
        kwargs = session.get.call_args.kwargs
        self.assertEqual(kwargs['params'], {'mphi_sync': 123456})
        self.assertIn('no-store', kwargs['headers']['Cache-Control'])
        self.assertEqual(kwargs['headers']['Pragma'], 'no-cache')


if __name__ == '__main__':
    unittest.main()
