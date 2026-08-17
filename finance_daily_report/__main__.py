from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings, load_dotenv
from .emailer import send_email
from .fetchers import collect_report_data
from .render import render_html, render_markdown
from .snapshots import update_snapshot_file
from .weekly import collect_weekly_report_data, write_weekly_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily finance report.")
    parser.add_argument("--weekly", action="store_true", help="Generate a next-week market events report instead of the daily report.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--email", action="store_true", help="Send the report by email after writing it.")
    parser.add_argument("--email-if-configured", action="store_true", help="Send email only when SMTP settings exist.")
    parser.add_argument("--format", choices=("md", "html", "both"), default="both", help="Output format. Defaults to both.")
    parser.add_argument("--output-dir", help="Directory for generated reports.")
    return parser.parse_args()


def main() -> int:
    load_dotenv(Path(".env"))
    args = parse_args()
    settings = Settings.from_env()

    if args.output_dir:
        settings.output_dir = Path(args.output_dir)

    report_date = datetime.now(ZoneInfo(settings.timezone)).date()
    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    if args.weekly:
        data = collect_weekly_report_data(report_date, settings)
        for path in write_weekly_report(data, settings, settings.output_dir, args.format):
            print(f"Wrote {path}")
        return 0

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = settings.output_dir / f"finance-daily-report-{report_date.isoformat()}"
    data = collect_report_data(report_date, settings)
    data.snapshots = update_snapshot_file(data, settings, output_stem.with_suffix(".snapshots.json"))
    markdown = render_markdown(data, settings)
    html = render_html(data, settings)

    if args.format in {"md", "both"}:
        markdown_path = output_stem.with_suffix(".md")
        markdown_path.write_text(markdown, encoding="utf-8")
        print(f"Wrote {markdown_path}")
    if args.format in {"html", "both"}:
        html_path = output_stem.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        print(f"Wrote {html_path}")

    should_email = args.email or (args.email_if_configured and settings.email_configured)
    if should_email:
        subject = f"Finance Daily Report - {report_date.isoformat()}"
        send_email(settings, subject, markdown)
        print(f"Sent email to {settings.report_recipient}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
