from __future__ import annotations

import unittest
from datetime import date

from finance_daily_report.config import Settings
from finance_daily_report.fetchers import ReportData
from finance_daily_report.render import render_html, render_markdown


class SnapshotOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ReportData(
            report_date=date(2026, 6, 29),
            snapshots=[
                self.snapshot("2026-06-29T05:55:00-07:00"),
                self.snapshot("2026-06-29T09:55:00-07:00"),
                self.snapshot("2026-06-29T06:55:00-07:00"),
            ],
        )
        self.settings = Settings()

    @staticmethod
    def snapshot(captured_at: str) -> dict[str, object]:
        return {
            "captured_at": captured_at,
            "market_phase": "premarket",
            "market_status": {"is_open": "yes"},
            "active_stocks": {},
        }

    def test_markdown_renders_newest_snapshot_first(self) -> None:
        report = render_markdown(self.data, self.settings)

        self.assertLess(report.index("9:55 AM Premarket Snapshot"), report.index("6:55 AM Premarket Snapshot"))
        self.assertLess(report.index("6:55 AM Premarket Snapshot"), report.index("5:55 AM Premarket Snapshot"))

    def test_html_renders_newest_snapshot_first(self) -> None:
        report = render_html(self.data, self.settings)

        self.assertLess(report.index("9:55 AM Premarket Snapshot"), report.index("6:55 AM Premarket Snapshot"))
        self.assertLess(report.index("6:55 AM Premarket Snapshot"), report.index("5:55 AM Premarket Snapshot"))


if __name__ == "__main__":
    unittest.main()
