from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from finance_daily_report.fetchers import (
    TRADINGVIEW_MIN_MARKET_CAP,
    SourceNote,
    fetch_tradingview_premarket_lists,
    fetch_tradingview_premarket_rows,
)


class TradingViewPremarketTests(unittest.TestCase):
    @patch("finance_daily_report.fetchers.requests.post")
    def test_scanner_filters_market_cap_and_formats_rows(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "data": [
                {
                    "s": "NASDAQ:BIG",
                    "d": ["BIG", "Big Corp", 12.5, 10.0, 1.14, 123456, 4.0, 100_000_000, "USD"],
                },
                {
                    "s": "NASDAQ:SMALL",
                    "d": ["SMALL", "Small Corp", 20.0, 20.0, 3.33, 999999, 8.0, 99_999_999, "USD"],
                },
            ]
        }
        post.return_value = response

        rows = fetch_tradingview_premarket_rows(
            limit=8,
            sort_by="premarket_change",
            sort_order="desc",
            change_operation="greater",
            change_threshold=0,
        )

        self.assertEqual([row["symbol"] for row in rows], ["BIG"])
        self.assertEqual(rows[0]["lastSalePrice"], "$12.50")
        self.assertEqual(rows[0]["changePercent"], "+10.00%")
        self.assertEqual(rows[0]["marketCap"], "$100.0M")
        request_payload = post.call_args.kwargs["json"]
        self.assertIn(
            {"left": "market_cap_basic", "operation": "egreater", "right": TRADINGVIEW_MIN_MARKET_CAP},
            request_payload["filter"],
        )

    @patch("finance_daily_report.fetchers.fetch_tradingview_premarket_rows")
    def test_lists_include_three_premarket_rankings(self, fetch_rows: Mock) -> None:
        fetch_rows.return_value = [{"symbol": "BIG"}]
        notes: list[SourceNote] = []

        result, as_of = fetch_tradingview_premarket_lists(8, notes)

        self.assertEqual(
            list(result),
            ["Most Active Stocks", "Top Gaining Stocks", "Top Declining Stocks"],
        )
        self.assertIn("TradingView premarket scan as of", as_of)
        self.assertEqual(fetch_rows.call_count, 3)
        self.assertTrue(all(note.status == "ok" for note in notes))


if __name__ == "__main__":
    unittest.main()
