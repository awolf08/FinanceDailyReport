# Finance Daily Report

Personal daily market brief generator.

It creates a Markdown report with:

- Premarket movers from TradingView, filtered to companies with at least $100M market cap
- Latest market news from public RSS feeds
- Today and tomorrow economic calendar checks
- NYSE market status so holidays and closed sessions are clearly labeled
- After-hours and next pre-market earnings calendar from Nasdaq
- Sunday next-week market events report covering CPI/PPI, jobs, FOMC/Fed items, GDP/PCE, Treasury auctions, and important mega-cap earnings

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

Generate the next-week market events report:

```bash
python -m finance_daily_report --weekly
```

The weekly report is saved as:

```text
reports/weekly-market-events-YYYY-MM-DD.md
reports/weekly-market-events-YYYY-MM-DD.html
```

## Daily automation

Use the local fallback publisher as the primary daily automation around 5:55 AM Pacific:

```bash
cd /path/to/FinanceDailyReport
scripts/fallback-publish-report.sh
```

It rebases local `main` onto `origin/main`, generates the report with `--email-if-configured` when needed, refuses to publish reports that still show DNS/network failures, force-adds the ignored report files, commits and pushes them, and syncs the public `awolf08/reports` site. If today's report already exists on GitHub, it skips generation and still makes sure the public site is current.

On US market holidays the report still sends, but the active-stock section is skipped and marked as closed.

## Weekly automation

Use the weekly publisher every Sunday around 6:00 PM Pacific:

```bash
cd /path/to/FinanceDailyReport
scripts/publish-weekly-report.sh
```

It generates the next-week market events report, force-adds the ignored weekly report files, commits them, and pushes them to `origin/main`.

This repo also includes a best-effort GitHub Actions backup at [`.github/workflows/daily-report.yml`](/Users/weicheng/Desktop/Projects/FinanceDailyReport/.github/workflows/daily-report.yml). It checks shortly after the local run window and generates/publishes only if the day's report is still missing. GitHub scheduled workflows can be delayed or dropped, so do not treat that schedule as the primary delivery path.

To run the GitHub backup manually:

```bash
gh workflow run daily-report.yml --repo awolf08/FinanceDailyReport -f force=true
```

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

The workflow force-adds the generated `reports/*.md` and `reports/*.html`, commits them to `main`, and publishes the newest HTML report into the separate `awolf08/reports` site repository under `daily-finance/`. Catch-up runs also retry publishing an already-generated report, so a temporary cross-repo publish failure can recover on the next scheduled check.

To publish into `awolf08/reports`, add the private half of a writable deploy key as this repository secret:

- `REPORTS_DEPLOY_KEY`

For a stable public URL that always opens the newest published report, use:

- `https://baybell.com/daily-finance/`

The dated report URLs still exist in both repositories. In the reports site, they are published as `daily-finance/YYYY-MM-DD.html`.

## Notes

This first version avoids paid API keys. Public finance endpoints sometimes rate-limit or change shape, so each section degrades independently and shows a clear note when a source is unavailable.
