from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .config import Settings
from .fetchers import SourceNote, clean, fetch_earnings, fetch_economic_events, fetch_text, parse_rss
from .render import escape, escape_attr, format_generated_at, symbol_link_html, symbol_link_markdown

IMPORTANT_EARNINGS = (
    "AAPL",
    "NVDA",
    "MSFT",
    "AMZN",
    "GOOGL",
    "GOOG",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "NFLX",
    "JPM",
    "GS",
    "BAC",
    "C",
    "WMT",
    "COST",
)

FED_SPEECH_FEEDS = (
    ("Federal Reserve Speeches", "https://www.federalreserve.gov/feeds/speeches.xml"),
    ("Federal Reserve Testimony", "https://www.federalreserve.gov/feeds/testimony.xml"),
)


@dataclass
class WeeklyReportData:
    report_date: date
    week_start: date
    week_end: date
    economic_events: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    fed_events: list[dict[str, str]] = field(default_factory=list)
    earnings: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    notes: list[SourceNote] = field(default_factory=list)


def next_market_week(report_date: date) -> tuple[date, date]:
    days_until_monday = (7 - report_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    week_start = report_date + timedelta(days=days_until_monday)
    return week_start, week_start + timedelta(days=4)


def collect_weekly_report_data(report_date: date, settings: Settings) -> WeeklyReportData:
    week_start, week_end = next_market_week(report_date)
    notes: list[SourceNote] = []
    data = WeeklyReportData(report_date=report_date, week_start=week_start, week_end=week_end, notes=notes)
    current = week_start
    important_symbols = set(settings.watchlist or IMPORTANT_EARNINGS) | set(IMPORTANT_EARNINGS)

    while current <= week_end:
        events = [event for event in fetch_economic_events(current, notes) if is_high_impact_macro_event(event)]
        data.economic_events[current.isoformat()] = events

        earnings = fetch_earnings(current, 80, notes)
        data.earnings[current.isoformat()] = [
            row for row in earnings if row.get("symbol", "").upper() in important_symbols
        ]
        current += timedelta(days=1)

    data.fed_events = fetch_weekly_fed_events(week_start, week_end, notes)
    return data


def is_high_impact_macro_event(event: dict[str, str]) -> bool:
    name = event.get("event", "").lower()
    return (
        any(term in name for term in ("cpi", "ppi", "pce", "gdp"))
        or any(term in name for term in ("payroll", "nonfarm", "unemployment", "jobless claims", "jolts", "adp employment"))
        or "fomc" in name
        or any(term in name for term in ("treasury", "auction", "note auction", "bond auction", "bill auction", "tips auction"))
    )


def fetch_weekly_fed_events(week_start: date, week_end: date, notes: list[SourceNote]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for source, url in FED_SPEECH_FEEDS:
        try:
            rss_text = fetch_text(url)
            items = parse_rss(rss_text, source)
        except Exception as exc:
            notes.append(SourceNote(source, "unavailable", str(exc)))
            continue

        notes.append(SourceNote(source, "ok"))
        for item in items:
            published = rss_item_date(item.get("published_sort", ""))
            if published is None or not (week_start <= published <= week_end):
                continue
            events.append(
                {
                    "date": published.isoformat(),
                    "time": "TBA",
                    "event": item.get("title", ""),
                    "source": source,
                    "link": item.get("link", ""),
                    "forecast": "",
                    "previous": "",
                }
            )
    events.sort(key=lambda item: (item.get("date", ""), item.get("time", ""), item.get("event", "")))
    return events


def rss_item_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except Exception:
        return None


def render_weekly_markdown(data: WeeklyReportData, settings: Settings) -> str:
    generated_at = format_generated_at(settings)
    lines = [
        f"# Next Week Market Events - {data.report_date.isoformat()}",
        "",
        f"_Generated: {generated_at}. Coverage: {data.week_start.isoformat()} to {data.week_end.isoformat()}. Not financial advice._",
        "",
        "[Baybell Home](https://www.baybell.com/)",
        "",
        "## Summary",
        "",
    ]
    summary = weekly_summary(data)
    if summary:
        lines.extend(f"- {item}" for item in summary)
    else:
        lines.append("- No high-impact macro events or watched mega-cap earnings returned by configured sources.")
    lines.append("")

    lines.extend(["## High-Impact Macro Calendar", ""])
    append_weekly_macro_markdown(lines, data)

    lines.extend(["## Important Earnings", ""])
    append_weekly_earnings_markdown(lines, data)

    lines.extend(["## Fed Speeches / Testimony", ""])
    if data.fed_events:
        for event in data.fed_events:
            link = event.get("link", "")
            title = event.get("event", "Fed event")
            event_text = f"[{title}]({link})" if link else title
            lines.append(f"- **{event.get('date', '')} {event.get('time', 'TBA')}** {event_text} | Impact: {macro_impact(event)}")
    else:
        lines.append("- No Fed speeches/testimony returned for the covered week.")
    lines.append("")

    lines.extend(["## Source Health", ""])
    for note in data.notes:
        detail = f" - {note.detail}" if note.detail else ""
        lines.append(f"- {note.source}: {note.status}{detail}")
    lines.append("")
    return "\n".join(lines)


def append_weekly_macro_markdown(lines: list[str], data: WeeklyReportData) -> None:
    any_events = False
    for day, events in data.economic_events.items():
        if not events:
            continue
        any_events = True
        lines.append(f"### {day}")
        for event in events:
            details = event_expectation_details(event)
            lines.append(
                f"- **{event.get('time') or 'TBA'}** {event.get('event', 'Unnamed event')}"
                f"{details} | Impact: {macro_impact(event)}"
            )
        lines.append("")
    if not any_events:
        lines.append("- No high-impact macro events returned.")
        lines.append("")


def append_weekly_earnings_markdown(lines: list[str], data: WeeklyReportData) -> None:
    any_earnings = False
    for day, rows in data.earnings.items():
        if not rows:
            continue
        any_earnings = True
        lines.append(f"### {day}")
        for row in rows:
            lines.append(
                f"- {symbol_link_markdown(row.get('symbol', ''))} {row.get('name', '')}"
                f" | Time: {row.get('time') or 'N/A'}"
                f" | EPS est: {row.get('epsForecast') or 'N/A'}"
                f" | Impact: {earnings_impact(row)}"
            )
        lines.append("")
    if not any_earnings:
        lines.append("- No watched mega-cap earnings returned.")
        lines.append("")


def render_weekly_html(data: WeeklyReportData, settings: Settings) -> str:
    title = f"Next Week Market Events - {data.report_date.isoformat()}"
    generated_at = format_generated_at(settings)
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
        "<style>",
        "body{margin:0;background:#f6f7f9;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45}",
        ".wrap{max-width:1040px;margin:0 auto;padding:28px 18px 44px}",
        "header{border-bottom:3px solid #1b4d89;padding-bottom:16px;margin-bottom:22px}",
        "h1{font-size:30px;margin:0 0 8px;color:#102a43}",
        "h2{font-size:20px;margin:28px 0 12px;color:#183b56;border-bottom:1px solid #d9e2ec;padding-bottom:6px}",
        "h3{font-size:16px;margin:18px 0 8px;color:#334e68}",
        ".meta{color:#627d98;font-size:14px}",
        ".home-link{display:inline-block;margin-top:10px;font-weight:700}",
        ".section{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px 18px;margin:14px 0}",
        "ul{margin:8px 0 18px;padding-left:20px}",
        "li{margin:8px 0}",
        "a{color:#0b63ce;text-decoration:none}",
        "a:hover{text-decoration:underline}",
        ".impact{color:#334e68}",
        ".source-health{font-size:13px;color:#52616f}",
        "</style>",
        "</head>",
        "<body>",
        '<main class="wrap">',
        "<header>",
        f"<h1>{escape(title)}</h1>",
        f'<div class="meta">Generated: {escape(generated_at)}. Coverage: {escape(data.week_start.isoformat())} to {escape(data.week_end.isoformat())}. Not financial advice.</div>',
        '<a class="home-link" href="https://www.baybell.com/">Baybell Home</a>',
        "</header>",
    ]

    parts.extend(["<h2>Summary</h2>", '<div class="section"><ul>'])
    summary = weekly_summary(data)
    if summary:
        parts.extend(f"<li>{escape(item)}</li>" for item in summary)
    else:
        parts.append("<li>No high-impact macro events or watched mega-cap earnings returned by configured sources.</li>")
    parts.extend(["</ul></div>"])

    parts.append("<h2>High-Impact Macro Calendar</h2>")
    append_weekly_macro_html(parts, data)

    parts.append("<h2>Important Earnings</h2>")
    append_weekly_earnings_html(parts, data)

    parts.extend(["<h2>Fed Speeches / Testimony</h2>", '<div class="section"><ul>'])
    if data.fed_events:
        for event in data.fed_events:
            parts.append(
                f"<li><strong>{escape(event.get('date', ''))} {escape(event.get('time', 'TBA'))}</strong> "
                f"{event_link_html(event)} | <span class=\"impact\">Impact: {escape(macro_impact(event))}</span></li>"
            )
    else:
        parts.append("<li>No Fed speeches/testimony returned for the covered week.</li>")
    parts.extend(["</ul></div>"])

    parts.extend(["<h2>Source Health</h2>", '<div class="section source-health"><ul>'])
    for note in data.notes:
        detail = f" - {note.detail}" if note.detail else ""
        parts.append(f"<li>{escape(note.source)}: {escape(note.status)}{escape(detail)}</li>")
    parts.extend(["</ul></div>", "</main>", "</body>", "</html>"])
    return "\n".join(parts)


def append_weekly_macro_html(parts: list[str], data: WeeklyReportData) -> None:
    any_events = False
    for day, events in data.economic_events.items():
        if not events:
            continue
        any_events = True
        parts.extend(['<div class="section">', f"<h3>{escape(day)}</h3>", "<ul>"])
        for event in events:
            parts.append(
                f"<li><strong>{escape(event.get('time') or 'TBA')}</strong> {escape(event.get('event', 'Unnamed event'))}"
                f"{escape(event_expectation_details(event))} | <span class=\"impact\">Impact: {escape(macro_impact(event))}</span></li>"
            )
        parts.extend(["</ul></div>"])
    if not any_events:
        parts.append('<div class="section"><ul><li>No high-impact macro events returned.</li></ul></div>')


def append_weekly_earnings_html(parts: list[str], data: WeeklyReportData) -> None:
    any_earnings = False
    for day, rows in data.earnings.items():
        if not rows:
            continue
        any_earnings = True
        parts.extend(['<div class="section">', f"<h3>{escape(day)}</h3>", "<ul>"])
        for row in rows:
            parts.append(
                f"<li>{symbol_link_html(row.get('symbol', ''))} {escape(row.get('name', ''))}"
                f" | Time: {escape(row.get('time') or 'N/A')}"
                f" | EPS est: {escape(row.get('epsForecast') or 'N/A')}"
                f" | <span class=\"impact\">Impact: {escape(earnings_impact(row))}</span></li>"
            )
        parts.extend(["</ul></div>"])
    if not any_earnings:
        parts.append('<div class="section"><ul><li>No watched mega-cap earnings returned.</li></ul></div>')


def weekly_summary(data: WeeklyReportData) -> list[str]:
    macro_count = sum(len(events) for events in data.economic_events.values())
    earnings_count = sum(len(rows) for rows in data.earnings.values())
    fed_count = len(data.fed_events)
    summary = []
    if macro_count:
        summary.append(f"{macro_count} high-impact macro event(s), including CPI/PPI/jobs/FOMC/Fed/GDP/PCE/Treasury-auction related items when present.")
    if earnings_count:
        symbols = sorted({row.get("symbol", "") for rows in data.earnings.values() for row in rows if row.get("symbol")})
        summary.append(f"{earnings_count} important earnings event(s): {', '.join(symbols)}.")
    if fed_count:
        summary.append(f"{fed_count} Fed speech/testimony item(s) from Federal Reserve feeds.")
    return summary


def event_expectation_details(event: dict[str, str]) -> str:
    details = []
    if event.get("forecast"):
        details.append(f"Market expectation: {event['forecast']}")
    if event.get("previous"):
        details.append(f"Previous: {event['previous']}")
    if event.get("source"):
        details.append(f"Source: {event['source']}")
    return f" | {' | '.join(details)}" if details else ""


def macro_impact(event: dict[str, str]) -> str:
    name = event.get("event", "").lower()
    if any(term in name for term in ("cpi", "ppi", "pce", "inflation")):
        return "Hotter-than-expected inflation can pressure SPX/NDX, lift yields and USD, and weigh on gold; softer data usually supports risk assets and Treasuries."
    if any(term in name for term in ("payroll", "jobless", "employment", "unemployment", "jobs")):
        return "Strong labor data can push yields higher and pressure duration-sensitive NDX; weaker data can support bonds/gold but may hurt growth sentiment."
    if "gdp" in name:
        return "Upside growth surprises can help cyclicals but may lift yields; downside surprises can support bonds/gold while pressuring equity earnings expectations."
    if any(term in name for term in ("fomc", "fed", "powell", "federal reserve")):
        return "Hawkish messaging can weigh on SPX/NDX and Treasuries while supporting yields/USD; dovish messaging tends to help equities and gold."
    if any(term in name for term in ("treasury", "auction", "note", "bond", "bill")):
        return "Weak auction demand can lift yields and pressure SPX/NDX/gold; strong demand can ease yields and support risk assets."
    return "Potential impact depends on surprise versus expectations, mainly through rates, USD, and growth expectations."


def earnings_impact(row: dict[str, str]) -> str:
    symbol = row.get("symbol", "").upper()
    if symbol in {"AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AMD", "AVGO"}:
        return "Mega-cap result/guidance can move NDX and SPX index breadth; AI/cloud/capex commentary is especially relevant for NDX."
    return "Large-cap earnings can affect sector sentiment and index futures if guidance diverges from expectations."


def event_link_html(event: dict[str, str]) -> str:
    link = event.get("link", "")
    title = event.get("event", "Fed event")
    if not link:
        return escape(title)
    return f'<a href="{escape_attr(link)}">{escape(title)}</a>'


def write_weekly_report(data: WeeklyReportData, settings: Settings, output_dir: Path, output_format: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = output_dir / f"weekly-market-events-{data.report_date.isoformat()}"
    paths: list[Path] = []
    if output_format in {"md", "both"}:
        path = output_stem.with_suffix(".md")
        path.write_text(render_weekly_markdown(data, settings), encoding="utf-8")
        paths.append(path)
    if output_format in {"html", "both"}:
        path = output_stem.with_suffix(".html")
        path.write_text(render_weekly_html(data, settings), encoding="utf-8")
        paths.append(path)
    return paths
