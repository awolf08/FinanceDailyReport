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
reports_site_repo="${REPORTS_SITE_REPO:-https://github.com/awolf08/reports.git}"

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

if [ ! -f "$report_html" ] || [ ! -f "$report_md" ]; then
  echo "Weekly report files for ${report_date} are missing locally after sync." >&2
  exit 1
fi

reports_site_dir="$(mktemp -d)"
git clone "$reports_site_repo" "$reports_site_dir"
mkdir -p "$reports_site_dir/weekly-finance"
cp "$report_html" "$reports_site_dir/weekly-finance/${report_date}.html"
cp "$report_md" "$reports_site_dir/weekly-finance/${report_date}.md"
cat > "$reports_site_dir/weekly-finance/index.html" <<EOF
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly Finance Report</title>
  <script>
    location.replace("./${report_date}.html");
  </script>
</head>
<body>
  <p>Opening the latest Weekly Finance Report.</p>
  <p><a href="./${report_date}.html">Open latest report</a></p>
</body>
</html>
EOF

python3 - "$reports_site_dir/index.html" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

html = path.read_text(encoding="utf-8")
if 'href="./weekly-finance/"' not in html:
    html = html.replace(
        '<a href="./daily-finance/">Daily Finance</a>',
        '<a href="./daily-finance/">Daily Finance</a>\n        <a href="./weekly-finance/">Weekly Finance</a>',
    )
if 'metric-label">Weekly Finance<' not in html:
    insert_after = '''          <a class="metric-card" href="./daily-finance/">
            <span class="metric-icon">DF</span>
            <span class="metric-label">Daily Finance</span>
            <strong>Live</strong>
            <small>Auto-published latest report</small>
          </a>'''
    weekly_card = insert_after + '''
          <a class="metric-card" href="./weekly-finance/">
            <span class="metric-icon">WF</span>
            <span class="metric-label">Weekly Finance</span>
            <strong>Live</strong>
            <small>Next-week market events</small>
          </a>'''
    html = html.replace(insert_after, weekly_card)
path.write_text(html, encoding="utf-8")
PY

(
  cd "$reports_site_dir"
  git config user.name "FinanceDailyReport weekly publisher"
  git config user.email "weekly@users.noreply.github.com"
  git add index.html weekly-finance/
  if git diff --cached --quiet; then
    echo "Reports site already contains weekly report ${report_date}."
  else
    git commit -m "Publish weekly finance report for ${report_date}"
    git push origin HEAD:main
  fi
)

echo "Weekly report ready:"
echo "- ${report_md}"
echo "- ${report_html}"
echo "- https://baybell.com/weekly-finance/${report_date}.html"
