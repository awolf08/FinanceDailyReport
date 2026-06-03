#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

timezone="${REPORT_TIMEZONE:-America/Los_Angeles}"
report_date="${REPORT_DATE:-$(TZ="$timezone" date +%F)}"
report_stem="reports/finance-daily-report-${report_date}"
report_md="${report_stem}.md"
report_html="${report_stem}.html"

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

if git cat-file -e "origin/main:${report_md}" 2>/dev/null && git cat-file -e "origin/main:${report_html}" 2>/dev/null; then
  echo "Report for ${report_date} already exists on origin/main. Nothing to publish."
  exit 0
fi

python3 -m finance_daily_report --date "$report_date" --email-if-configured

if grep -Eq "Network readiness: unavailable|Failed to resolve|NameResolutionError" "$report_md"; then
  echo "Generated report still shows network/DNS failure; refusing to publish an empty report." >&2
  echo "Likely fix: rerun after network is ready, or increase REPORT_NETWORK_WAIT_SECONDS." >&2
  exit 1
fi

git add -f "$report_md" "$report_html"
if git diff --cached --quiet; then
  echo "Generated report has no commit-worthy changes."
  exit 0
fi

git commit -m "Add daily report for ${report_date}"
git push origin HEAD:main
