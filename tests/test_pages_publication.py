"""Publication contracts: skip duplicate deploys, retain real error signals."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pages_publication as pages

NOW = datetime(2026, 10, 9, 19, tzinfo=timezone.utc)


def snapshot():
    data = {name: {'records': []} for name in pages.FILES}
    data['latest.json'] = {'current': {'date': '2026-10-09', 'level': 17.92}}
    data['status.json'] = {
        'state': 'current', 'observation_date': '2026-10-09',
        'data_updated_at': '2026-10-09T08:01:06-04:00',
        'checked_at': '2026-10-09T14:49:00-04:00',
    }
    return data


def source(data):
    session = Mock()

    def get(url, **kwargs):
        response = Mock()
        response.json.return_value = data[url.rsplit('/', 1)[1]]
        return response

    session.get.side_effect = get
    return session


class PagesContracts(unittest.TestCase):
    def test_same_day_measurement_with_different_check_time_skips_deploy(self):
        expected = snapshot()
        published = copy.deepcopy(expected)
        published['status.json']['checked_at'] = '2026-10-09T08:01:06-04:00'
        session = source(published)
        needed, _ = pages.publication_needed(expected, session=session, now=NOW)
        self.assertFalse(needed)
        self.assertEqual(session.get.call_count, len(pages.FILES))
        pages.check_published(expected, session=session, now=NOW)

    def test_changes_to_any_model_ledger_or_validation_require_publication(self):
        for name in pages.FILES:
            if name == 'status.json':
                continue
            with self.subTest(file=name):
                expected = snapshot()
                published = copy.deepcopy(expected)
                published[name]['unexpected'] = True
                self.assertTrue(pages.publication_needed(expected, session=source(published), now=NOW)[0])
                with self.assertRaises(ValueError):
                    pages.check_published(expected, session=source(published), now=NOW)

    def test_waiting_heartbeat_stays_strict(self):
        expected = snapshot()
        expected['status.json'].update(state='waiting', observation_date='2026-10-08')
        published = copy.deepcopy(expected)
        published['status.json']['checked_at'] = '2026-10-09T08:01:06-04:00'
        self.assertTrue(pages.publication_needed(expected, session=source(published), now=NOW)[0])

    def test_source_error_requires_publication_and_is_not_ignored(self):
        expected = snapshot()
        published = copy.deepcopy(expected)
        published['status.json']['state'] = 'error'
        self.assertTrue(pages.publication_needed(expected, session=source(published), now=NOW)[0])
        with self.assertRaises(ValueError):
            pages.check_published(expected, session=source(published), now=NOW)

    def test_latest_error_heartbeat_is_not_ignored(self):
        expected = snapshot()
        expected['status.json']['state'] = 'error'
        published = copy.deepcopy(expected)
        published['status.json']['checked_at'] = '2026-10-09T08:01:06-04:00'
        self.assertTrue(pages.publication_needed(expected, session=source(published), now=NOW)[0])

    def test_bad_old_or_future_check_times_are_rejected(self):
        for stamp in ('invalid', None, '2026-10-08T08:00:00-04:00',
                      '2026-10-09T08:00:00', '2026-10-10T08:00:00-04:00'):
            with self.subTest(stamp=stamp):
                expected = snapshot()
                published = copy.deepcopy(expected)
                published['status.json']['checked_at'] = stamp
                with self.assertRaises(ValueError):
                    pages.check_published(expected, session=source(published), now=NOW)

    def test_http_failure_or_unavailable_page_requests_recovery(self):
        for error in (requests.Timeout(), requests.HTTPError()):
            session = Mock()
            session.get.side_effect = error
            self.assertTrue(pages.publication_needed(snapshot(), session=session, now=NOW)[0])

    def test_frontend_push_and_explicit_recovery_always_publish(self):
        session = Mock()
        self.assertTrue(pages.publication_needed(snapshot(), session=session, now=NOW, force=True)[0])
        session.get.assert_not_called()

    def test_site_with_yesterdays_measurement_is_recovered(self):
        published = snapshot()
        published['latest.json']['current']['date'] = '2026-10-08'
        self.assertTrue(pages.publication_needed(snapshot(), session=source(published), now=NOW)[0])

    def test_verification_uses_unique_queries_and_no_cache(self):
        session = source(snapshot())
        pages.check_published(snapshot(), session=session, now=NOW)
        calls = session.get.call_args_list
        self.assertEqual(len({c.kwargs['params']['verify'] for c in calls}), len(pages.FILES))
        self.assertTrue(all('no-store' in c.kwargs['headers']['Cache-Control'] for c in calls))


if __name__ == '__main__':
    unittest.main()
