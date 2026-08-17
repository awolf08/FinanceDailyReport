#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

timezone="${REPORT_TIMEZONE:-America/Los_Angeles}"
report_date="${REPORT_DATE:-$(TZ="$timezone" date +%F)}"
force_generate="${REPORT_FORCE_GENERATE:-false}"
dry_run="${REPORT_DRY_RUN:-false}"
output_dir="${REPORT_OUTPUT_DIR:-reports}"
report_stem="${output_dir}/weekly-market-events-${report_date}"
report_md="${report_stem}.md"
report_html="${report_stem}.html"
repo_report_stem="reports/weekly-market-events-${report_date}"
repo_report_md="${repo_report_stem}.md"
repo_report_html="${repo_report_stem}.html"

if [ "$(git branch --show-current)" != "main" ]; then
  echo "Weekly publish must run from the main branch." >&2
  exit 1
fi

git fetch --prune origin

if [ -n "$(git status --porcelain --untracked-files=no -- . ':(exclude)reports')" ]; then
  echo "Working tree has tracked changes. Commit or stash them before weekly publish." >&2
  git status --short
  exit 1
fi

git pull --rebase origin main

report_exists_on_origin=false
if git cat-file -e "origin/main:${repo_report_md}" 2>/dev/null && git cat-file -e "origin/main:${repo_report_html}" 2>/dev/null; then
  report_exists_on_origin=true
  if [ "$force_generate" = "true" ]; then
    echo "Weekly report for ${report_date} already exists on origin/main. Force-generating for test."
  else
    echo "Weekly report for ${report_date} already exists on origin/main. Skipping generation."
  fi
fi

if [ "$report_exists_on_origin" = "false" ] || [ "$force_generate" = "true" ]; then
  python3 -m finance_daily_report --weekly --date "$report_date" --format both --output-dir "$output_dir"

  if grep -Eq "No high-impact macro events|No watched mega-cap earnings|Source Health" "$report_md"; then
    echo "Weekly report generated; one or more sections may be empty. Publishing because sparse event weeks are valid."
  fi

  if [ "$dry_run" = "true" ]; then
    echo "Dry run enabled. Skipping commit and push."
    exit 0
  fi

  git add -f "$report_md" "$report_html"
  if git diff --cached --quiet; then
    echo "Weekly report has no commit-worthy changes."
  else
    git commit -m "Add weekly market events report for ${report_date}"
    git push origin HEAD:main
  fi
fi

echo "Weekly report ready:"
echo "- ${report_md}"
echo "- ${report_html}"
