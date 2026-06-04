from __future__ import annotations

import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings
from .fetchers import ReportData


def render_markdown(data: ReportData, settings: Settings) -> str:
    today = data.report_date
    tomorrow = today + timedelta(days=1)
    generated_at = format_generated_at(settings)
    lines: list[str] = [
        f"# Finance Daily Report - {today.isoformat()}",
        "",
        f"_Generated: {generated_at}. Timezone: {settings.timezone}. Not financial advice._",
        "",
        "## Market Status",
        "",
        format_market_status(data),
        "",
        "## 1. Intraday Active Stock Snapshots",
        "",
    ]

    append_snapshot_markdown(lines, data)

    lines.extend(["## 2. Latest Market News", ""])
    if data.news:
        for item in data.news:
            published = f" ({item['published']})" if item.get("published") else ""
            link = item.get("link", "")
            title = item["title"]
            source = item.get("source", "News")
            priority = "High priority | " if int(item.get("priority_score", "0")) >= 4 else ""
            if link:
                lines.append(f"- **{source}**{published}: {priority}[{title}]({link})")
            else:
                lines.append(f"- **{source}**{published}: {priority}{title}")
    else:
        lines.append("- No news items returned.")
    lines.append("")

    lines.extend(["## 3. Economic Calendar", ""])
    append_economic_day(lines, f"Today ({today.isoformat()})", data.economic_events.get("today", []))
    append_economic_day(lines, f"Tomorrow ({tomorrow.isoformat()})", data.economic_events.get("tomorrow", []))

    lines.extend(["## 4. After-hours Earnings", ""])
    append_earnings_group(lines, f"Today after close ({today.isoformat()})", data.earnings.get("today", []), "time-after-hours")
    append_earnings_group(lines, f"Tomorrow before open ({tomorrow.isoformat()})", data.earnings.get("tomorrow", []), "time-pre-market")
    append_earnings_group(lines, f"Other scheduled earnings ({today.isoformat()} to {tomorrow.isoformat()})", data.earnings.get("today", []) + data.earnings.get("tomorrow", []), "")

    lines.extend(["## Source Health", ""])
    for note in data.notes:
        detail = f" - {note.detail}" if note.detail else ""
        lines.append(f"- {note.source}: {note.status}{detail}")
    lines.append("")

    return "\n".join(lines)


def render_html(data: ReportData, settings: Settings) -> str:
    today = data.report_date
    tomorrow = today + timedelta(days=1)
    generated_at = format_generated_at(settings)
    title = f"Finance Daily Report - {today.isoformat()}"
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
        "<style>",
        "body{margin:0;background:#f6f7f9;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45}",
        ".wrap{max-width:980px;margin:0 auto;padding:28px 18px 44px}",
        "header{border-bottom:3px solid #1b4d89;padding-bottom:16px;margin-bottom:22px}",
        "h1{font-size:30px;margin:0 0 8px;color:#102a43}",
        "h2{font-size:20px;margin:28px 0 12px;color:#183b56;border-bottom:1px solid #d9e2ec;padding-bottom:6px}",
        "h3{font-size:16px;margin:18px 0 8px;color:#334e68}",
        ".meta{color:#627d98;font-size:14px}",
        ".status{background:#fff;border-left:5px solid #1b4d89;padding:12px 14px;margin:12px 0;border-radius:6px}",
        "ul{margin:8px 0 18px;padding-left:20px}",
        "li{margin:7px 0}",
        "a{color:#0b63ce;text-decoration:none}",
        "a:hover{text-decoration:underline}",
        ".section{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px 18px;margin:14px 0}",
        ".source-health{font-size:13px;color:#52616f}",
        ".priority{font-weight:700;color:#8a4b00}",
        "</style>",
        "</head>",
        "<body>",
        '<main class="wrap">',
        "<header>",
        f"<h1>{escape(title)}</h1>",
        f'<div class="meta">Generated: {escape(generated_at)}. Timezone: {escape(settings.timezone)}. Not financial advice.</div>',
        "</header>",
        "<h2>Market Status</h2>",
        f'<div class="status">{inline_markdown(format_market_status(data).lstrip("- "))}</div>',
        "<h2>1. Intraday Active Stock Snapshots</h2>",
    ]

    append_snapshot_html(parts, data)

    parts.extend(["<h2>2. Latest Market News</h2>", '<div class="section"><ul>'])
    if data.news:
        for item in data.news:
            parts.append(render_news_html(item))
    else:
        parts.append("<li>No news items returned.</li>")
    parts.extend(["</ul>", "</div>"])

    parts.append("<h2>3. Economic Calendar</h2>")
    append_economic_html(parts, f"Today ({today.isoformat()})", data.economic_events.get("today", []))
    append_economic_html(parts, f"Tomorrow ({tomorrow.isoformat()})", data.economic_events.get("tomorrow", []))

    parts.append("<h2>4. After-hours Earnings</h2>")
    append_earnings_html(parts, f"Today after close ({today.isoformat()})", data.earnings.get("today", []), "time-after-hours")
    append_earnings_html(parts, f"Tomorrow before open ({tomorrow.isoformat()})", data.earnings.get("tomorrow", []), "time-pre-market")
    append_earnings_html(parts, f"Other scheduled earnings ({today.isoformat()} to {tomorrow.isoformat()})", data.earnings.get("today", []) + data.earnings.get("tomorrow", []), "")

    parts.extend(["<h2>Source Health</h2>", '<div class="section source-health"><ul>'])
    for note in data.notes:
        detail = f" - {note.detail}" if note.detail else ""
        parts.append(f"<li>{escape(note.source)}: {escape(note.status)}{escape(detail)}</li>")
    parts.extend(["</ul>", "</div>", "</main>", "</body>", "</html>"])
    return "\n".join(parts)


def render_news_html(item: dict[str, str]) -> str:
    published = f" ({item['published']})" if item.get("published") else ""
    source = item.get("source", "News")
    title = item["title"]
    link = item.get("link", "")
    priority = '<span class="priority">High priority | </span>' if int(item.get("priority_score", "0")) >= 4 else ""
    if link:
        title_html = f'<a href="{escape_attr(link)}">{escape(title)}</a>'
    else:
        title_html = escape(title)
    return f"<li><strong>{escape(source)}</strong>{escape(published)}: {priority}{title_html}</li>"


def format_generated_at(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")


def append_economic_html(parts: list[str], title: str, events: list[dict[str, str]]) -> None:
    parts.extend(['<div class="section">', f"<h3>{escape(title)}</h3>", "<ul>"])
    if not events:
        parts.append("<li>No major events returned by configured sources.</li>")
    for event in events:
        time = event.get("time") or "Time N/A"
        name = event.get("event") or "Unnamed event"
        details = []
        if event.get("forecast"):
            details.append(f"Forecast: {event['forecast']}")
        if event.get("previous"):
            details.append(f"Previous: {event['previous']}")
        if event.get("source"):
            details.append(f"Source: {event['source']}")
        suffix = f" | {' | '.join(details)}" if details else ""
        parts.append(f"<li><strong>{escape(time)}</strong> {escape(name)}{escape(suffix)}</li>")
    parts.extend(["</ul>", "</div>"])


def append_earnings_html(parts: list[str], title: str, rows: list[dict[str, str]], time_filter: str) -> None:
    filtered_rows = filter_earnings(rows, time_filter)
    parts.extend(['<div class="section">', f"<h3>{escape(title)}</h3>", "<ul>"])
    if not filtered_rows:
        parts.append("<li>No earnings returned.</li>")
    for row in filtered_rows:
        symbol = row.get("symbol", "")
        name = row.get("name", "")
        when = row.get("time", "")
        eps = row.get("epsForecast", "")
        quarter = row.get("fiscalQuarterEnding", "")
        parts.append(f"<li><strong>{escape(symbol)}</strong> {escape(name)} | Time: {escape(when or 'N/A')} | EPS est: {escape(eps or 'N/A')} | Quarter: {escape(quarter or 'N/A')}</li>")
    parts.extend(["</ul>", "</div>"])


def inline_markdown(value: str) -> str:
    escaped = escape(value)
    return escaped.replace("**", "<strong>", 1).replace("**", "</strong>", 1)


def escape(value: str) -> str:
    return html.escape(str(value), quote=False)


def escape_attr(value: str) -> str:
    return html.escape(str(value), quote=True)


def format_market_status(data: ReportData) -> str:
    status = data.market_status
    label = status.get("label", "Market status unavailable")
    reason = status.get("reason", "")
    if status.get("is_open") == "yes":
        return f"- **{label}.** {reason}."
    if reason:
        return f"- **{label}.** {reason}."
    return f"- **{label}.**"


def format_stock_detail(section: str, row: dict[str, str]) -> str:
    change = row.get("change", "")
    if section in {"Most Active", "After-Hours Most Active"}:
        return f"Volume: {format_number(change)}" if change else "Volume: N/A"
    return f"Change %: {change or 'N/A'}"


def format_number(value: str) -> str:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return value
    return f"{number:,.0f}"


def get_active_section_title(data: ReportData) -> str:
    phase = data.market_phase
    if phase == "premarket":
        return "Premarket Active Stocks"
    if phase == "regular":
        return "Regular Session Active Stocks"
    if phase == "after_hours":
        return "After-hours / Closing Movers"
    if phase == "open_day":
        return "Active Stocks"
    return "Market Movers"


def get_active_section_note(data: ReportData) -> str:
    phase = data.market_phase
    as_of = f" Latest source timestamp: {data.active_stocks_as_of}." if data.active_stocks_as_of else ""
    if phase == "premarket":
        return f"This section uses Nasdaq market movers during premarket hours.{as_of}"
    if phase == "regular":
        return (
            "Premarket-only movers are no longer available after 9:30 AM ET. "
            f"This section falls back to Nasdaq regular-session market movers.{as_of}"
        )
    if phase == "after_hours":
        if data.active_stocks_source == "after_hours_article":
            return (
                "This section uses Nasdaq's published After Hours Most Active article. "
                f"It is a real after-hours leaderboard, but it may post after the live session has already started.{as_of}"
            )
        return (
            "Nasdaq's public market movers endpoint does not expose a separate after-hours activity list. "
            f"This section shows the latest overall Nasdaq movers after the close instead.{as_of}"
        )
    if phase == "open_day":
        return (
            "This report is for a market-open date outside the live session, "
            f"so the movers source is labeled generically.{as_of}"
        )
    return ""


def append_snapshot_markdown(lines: list[str], data: ReportData) -> None:
    snapshots = data.snapshots or [current_snapshot(data)]
    for snapshot in snapshots:
        lines.append(f"### {snapshot_title(snapshot)}")
        note = snapshot_note(snapshot)
        if note:
            lines.append(f"- {note}")
            lines.append("")

        active_stocks = snapshot.get("active_stocks") or {}
        market_status = snapshot.get("market_status") or {}
        if market_status.get("is_open") == "no":
            lines.append(f"- Skipped because {market_status.get('reason', 'US market is closed')}.")
            lines.append("")
        elif active_stocks:
            for section, rows in active_stocks.items():
                lines.append(f"#### {section}")
                if not rows:
                    lines.append("- No rows returned.")
                for row in rows:
                    symbol = row.get("symbol", "")
                    name = row.get("name", "")
                    last = row.get("lastSalePrice", "")
                    change_value = row.get("lastSaleChange", "")
                    detail = format_stock_detail(section, row)
                    lines.append(f"- **{symbol}** {name} | Last: {last} | Move: {change_value} | {detail}")
                lines.append("")
        else:
            lines.append("- Market movers source unavailable.")
            lines.append("")

        health = compact_snapshot_health(snapshot)
        if health:
            lines.append("Source health:")
            for item in health:
                lines.append(f"- {item}")
            lines.append("")


def append_snapshot_html(parts: list[str], data: ReportData) -> None:
    snapshots = data.snapshots or [current_snapshot(data)]
    for snapshot in snapshots:
        parts.extend(['<div class="section">', f"<h3>{escape(snapshot_title(snapshot))}</h3>"])
        note = snapshot_note(snapshot)
        if note:
            parts.append(f"<p>{escape(note)}</p>")

        active_stocks = snapshot.get("active_stocks") or {}
        market_status = snapshot.get("market_status") or {}
        if market_status.get("is_open") == "no":
            parts.append(f'<ul><li>Skipped because {escape(market_status.get("reason", "US market is closed"))}.</li></ul>')
        elif active_stocks:
            for section, rows in active_stocks.items():
                parts.extend([f"<h4>{escape(section)}</h4>", "<ul>"])
                if not rows:
                    parts.append("<li>No rows returned.</li>")
                for row in rows:
                    symbol = row.get("symbol", "")
                    name = row.get("name", "")
                    last = row.get("lastSalePrice", "")
                    change_value = row.get("lastSaleChange", "")
                    detail = format_stock_detail(section, row)
                    parts.append(f"<li><strong>{escape(symbol)}</strong> {escape(name)} | Last: {escape(last)} | Move: {escape(change_value)} | {escape(detail)}</li>")
                parts.append("</ul>")
        else:
            parts.append("<ul><li>Market movers source unavailable.</li></ul>")

        health = compact_snapshot_health(snapshot)
        if health:
            parts.extend(['<p class="meta">Source health:</p>', '<ul class="source-health">'])
            for item in health:
                parts.append(f"<li>{escape(item)}</li>")
            parts.append("</ul>")
        parts.append("</div>")


def current_snapshot(data: ReportData) -> dict[str, object]:
    return {
        "slot": "",
        "captured_at": "",
        "timezone": "",
        "market_phase": data.market_phase,
        "market_status": data.market_status,
        "active_stocks": data.active_stocks,
        "active_stocks_as_of": data.active_stocks_as_of,
        "active_stocks_source": data.active_stocks_source,
        "notes": [
            {
                "source": note.source,
                "status": note.status,
                "detail": note.detail,
            }
            for note in data.notes
        ],
    }


def snapshot_title(snapshot: dict[str, object]) -> str:
    phase = str(snapshot.get("market_phase") or "unknown")
    captured_at = str(snapshot.get("captured_at") or "")
    slot = str(snapshot.get("slot") or "")
    label = phase.replace("_", " ").title()
    if captured_at:
        try:
            captured = datetime.fromisoformat(captured_at)
            return f"{captured.strftime('%-I:%M %p')} {label} Snapshot"
        except ValueError:
            pass
    if slot:
        return f"{slot} {label} Snapshot"
    return f"{label} Snapshot"


def snapshot_note(snapshot: dict[str, object]) -> str:
    phase = str(snapshot.get("market_phase") or "unknown")
    as_of = str(snapshot.get("active_stocks_as_of") or "")
    suffix = f" Latest source timestamp: {as_of}." if as_of else ""
    if phase == "premarket":
        return f"Nasdaq market movers captured during premarket hours.{suffix}"
    if phase == "regular":
        return f"Nasdaq market movers captured during the regular session.{suffix}"
    if phase == "after_hours":
        if snapshot.get("active_stocks_source") == "after_hours_article":
            return f"Nasdaq after-hours most-active article captured after the close.{suffix}"
        return f"Nasdaq market movers captured after the close.{suffix}"
    if phase == "open_day":
        return f"Nasdaq market movers captured outside the live session for this open market date.{suffix}"
    return suffix.strip()


def compact_snapshot_health(snapshot: dict[str, object]) -> list[str]:
    result: list[str] = []
    notes = snapshot.get("notes") or []
    if not isinstance(notes, list):
        return result

    important_sources = (
        "NYSE calendar",
        "Network readiness",
        "Nasdaq market movers",
        "Nasdaq after-hours article",
    )
    for note in notes:
        if not isinstance(note, dict):
            continue
        source = str(note.get("source") or "")
        if not source.startswith(important_sources):
            continue
        status = str(note.get("status") or "")
        detail = str(note.get("detail") or "")
        result.append(f"{source}: {status}{f' - {detail}' if detail else ''}")
    return result


def append_economic_day(lines: list[str], title: str, events: list[dict[str, str]]) -> None:
    lines.append(f"### {title}")
    if not events:
        lines.append("- No major events returned by configured sources.")
        lines.append("")
        return
    for event in events:
        time = event.get("time") or "Time N/A"
        name = event.get("event") or "Unnamed event"
        forecast = event.get("forecast")
        previous = event.get("previous")
        source = event.get("source", "")
        details = []
        if forecast:
            details.append(f"Forecast: {forecast}")
        if previous:
            details.append(f"Previous: {previous}")
        if source:
            details.append(f"Source: {source}")
        suffix = f" | {' | '.join(details)}" if details else ""
        lines.append(f"- **{time}** {name}{suffix}")
    lines.append("")


def append_earnings_group(lines: list[str], title: str, rows: list[dict[str, str]], time_filter: str) -> None:
    lines.append(f"### {title}")
    filtered_rows = filter_earnings(rows, time_filter)
    if not filtered_rows:
        lines.append("- No earnings returned.")
        lines.append("")
        return
    for row in filtered_rows:
        symbol = row.get("symbol", "")
        name = row.get("name", "")
        when = row.get("time", "")
        eps = row.get("epsForecast", "")
        quarter = row.get("fiscalQuarterEnding", "")
        lines.append(f"- **{symbol}** {name} | Time: {when or 'N/A'} | EPS est: {eps or 'N/A'} | Quarter: {quarter or 'N/A'}")
    lines.append("")


def filter_earnings(rows: list[dict[str, str]], time_filter: str) -> list[dict[str, str]]:
    if time_filter:
        return [row for row in rows if row.get("time") == time_filter]
    return [row for row in rows if row.get("time") not in {"time-after-hours", "time-pre-market"}]
