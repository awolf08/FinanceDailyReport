# Finance Daily Report

Personal daily market brief generator.

It creates a Markdown report with:

- Premarket / active stocks and movers from Nasdaq market movers
- Latest market news from public RSS feeds
- Today and tomorrow economic calendar checks
- NYSE market status so holidays and closed sessions are clearly labeled
- After-hours and next pre-market earnings calendar from Nasdaq

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Email delivery is optional. If you want email, fill in `SMTP_*` and `REPORT_RECIPIENT` in `.env`.

For Gmail, use an app password instead of your normal account password.

## Run

```bash
python -m finance_daily_report
```

The report is saved under `reports/`.
By default, it writes both Markdown (`.md`) and browser-friendly HTML (`.html`).

To send email as well:

```bash
python -m finance_daily_report --email
```

For automation-friendly behavior, send only when email settings are present:

```bash
python -m finance_daily_report --email-if-configured
```

Run for a specific date:

```bash
python -m finance_daily_report --date 2026-05-25
```

Choose one output format:

```bash
python -m finance_daily_report --format html
python -m finance_daily_report --format md
```

## Daily automation

For a daily premarket email, schedule this command around 6:00 AM Pacific:

```bash
cd /path/to/FinanceDailyReport
python -m finance_daily_report --email-if-configured
```

On US market holidays the report still sends, but the active-stock section is skipped and marked as closed.

This repo also includes a GitHub Actions workflow at [`.github/workflows/daily-report.yml`](/Users/weicheng/Desktop/Projects/FinanceDailyReport/.github/workflows/daily-report.yml) that runs automatically on weekdays at `13:05 UTC`, which is `6:05 AM` in Los Angeles during daylight saving time.

To reduce missed-report risk from a single dropped cron trigger, the workflow also runs hourly catch-up checks on weekdays from `13:35 UTC` through `20:35 UTC`. Those catch-up runs skip themselves once that day's Markdown and HTML report already exist, so you get a fallback without duplicate daily publishes.

To let the scheduled run send email, add these repository secrets in GitHub:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `REPORT_RECIPIENT`

Optional repository variables:

- `REPORT_TIMEZONE`
- `REPORT_NEWS_LIMIT`
- `REPORT_STOCK_LIMIT`
- `REPORT_WATCHLIST`

The workflow force-adds the generated `reports/*.md` and `reports/*.html`, commits them to `main`, and your GitHub Pages site updates from that push automatically.

## Notes

This first version avoids paid API keys. Public finance endpoints sometimes rate-limit or change shape, so each section degrades independently and shows a clear note when a source is unavailable.
