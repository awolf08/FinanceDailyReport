from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from finance_daily_report.config import Settings
from finance_daily_report.fetchers import ReportData
from finance_daily_report.snapshots import update_snapshot_file


class SnapshotSlotTests(unittest.TestCase):
    def test_configured_snapshot_slot_overrides_capture_minute(self) -> None:
        data = ReportData(report_date=date(2026, 7, 16), market_phase="regular")
        settings = Settings(snapshot_slot="07:59")

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshots = update_snapshot_file(data, settings, Path(temp_dir) / "report.snapshots.json")

        self.assertEqual(snapshots[0]["slot"], "07:59")
        self.assertIn("captured_at", snapshots[0])


if __name__ == "__main__":
    unittest.main()
