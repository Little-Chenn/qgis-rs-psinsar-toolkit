from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


DEV_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEV_ROOT))

from rs_psinsar_toolkit.timeseries_core import (
    TimeSeriesCancelled,
    descriptive_summary,
    run_timeseries_review,
)
from rs_psinsar_toolkit.timeseries_settings import (
    TimeSeriesSettings,
    controlled_sample,
    inspect_inputs,
)


class TimeSeriesReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.gpkg = self.root / "synthetic.gpkg"
        connection = sqlite3.connect(self.gpkg)
        connection.execute(
            "CREATE TABLE time_catalog (ordinal INTEGER, field_name TEXT, "
            "acquisition_date TEXT, displacement_unit TEXT, is_initial INTEGER)"
        )
        fields = [
            (0, "D_20240101", "2024-01-01", "mm", 1),
            (1, "D_20240201", "2024-02-01", "mm", 0),
            (2, "D_20240301", "2024-03-01", "mm", 0),
        ]
        connection.executemany(
            "INSERT INTO time_catalog VALUES (?,?,?,?,?)", fields
        )
        connection.execute(
            "CREATE TABLE ps_timeseries_points ("
            "fid INTEGER PRIMARY KEY, ps_uid INTEGER, source_part INTEGER, "
            "source_fid INTEGER, velocity REAL, coherence REAL, lon REAL, lat REAL, "
            "D_20240101 REAL, D_20240201 REAL, D_20240301 REAL)"
        )
        connection.executemany(
            "INSERT INTO ps_timeseries_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1, 1, 0, 0, -2.0, 0.8, 118.0, 24.5, 0.0, -1.0, -2.0),
                (2, 2, 0, 1, 3.0, 0.9, 118.1, 24.6, 0.0, 1.0, 3.0),
            ],
        )
        connection.commit()
        connection.close()
        self.points = self.root / "points.csv"
        with self.points.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["selection_rank", "ps_uid"])
            writer.writeheader()
            writer.writerows(
                [
                    {"selection_rank": 1, "ps_uid": 1},
                    {"selection_rank": 2, "ps_uid": 2},
                ]
            )

    def tearDown(self):
        self.temp.cleanup()

    def settings(self) -> TimeSeriesSettings:
        return TimeSeriesSettings(
            input_gpkg=str(self.gpkg),
            point_csv=str(self.points),
            output_root=str(self.root),
            export_csv=True,
            export_gpkg=False,
            export_png=False,
            export_pdf=False,
            load_result=False,
        )

    def test_summary(self):
        result = descriptive_summary([0.0, -1.0, 2.0])
        self.assertEqual(result["net_change_mm"], 2.0)
        self.assertEqual(result["range_mm"], 3.0)
        self.assertEqual(result["max_absolute_step_mm"], 3.0)
        self.assertEqual(result["net_change_m"], result["net_change_mm"])

    def test_inspection_and_csv_only_run(self):
        inspection = inspect_inputs(self.settings())
        self.assertEqual(inspection.selected_point_count, 2)
        self.assertEqual(len(inspection.fields), 3)
        result = run_timeseries_review(self.settings())
        self.assertEqual(result.point_count, 2)
        self.assertEqual(result.date_count, 3)
        with Path(result.artifacts["long_csv"]).open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 6)
        report = json.loads(Path(result.artifacts["qa_json"]).read_text("utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scientific_semantics"]["displacement_unit"], "mm")
        self.assertTrue(report["checks"]["unit_is_mm"])
        self.assertTrue(report["checks"]["input_gpkg_unchanged"])
        self.assertIn("displacement_mm", rows[0])
        self.assertEqual(rows[0]["displacement_mm"], rows[0]["displacement_m"])

    def test_immediate_cancel(self):
        with self.assertRaises(TimeSeriesCancelled):
            run_timeseries_review(self.settings(), is_cancelled=lambda: True)

    def test_controlled_sample_four_strata(self):
        rows = []
        strata = (
            ("A_CLUSTER", "LOW"),
            ("A_CLUSTER", "HIGH"),
            ("B_ISOLATED", "LOW"),
            ("B_ISOLATED", "HIGH"),
        )
        for group, (tier, side) in enumerate(strata):
            for index in range(2):
                rows.append(
                    {
                        "ps_uid": group * 10 + index + 1,
                        "review_tier": tier,
                        "tail_side": side,
                        "support_n": 10 - index,
                        "velocity_mm_per_year": (-1 if side == "LOW" else 1)
                        * (5 + index),
                        "coherence": 0.9,
                        "local_rz": (-1 if side == "LOW" else 1) * (3 + index),
                        "lon": 118.0 + group * 0.1,
                        "lat": 24.0 + index * 0.1,
                    }
                )
        selected = controlled_sample(rows, 1, 500.0)
        self.assertEqual(len(selected), 4)
        self.assertEqual({row["review_tier"] for row in selected}, {"A_CLUSTER", "B_ISOLATED"})


if __name__ == "__main__":
    unittest.main()
