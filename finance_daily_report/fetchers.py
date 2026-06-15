from __future__ import annotations

import html
import re
import socket
import time as time_module
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    import pandas_market_calendars as mcal
except ImportError:
    mcal = None

from .config import Settings

NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

NEWS_FEEDS = [
    ("MarketWatch Top Stories", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Google News Markets", "https://news.google.com/rss/search?q=(stock%20market%20OR%20Federal%20Reserve%20OR%20earnings)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
]

NEWS_PRIORITY_TERMS = (
    "federal reserve",
    "fed",
    "cpi",
    "pce",
    "jobs",
    "payroll",
    "unemployment",
    "treasury",
    "yield",
    "inflation",
    "earnings",
    "guidance",
    "nasdaq",
    "s&p 500",
    "dow",
    "oil",
    "dollar",
)

NOISY_NEWS_TERMS = (
    "equity in earnings of",
    "tradingview",
    "stock market today:",
)

NETWORK_READY_HOSTS = (
    "api.nasdaq.com",
    "query1.finance.yahoo.com",
    "news.google.com",
    "www.federalreserve.gov",
)


@dataclass
class SourceNote:
    source: str
    status: str
    detail: str = ""


@dataclass
class ReportData:
    report_date: date
    market_status: dict[str, str] = field(default_factory=dict)
    market_phase: str = "unknown"
    active_stocks: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    active_stocks_as_of: str = ""
    active_stocks_source: str = "market_movers"
    news: list[dict[str, str]] = field(default_factory=list)
    economic_events: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    earnings: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    notes: list[SourceNote] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)


def collect_report_data(report_date: date, settings: Settings) -> ReportData:
    data = ReportData(report_date=report_date)
    data.market_status = fetch_market_status(report_date, data.notes)
    data.market_phase = determine_market_phase(report_date, settings, data.market_status)
    wait_for_network(settings.network_wait_seconds, data.notes)
    if data.market_status.get("is_open") == "no":
        data.notes.append(SourceNote("Nasdaq market movers", "skipped", data.market_status.get("reason", "Market closed")))
    else:
        if data.market_phase in {"premarket", "regular"}:
            data.active_stocks, data.active_stocks_as_of = fetch_yahoo_regular_market_lists(10, data.notes)
            data.active_stocks_source = "yahoo_regular_market_lists"
        else:
            data.active_stocks, data.active_stocks_as_of = fetch_market_movers(settings.stock_limit, data.notes)
        if data.market_phase == "after_hours":
            after_hours_rows, after_hours_as_of = fetch_after_hours_most_active(report_date, settings.stock_limit, data.notes)
            if after_hours_rows:
                data.active_stocks = {"After-Hours Most Active": after_hours_rows}
                data.active_stocks_as_of = after_hours_as_of
                data.active_stocks_source = "after_hours_article"
    data.news = fetch_news(settings.news_limit, data.notes, report_date)
    data.economic_events = {
        "today": fetch_economic_events(report_date, data.notes),
        "tomorrow": fetch_economic_events(report_date + timedelta(days=1), data.notes),
    }
    data.earnings = {
        "today": fetch_earnings(report_date, settings.stock_limit, data.notes),
        "tomorrow": fetch_earnings(report_date + timedelta(days=1), settings.stock_limit, data.notes),
    }
    return data


def wait_for_network(wait_seconds: int, notes: list[SourceNote]) -> None:
    if wait_seconds <= 0:
        notes.append(SourceNote("Network readiness", "skipped", "REPORT_NETWORK_WAIT_SECONDS <= 0"))
        return

    deadline = time_module.monotonic() + wait_seconds
    last_error = ""
    while True:
        for host in NETWORK_READY_HOSTS:
            try:
                with socket.create_connection((host, 443), timeout=5):
                    notes.append(SourceNote("Network readiness", "ok", f"connected to {host}:443"))
                    return
            except OSError as exc:
                last_error = f"{host}: {exc}"

        remaining = deadline - time_module.monotonic()
        if remaining <= 0:
            notes.append(SourceNote("Network readiness", "unavailable", last_error))
            return
        time_module.sleep(min(10, remaining))


def determine_market_phase(report_date: date, settings: Settings, market_status: dict[str, str]) -> str:
    if market_status.get("is_open") != "yes":
        return "closed"

    now_et = datetime.now(ZoneInfo("America/New_York"))

    if report_date != now_et.date():
        return "open_day"

    current_time = now_et.timetz().replace(tzinfo=None)
    if current_time < time(9, 30):
        return "premarket"
    if current_time <= time(16, 0):
        return "regular"
    if current_time <= time(20, 0):
        return "after_hours"
    return "closed"


def fetch_market_status(target_date: date, notes: list[SourceNote]) -> dict[str, str]:
    if mcal is None:
        notes.append(SourceNote("NYSE calendar", "unavailable", "Install pandas-market-calendars for holiday checks"))
        return {
            "is_open": "unknown",
            "label": "Market schedule unavailable",
            "reason": "NYSE calendar dependency is not installed",
        }

    try:
        calendar = mcal.get_calendar("NYSE")
        schedule = calendar.schedule(start_date=target_date, end_date=target_date)
    except Exception as exc:
        notes.append(SourceNote("NYSE calendar", "unavailable", str(exc)))
        return {
            "is_open": "unknown",
            "label": "Market schedule unavailable",
            "reason": "NYSE calendar source unavailable",
        }

    if schedule.empty:
        notes.append(SourceNote(f"NYSE calendar {target_date.isoformat()}", "closed"))
        return {
            "is_open": "no",
            "label": "US market closed",
            "reason": "NYSE has no regular session for this date",
        }

    row = schedule.iloc[0]
    open_time = row["market_open"].tz_convert("America/New_York").strftime("%-I:%M %p ET")
    close_time = row["market_close"].tz_convert("America/New_York").strftime("%-I:%M %p ET")
    notes.append(SourceNote(f"NYSE calendar {target_date.isoformat()}", "open"))
    return {
        "is_open": "yes",
        "label": "US market open",
        "open": open_time,
        "close": close_time,
        "reason": f"Regular session {open_time}-{close_time}",
    }


def fetch_json(url: str, *, headers: dict[str, str] | None = None) -> Any:
    response = requests.get(url, headers=headers or NASDAQ_HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_text(url: str, *, headers: dict[str, str] | None = None) -> str:
    response = requests.get(url, headers=headers or {"User-Agent": NASDAQ_HEADERS["User-Agent"]}, timeout=30)
    response.raise_for_status()
    return response.content.decode(response.encoding or "utf-8-sig", errors="replace")


def fetch_market_movers(limit: int, notes: list[SourceNote]) -> tuple[dict[str, list[dict[str, str]]], str]:
    url = "https://api.nasdaq.com/api/marketmovers?assetclass=stocks&exchange=NASDAQ"
    try:
        payload = fetch_json(url)
        stocks = payload["data"]["STOCKS"]
    except Exception as exc:
        notes.append(SourceNote("Nasdaq market movers", "unavailable", str(exc)))
        return {}, ""

    mapping = {
        "MostActiveByShareVolume": "Most Active",
        "MostAdvanced": "Gainers",
        "MostDeclined": "Decliners",
        "Nasdaq100Movers": "Nasdaq 100 Movers",
    }
    result: dict[str, list[dict[str, str]]] = {}
    for key, title in mapping.items():
        rows = stocks.get(key, {}).get("table", {}).get("rows", [])
        result[title] = [clean_dict(row) for row in rows[:limit]]

    as_of = clean(
        stocks.get("MostActiveByShareVolume", {}).get("dataAsOf")
        or stocks.get("MostActiveByShareVolume", {}).get("lastTradeTimestamp")
    )
    notes.append(SourceNote("Nasdaq market movers", "ok", as_of))
    return result, as_of


def fetch_yahoo_regular_market_lists(limit: int, notes: list[SourceNote]) -> tuple[dict[str, list[dict[str, str]]], str]:
    screeners = (
        ("most_actives", "Most Active Stocks", "Yahoo Finance Most Active Stocks"),
        ("most_actives_etfs", "Most Active ETFs", "Yahoo Finance Most Active ETFs"),
        ("day_gainers", "Top Gaining Stocks", "Yahoo Finance Stock Gainers"),
        ("day_losers", "Top Declining Stocks", "Yahoo Finance Stock Losers"),
    )
    result: dict[str, list[dict[str, str]]] = {}
    for scr_id, section_title, note_source in screeners:
        rows = fetch_yahoo_screener_rows(scr_id, note_source, limit, notes)
        if rows:
            result[section_title] = rows

    as_of = datetime.now(ZoneInfo("America/New_York")).strftime("Yahoo Finance market lists as of %-I:%M %p ET")
    if result:
        return result, as_of
    return {}, ""


def fetch_yahoo_screener_rows(scr_id: str, note_source: str, limit: int, notes: list[SourceNote]) -> list[dict[str, str]]:
    url = (
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        f"?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count=40"
    )
    try:
        payload = fetch_json(url, headers={"User-Agent": NASDAQ_HEADERS["User-Agent"]})
        quotes = payload["finance"]["result"][0]["quotes"]
    except Exception as exc:
        notes.append(SourceNote(note_source, "unavailable", str(exc)))
        return []

    rows: list[dict[str, str]] = []
    for quote in quotes:
        price = yahoo_raw_value(quote.get("regularMarketPrice"))
        if price is not None and price < 5:
            continue

        symbol = clean(str(quote.get("symbol") or quote.get("ticker") or ""))
        if not symbol:
            continue

        rows.append(
            {
                "symbol": symbol,
                "name": clean(str(quote.get("shortName") or quote.get("longName") or quote.get("companyName") or quote.get("displayName") or "")),
                "lastSalePrice": yahoo_money(quote.get("regularMarketPrice")),
                "lastSaleChange": yahoo_signed(quote.get("regularMarketChange")),
                "changePercent": yahoo_signed(quote.get("regularMarketChangePercent")),
                "change": yahoo_long_format(quote.get("regularMarketVolume")),
            }
        )
        if len(rows) >= limit:
            break

    if rows:
        notes.append(SourceNote(note_source, "ok", f"{len(rows)} rows at or above $5"))
    else:
        notes.append(SourceNote(note_source, "unavailable", "No rows at or above $5 returned"))
    return rows


def fetch_after_hours_most_active(target_date: date, limit: int, notes: list[SourceNote]) -> tuple[list[dict[str, str]], str]:
    try:
        article_url, article_title = find_after_hours_article_url(target_date)
    except Exception as exc:
        notes.append(SourceNote(f"Nasdaq after-hours article {target_date.isoformat()}", "unavailable", str(exc)))
        return [], ""

    if not article_url:
        notes.append(
            SourceNote(
                f"Nasdaq after-hours article {target_date.isoformat()}",
                "skipped",
                "No matching After Hours Most Active article found yet",
            )
        )
        return [], ""

    try:
        article_html = fetch_text(article_url)
        rows = parse_after_hours_article(article_html, limit)
    except Exception as exc:
        notes.append(SourceNote(f"Nasdaq after-hours article {target_date.isoformat()}", "unavailable", str(exc)))
        return [], ""

    if not rows:
        notes.append(
            SourceNote(
                f"Nasdaq after-hours article {target_date.isoformat()}",
                "unavailable",
                "Article found, but no after-hours rows were parsed",
            )
        )
        return [], ""

    published = clean(find_meta_content(article_html, "article:published_time") or "")
    as_of = clean(article_title.replace("After Hours Most Active for ", "", 1))
    detail = published or as_of
    notes.append(SourceNote(f"Nasdaq after-hours article {target_date.isoformat()}", "ok", detail))
    return rows, detail


def find_after_hours_article_url(target_date: date) -> tuple[str, str]:
    html_text = fetch_text("https://www.nasdaq.com/authors/nasdaqcom")
    matches = re.findall(
        r'<a class="content-feed__card-title-link" href="([^"]+)">(After Hours Most Active for [^<]+)</a>',
        html_text,
        flags=re.IGNORECASE,
    )
    target_label = target_date.strftime("%b %d, %Y").replace(" 0", " ")
    for href, title in matches:
        if target_label in clean(title):
            return absolutize_nasdaq_url(href), clean(title)
    return "", ""


def parse_after_hours_article(html_text: str, limit: int) -> list[dict[str, str]]:
    match = re.search(
        r'<div class="body__content">\s*<p>(.*?)</p>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []

    body_html = match.group(1)
    rows: list[dict[str, str]] = []
    pattern = re.compile(
        r'(?:<br\s*/?>\s*)*(?P<name>[^<]+?)\s*\(<a [^>]*>(?P<symbol>[A-Z.\-]+)</a>\)\s+is\s+'
        r'(?P<move>unchanged|[+\-]?[0-9.]+)\s+at\s+\$(?P<last>[0-9.]+),\s+with\s+'
        r'(?P<volume>[0-9,]+)\s+shares traded\.',
        flags=re.IGNORECASE,
    )
    for parsed in pattern.finditer(body_html):
        move = clean(parsed.group("move"))
        rows.append(
            {
                "symbol": clean(parsed.group("symbol")),
                "name": clean(strip_tags(parsed.group("name"))),
                "lastSalePrice": f"${clean(parsed.group('last'))}",
                "lastSaleChange": "0" if move.lower() == "unchanged" else move,
                "change": clean(parsed.group("volume")),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def fetch_earnings(target_date: date, limit: int, notes: list[SourceNote]) -> list[dict[str, str]]:
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={target_date.isoformat()}"
    try:
        payload = fetch_json(url)
        rows = payload.get("data", {}).get("rows", []) if payload.get("data") else []
    except Exception as exc:
        notes.append(SourceNote(f"Nasdaq earnings {target_date.isoformat()}", "unavailable", str(exc)))
        return []

    if not isinstance(rows, list):
        notes.append(SourceNote(f"Nasdaq earnings {target_date.isoformat()}", "unavailable", "Unexpected response shape"))
        return []

    notes.append(SourceNote(f"Nasdaq earnings {target_date.isoformat()}", "ok"))
    return [clean_dict(row) for row in rows[:limit]]


def fetch_economic_events(target_date: date, notes: list[SourceNote]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    events.extend(fetch_nasdaq_economic_events(target_date, notes))
    events.extend(fetch_census_events(target_date, notes))

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for event in events:
        key = (event.get("time", ""), event.get("event", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def fetch_nasdaq_economic_events(target_date: date, notes: list[SourceNote]) -> list[dict[str, str]]:
    url = f"https://api.nasdaq.com/api/calendar/economicevents?date={target_date.isoformat()}"
    try:
        payload = fetch_json(url)
    except Exception as exc:
        notes.append(SourceNote(f"Nasdaq economic calendar {target_date.isoformat()}", "unavailable", str(exc)))
        return []

    rows = payload.get("data", {}).get("rows", []) if payload.get("data") else []
    notes.append(SourceNote(f"Nasdaq economic calendar {target_date.isoformat()}", "ok"))
    return [
        {
            "time": clean(row.get("time") or row.get("gmt") or ""),
            "event": clean(row.get("eventName") or row.get("name") or row.get("event", "")),
            "actual": clean(row.get("actual", "")),
            "forecast": clean(row.get("forecast") or row.get("consensus") or ""),
            "previous": clean(row.get("previous", "")),
            "country": clean(row.get("country", "")),
            "source": "Nasdaq",
        }
        for row in rows
        if is_relevant_economic_row(row)
    ]


def is_relevant_economic_row(row: dict[str, Any]) -> bool:
    country = clean(row.get("country", "")).lower()
    if country in {"united states", "usa", "us"}:
        return True
    return not country


def fetch_census_events(target_date: date, notes: list[SourceNote]) -> list[dict[str, str]]:
    url = "https://www.census.gov/economic-indicators/calendar-listview.html"
    try:
        text = fetch_text(url)
    except Exception as exc:
        notes.append(SourceNote("Census economic indicators", "unavailable", str(exc)))
        return []

    events: list[dict[str, str]] = []
    expected_key = target_date.strftime("%Y%m%d")
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.IGNORECASE | re.DOTALL):
        if expected_key not in row_html:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        visible_cells = [clean(cell) for cell in cells[:4]]
        if len(visible_cells) < 4:
            continue
        event_name, _, release_time, period = visible_cells
        if event_name and release_time:
            events.append(
                {
                    "time": release_time,
                    "event": f"{event_name} ({period})" if period else event_name,
                    "source": "Census",
                }
            )
    notes.append(SourceNote("Census economic indicators", "ok"))
    return events[:5]


def fetch_news(limit: int, notes: list[SourceNote], report_date: date) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for source, url in NEWS_FEEDS:
        try:
            text = fetch_text(url)
            parsed = parse_rss(text, source)
            items.extend(parsed)
            notes.append(SourceNote(source, "ok"))
        except Exception as exc:
            notes.append(SourceNote(source, "unavailable", str(exc)))

    recent_items = [item for item in items if not is_stale_news(item, report_date)]
    if recent_items:
        items = recent_items

    for item in items:
        item["priority_score"] = str(score_news_item(item))

    items.sort(
        key=lambda item: (
            int(item.get("priority_score", "0")),
            item.get("published_sort", ""),
        ),
        reverse=True,
    )
    deduped: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for item in items:
        if is_noisy_news(item):
            continue
        normalized = re.sub(r"\W+", "", item["title"].lower())
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        deduped.append(item)
    return deduped[:limit]


def is_stale_news(item: dict[str, str], report_date: date) -> bool:
    published = item.get("published_sort", "")
    if not published:
        return False
    try:
        published_date = datetime.fromisoformat(published).date()
    except ValueError:
        return False
    return published_date < report_date - timedelta(days=3)


def score_news_item(item: dict[str, str]) -> int:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    score = sum(2 for term in NEWS_PRIORITY_TERMS if term in text)
    if item.get("source") == "Federal Reserve":
        score += 4
    if item.get("source") == "MarketWatch Top Stories":
        score += 1
    return score


def is_noisy_news(item: dict[str, str]) -> bool:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    return any(term in text for term in NOISY_NEWS_TERMS)


def parse_rss(text: str, source: str) -> list[dict[str, str]]:
    cleaned_text = text.lstrip("\ufeff").lstrip("ï»¿")
    root = ET.fromstring(cleaned_text.encode("utf-8"))
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = clean(find_child_text(item, "title"))
        link = clean(find_child_text(item, "link"))
        description = clean(strip_tags(find_child_text(item, "description")))
        published = clean(find_child_text(item, "pubDate"))
        sort_value = published
        if published:
            try:
                sort_value = parsedate_to_datetime(published).isoformat()
            except Exception:
                pass
        if title:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published": published,
                    "published_sort": sort_value,
                    "source": source,
                }
            )
    return items


def find_child_text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    return child.text if child is not None and child.text else ""


def clean(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = strip_tags(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_dict(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): clean(value) for key, value in row.items()}


def yahoo_raw_value(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("raw")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def yahoo_fmt_value(value: Any) -> str:
    if isinstance(value, dict):
        return clean(value.get("fmt") or value.get("longFmt") or value.get("raw"))
    return clean(value)


def yahoo_long_format(value: Any) -> str:
    if isinstance(value, dict):
        return clean(value.get("longFmt") or value.get("fmt") or value.get("raw"))
    return clean(value)


def yahoo_money(value: Any) -> str:
    formatted = yahoo_fmt_value(value)
    if not formatted or formatted.startswith("$"):
        return formatted
    return f"${formatted}"


def yahoo_signed(value: Any) -> str:
    raw = yahoo_raw_value(value)
    formatted = yahoo_fmt_value(value)
    if raw is None or not formatted:
        return formatted
    if raw > 0 and not formatted.startswith("+"):
        return f"+{formatted}"
    return formatted


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def absolutize_nasdaq_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://www.nasdaq.com{url}"


def find_meta_content(html_text: str, name: str) -> str:
    patterns = [
        rf'<meta[^>]+property="{re.escape(name)}"[^>]+content="([^"]+)"',
        rf'<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return ""
