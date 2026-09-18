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
    def test_probe_recognizes_today(self):
        now = datetime(2026, 9, 18, 8, 2, tzinfo=sync.TZ)
        rows = [{'date': '2026-09-18', 'level': 21.26}]
        with patch.object(sync, 'fetch_source', return_value='page'), patch.object(
            sync, 'extract_recent_months', return_value=rows
        ):
            self.assertEqual(watcher.probe(now), (True, '2026-09-18'))

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

