import unittest

import pandas as pd

from scrape import build_rows, split_integer_evenly
from process_tesla_data import build_tesla_daily_records, build_tesla_monthly_records
from scrape_tesla import parse_tesla_baseline


class ReliabilityTests(unittest.TestCase):
    def test_integer_split_preserves_total(self):
        self.assertEqual(split_integer_evenly(5, 2), [2, 3])
        self.assertEqual(sum(split_integer_evenly(204_728_837, 2)), 204_728_837)

    def test_gap_is_backfilled_evenly_and_marked_estimated(self):
        source = pd.DataFrame([{
            "date": "2026-08-05",
            "assist_total": 13_644_906_124,
            "drive_total": 39_471_872_929,
            "estimated": False,
        }])

        _, rows = build_rows(
            source,
            "2026-08-07",
            13_731_017_657,
            39_676_601_766,
        )

        self.assertEqual([row["date"] for row in rows], ["2026-08-06", "2026-08-07"])
        self.assertEqual([row["daily_assist"] for row in rows], [43_055_766, 43_055_767])
        self.assertEqual([row["daily_drive"] for row in rows], [102_364_418, 102_364_419])
        self.assertTrue(all(row["estimated"] for row in rows))
        self.assertEqual(rows[-1]["assist_total"], 13_731_017_657)
        self.assertEqual(rows[-1]["drive_total"], 39_676_601_766)

    def test_normal_next_day_is_not_estimated(self):
        source = pd.DataFrame([{
            "date": "2026-08-07",
            "assist_total": 100,
            "drive_total": 200,
            "estimated": True,
        }])

        _, rows = build_rows(source, "2026-08-08", 110, 225)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["estimated"])

    def test_force_replacement_keeps_existing_estimate_marker(self):
        source = pd.DataFrame([
            {
                "date": "2026-08-06",
                "assist_total": 50,
                "drive_total": 100,
                "estimated": True,
            },
            {
                "date": "2026-08-07",
                "assist_total": 100,
                "drive_total": 200,
                "estimated": True,
            },
        ])

        _, rows = build_rows(source, "2026-08-07", 102, 204)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["estimated"])

    def test_tesla_baseline_series_and_monthly_average(self):
        source = pd.DataFrame([
            {"date": "2026-10-31", "base_fsd_miles": 1_000, "base_time_utc": "2026-10-01T00:00:00Z", "average_daily_fsd_km": 100},
            {"date": "2026-11-01", "base_fsd_miles": 1_100, "base_time_utc": "2026-11-01T00:00:00Z", "average_daily_fsd_km": 120},
            {"date": "2026-11-02", "base_fsd_miles": 1_200, "base_time_utc": "2026-11-02T00:00:00Z", "average_daily_fsd_km": 150},
        ])
        daily = build_tesla_daily_records(source)
        monthly = build_tesla_monthly_records(daily)

        self.assertEqual([row["average_daily_fsd_km"] for row in daily], [100, 120, 150])
        self.assertEqual(monthly[0]["average_daily_fsd_km"], 100)
        self.assertEqual(monthly[1]["average_daily_fsd_km"], 135)

    def test_parses_tesla_server_baseline(self):
        baseline = parse_tesla_baseline("""
          const totalMilesStart = 16485475664;
          const startEpochTime = new Date('2026-10-22T08:14:00Z').getTime();
          const totalDistancePerMillisecondAdded = useKm ? (22 / 42) * KM_PER_MILE : 22 / 42;
        """)
        self.assertEqual(baseline["base_fsd_miles"], 16_485_475_664)
        self.assertEqual(baseline["base_time_utc"], "2026-10-22T08:14:00Z")
        self.assertAlmostEqual(baseline["average_daily_fsd_km"], 72_834_130.29, places=2)


if __name__ == "__main__":
    unittest.main()
