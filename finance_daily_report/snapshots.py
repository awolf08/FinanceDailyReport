from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .fetchers import ReportData

SNAPSHOT_SCHEMA_VERSION = 1


def update_snapshot_file(data: ReportData, settings: Settings, snapshot_path: Path) -> list[dict[str, Any]]:
    captured_at = datetime.now(ZoneInfo(settings.timezone))
    snapshot = {
        "slot": captured_at.strftime("%H:%M"),
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "timezone": settings.timezone,
        "market_phase": data.market_phase,
        "market_status": data.market_status,
        "active_stocks": data.active_stocks,
        "active_stocks_as_of": data.active_stocks_as_of,
        "active_stocks_source": data.active_stocks_source,
        "news": data.news,
        "economic_events": data.economic_events,
        "earnings": data.earnings,
        "notes": [
            {
                "source": note.source,
                "status": note.status,
                "detail": note.detail,
            }
            for note in data.notes
        ],
    }

    document = read_snapshot_document(snapshot_path, data.report_date.isoformat())
    snapshots = document["snapshots"]
    replace_index = next((index for index, item in enumerate(snapshots) if item.get("slot") == snapshot["slot"]), None)
    if replace_index is None:
        snapshots.append(snapshot)
    else:
        snapshots[replace_index] = snapshot
    snapshots.sort(key=lambda item: item.get("captured_at", ""))

    document["snapshots"] = snapshots
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshots


def read_snapshot_document(snapshot_path: Path, report_date: str) -> dict[str, Any]:
    if not snapshot_path.exists():
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "report_date": report_date,
            "snapshots": [],
        }

    try:
        document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        document = {}

    if not isinstance(document, dict):
        document = {}
    snapshots = document.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []

    return {
        "schema_version": int(document.get("schema_version", SNAPSHOT_SCHEMA_VERSION)),
        "report_date": str(document.get("report_date") or report_date),
        "snapshots": [item for item in snapshots if isinstance(item, dict)],
    }
