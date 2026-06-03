#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

timezone="${REPORT_TIMEZONE:-America/Los_Angeles}"
report_date="${REPORT_DATE:-$(TZ="$timezone" date +%F)}"
report_stem="reports/finance-daily-report-${report_date}"
report_md="${report_stem}.md"
report_html="${report_stem}.html"
reports_site_repo="${REPORTS_SITE_REPO:-https://github.com/awolf08/reports.git}"

if [ "$(git branch --show-current)" != "main" ]; then
  echo "Fallback publish must run from the main branch." >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Working tree has tracked changes. Commit or stash them before fallback publish." >&2
  git status --short
  exit 1
fi

git fetch --prune origin
git pull --rebase origin main

report_exists_on_origin=false
if git cat-file -e "origin/main:${report_md}" 2>/dev/null && git cat-file -e "origin/main:${report_html}" 2>/dev/null; then
  report_exists_on_origin=true
  echo "Report for ${report_date} already exists on origin/main. Skipping local generation."
fi

if [ "$report_exists_on_origin" = "false" ]; then
  python3 -m finance_daily_report --date "$report_date" --email-if-configured

  if grep -Eq "Network readiness: unavailable|Failed to resolve|NameResolutionError" "$report_md"; then
    echo "Generated report still shows network/DNS failure; refusing to publish an empty report." >&2
    echo "Likely fix: rerun after network is ready, or increase REPORT_NETWORK_WAIT_SECONDS." >&2
    exit 1
  fi

  git add -f "$report_md" "$report_html"
  if git diff --cached --quiet; then
    echo "Generated report has no commit-worthy changes."
  else
    git commit -m "Add daily report for ${report_date}"
    git push origin HEAD:main
  fi
fi

if [ ! -f "$report_html" ] || [ ! -f "$report_md" ]; then
  echo "Report files for ${report_date} are missing locally after sync." >&2
  exit 1
fi

reports_site_dir="$(mktemp -d)"
git clone "$reports_site_repo" "$reports_site_dir"
mkdir -p "$reports_site_dir/daily-finance"
cp "$report_html" "$reports_site_dir/daily-finance/${report_date}.html"
cp "$report_md" "$reports_site_dir/daily-finance/${report_date}.md"
cat > "$reports_site_dir/daily-finance/index.html" <<EOF
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Latest Finance Daily Report</title>
  <link rel="canonical" href="./${report_date}.html">
  <meta http-equiv="refresh" content="0; url=./${report_date}.html">
  <script>location.replace("./${report_date}.html");</script>
</head>
<body>
  <p><a href="./${report_date}.html">Open latest Finance Daily Report</a></p>
</body>
</html>
EOF

python3 - "$reports_site_dir/index.html" "$report_date" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
report_date = sys.argv[2]
if path.exists():
    html = path.read_text(encoding="utf-8")
    html = html.replace('href="./daily-finance/"', f'href="./daily-finance/{report_date}.html"')
    html = html.replace('href="./daily-finance/index.html"', f'href="./daily-finance/{report_date}.html"')
    path.write_text(html, encoding="utf-8")
PY

(
  cd "$reports_site_dir"
  git config user.name "FinanceDailyReport fallback"
  git config user.email "fallback@users.noreply.github.com"
  git add index.html daily-finance/
  if git diff --cached --quiet; then
    echo "Reports site already contains ${report_date}."
  else
    git commit -m "Publish daily finance report for ${report_date}"
    git push origin HEAD:main
  fi
)
