"""Offline contracts for cross-border observations; zero external network calls."""
from datetime import date
from pathlib import Path
import csv
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import crossborder_pilot as pilot

TODAY = date(2026, 11, 4)
URL = "https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico"


def peru_row(**overrides):
    row = {
        "station": "pe:tamshiyacu", "date": "2026-11-01",
        "metric": "discharge", "value": "12700", "unit": "m3/s",
        "datum": "", "source_url": URL, "source_reference": "BOLETIM-2026-11-01",
    }
    row.update(overrides)
    return row


class CrossBorderContracts(unittest.TestCase):
    def test_known_tabatinga_code_and_country(self):
        self.assertEqual(pilot.TABATINGA, "10100000")
        self.assertEqual(pilot.SOURCES[pilot.TABATINGA]["river"], "Solimoes")
        self.assertFalse(any(pilot.SOURCES[k]["country"] == "CO" for k in pilot.SOURCES))

    def test_peruvian_discharge_keeps_unit(self):
        row = pilot.normalize_peru_row(peru_row(), TODAY)
        self.assertEqual(row["unit"], "m3/s")
        self.assertEqual(row["value"], 12700)
        self.assertEqual(row["verification"], "documental_manual")

    def test_level_datum_required(self):
        with self.assertRaises(ValueError):
            pilot.normalize_peru_row(peru_row(metric="stage", unit="m", value="8.4"), TODAY)

    def test_asl_distinct_from_local_gauge(self):
        row = pilot.normalize_peru_row(peru_row(metric="stage", unit="m_asl",
                                                value="89.1", datum="sea_level"), TODAY)
        self.assertEqual(row["unit"], "m_asl")
        self.assertEqual(row["datum"], "sea_level")

    def test_unknown_station_future_date_and_nonofficial_url_rejected(self):
        for override in [
            {"station": "co:guainia"},
            {"date": "2026-11-05"},
            {"source_url": "https://evil.example.org/report"},
            {"source_url": "https://www.senamhi.gob.pe.evil.net/report"},
            {"source_reference": ""},
        ]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                pilot.normalize_peru_row(peru_row(**override), TODAY)

    def test_daily_trend_requires_exact_dates(self):
        base = peru_row()
        observations = [
            pilot.normalize_peru_row(peru_row(date=f"2026-10-{d:02d}", value=str(v)), TODAY)
            for d, v in [(25, 12500), (29, 12700)]
        ]
        observations.append(pilot.normalize_peru_row(base, TODAY))
        tracks, _ = pilot.merge_tracks({}, observations)
        signal = pilot.trend_for(next(iter(tracks.values())), TODAY)
        self.assertEqual(signal["change_3d_per_day"], round((12700 - 12700)/3, 5))
        self.assertEqual(signal["change_7d_per_day"], round((12700 - 12500)/7, 5))

    def test_conflicting_revisions_do_not_rewrite_record(self):
        old = pilot.normalize_peru_row(peru_row(value="12000"), TODAY)
        new = pilot.normalize_peru_row(peru_row(value="13000"), TODAY)
        tracks, _ = pilot.merge_tracks({}, [old])
        merged, conflicts = pilot.merge_tracks(tracks, [new])
        key = pilot.track_id(old)
        self.assertEqual(merged[key]["observations"][0]["value"], 12000)
        self.assertEqual(conflicts[0]["resolution"], "old_value_preserved")

    def test_csv_without_rows_is_valid_and_does_not_create_fake_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "in.csv"
            with file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=sorted(pilot.COLUMNS))
                writer.writeheader()
            self.assertEqual(pilot.read_peru(file, TODAY), [])
            result = pilot.build({}, [], [], TODAY, "2026-11-04T09:00:00-04:00")
            self.assertEqual(result["peru_tracks_total"], 0)
            self.assertFalse(result["affects_public_forecast"])
            self.assertEqual(result["source_status"]["senamhi_peru"]["state"],
                             "awaiting_documented_data")

    def test_duplicate_datum_is_kept_separate(self):
        a = pilot.normalize_peru_row(peru_row(metric="stage", unit="m", value="8.0",
                                              datum="local_gauge"), TODAY)
        b = pilot.normalize_peru_row(peru_row(metric="stage", unit="m_asl", value="90.0",
                                              datum="sea_level"), TODAY)
        tracks, _ = pilot.merge_tracks({}, [a, b])
        self.assertEqual(len(tracks), 2)


if __name__ == "__main__":
    unittest.main()
