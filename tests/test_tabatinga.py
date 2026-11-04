"""Tests for the isolated Tabatinga observation and source-failure contracts."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_tabatinga as tab


NOW = datetime(2026, 11, 4, 9, 23, tzinfo=tab.TZ)


def row(day, level, station="10100000", hour="08:00:00"):
    return (f"<DadosHidrometereologicos><CodEstacao>{station}</CodEstacao>"
            f"<DataHora>{day} {hour}</DataHora><Nivel>{level}</Nivel>"
            f"</DadosHidrometereologicos>")


def xml(*rows):
    return ("<root>" + "".join(rows) + "</root>").encode()


class TabatingaContracts(unittest.TestCase):
    def test_valid_negative_and_zero_levels_are_retained_in_metres(self):
        rows = tab.parse_observations(xml(row("2026-11-04", "-234"),
                                          row("2026-11-04", "0", hour="09:00:00")),
                                      NOW.date())
        self.assertEqual([r["level_m"] for r in rows], [-2.34, 0])
        self.assertEqual(tab.aggregate(rows)[0]["level_m"], -1.17)

    def test_wrong_station_future_and_invalid_sentinels_do_not_create_readings(self):
        rows = tab.parse_observations(xml(row("2026-11-04", "123"),
                                          row("2026-11-05", "200"),
                                          row("2026-11-04", "300", station="14100000"),
                                          row("2026-11-04", "-99999", hour="09:00:00"),
                                          row("2026-11-04", "NaN", hour="10:00:00")), NOW.date())
        self.assertEqual(rows, [{"date": "2026-11-04", "level_m": 1.23}])

    def test_no_matching_data_and_conflicting_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            tab.parse_observations(xml(row("2026-11-04", "123", station="14100000")), NOW.date())
        with self.assertRaises(ValueError):
            tab.parse_observations(xml(row("2026-11-04", "123"), row("2026-11-04", "124")), NOW.date())

    def test_changes_require_observations_on_exact_reference_days(self):
        rows = [{"date": "2026-10-28", "level_m": -2.0},
                {"date": "2026-11-01", "level_m": -1.5},
                {"date": "2026-11-04", "level_m": -1.0}]
        result = tab.build_success(tab.empty_snapshot(), rows, NOW)
        self.assertEqual(result["changes_cm"], {"3d": 50.0, "7d": 100.0})
        missing = tab.build_success(tab.empty_snapshot(), [rows[0], rows[2]], NOW)
        self.assertIsNone(missing["changes_cm"]["3d"])
        self.assertEqual(missing["changes_cm"]["7d"], 100.0)

    def test_partial_day_is_a_median_and_reports_number_of_readings(self):
        rows = [{"date": "2026-11-04", "level_m": value} for value in (1.0, 2.0, 10.0)]
        latest = tab.build_success(tab.empty_snapshot(), rows, NOW)["latest"]
        self.assertEqual(latest, {"date": "2026-11-04", "level_m": 2.0, "samples": 3})

    def test_stale_source_and_regression_are_distinguished(self):
        rows = [{"date": "2026-10-30", "level_m": 1.0}]
        stale = tab.build_success(tab.empty_snapshot(), rows, NOW)
        self.assertEqual(stale["source_status"], "stale")
        previous = tab.empty_snapshot()
        previous["latest"] = {"date": "2026-11-03", "level_m": 1.2, "samples": 1}
        with self.assertRaises(ValueError):
            tab.build_success(previous, rows, NOW)

    def test_source_failure_keeps_last_reading_and_marks_unavailable(self):
        previous = tab.build_success(tab.empty_snapshot(),
                                     [{"date": "2026-11-04", "level_m": -1.25}], NOW)
        failed = tab.build_failure(previous, NOW + timedelta(hours=1), TimeoutError())
        self.assertEqual(failed["latest"], previous["latest"])
        self.assertEqual(failed["daily"], previous["daily"])
        self.assertEqual(failed["source_status"], "unavailable")
        self.assertEqual(failed["error"], "TimeoutError")

    def test_collection_failure_writes_only_the_requested_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tabatinga.json"
            before = tab.build_success(tab.empty_snapshot(),
                                       [{"date": "2026-11-04", "level_m": -1.25}], NOW)
            tab.write_snapshot(output, before)
            with patch.object(sys, "argv", ["collect_tabatinga.py", "--output", str(output)]), \
                 patch.object(tab, "fetch_observations", side_effect=TimeoutError()):
                self.assertEqual(tab.main(), 0)
            after = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(after["latest"], before["latest"])
            self.assertEqual(after["source_status"], "unavailable")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["tabatinga.json"])

    def test_incompatible_existing_snapshot_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tabatinga.json"
            output.write_text('{"schema": "unknown"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                tab.read_snapshot(output)
            self.assertEqual(output.read_text(encoding="utf-8"), '{"schema": "unknown"}')

    def test_transient_timeout_is_retried_before_accepting_real_observations(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = xml(row("2026-11-04", "-234"))
        with patch.object(tab, "urlopen", side_effect=[TimeoutError(), response]) as request, \
             patch.object(tab.time, "sleep") as wait:
            rows, used = tab.fetch_observations(NOW.date())
        self.assertEqual(rows[0]["level_m"], -2.34)
        self.assertEqual(used, tab.SOURCE_URL)
        self.assertEqual(request.call_count, 2)
        wait.assert_called_once_with(1)

    def test_official_fallback_records_actual_source(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = xml(row("2026-11-04", "317"))
        with patch.object(tab, "urlopen", side_effect=[TimeoutError(), TimeoutError(), response]), \
             patch.object(tab.time, "sleep"):
            rows, used = tab.fetch_observations(NOW.date())
        result = tab.build_success(tab.empty_snapshot(), rows, NOW, used)
        self.assertEqual(result["source"]["url"], tab.FALLBACK_SOURCE_URL)
        self.assertEqual(result["latest"]["level_m"], 3.17)

    def test_persistent_timeout_stops_after_four_attempts_across_both_endpoints(self):
        with patch.object(tab, "urlopen", side_effect=TimeoutError()) as request, \
             patch.object(tab.time, "sleep"):
            with self.assertRaises(TimeoutError):
                tab.fetch_observations(NOW.date())
        self.assertEqual(request.call_count, 4)


if __name__ == "__main__":
    unittest.main()
