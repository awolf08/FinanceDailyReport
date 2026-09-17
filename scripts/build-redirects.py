"""Keep existing Pages URLs working after the report repository migration."""
from pathlib import Path
from html import escape
import shutil

root = Path('_site')
root.mkdir(exist_ok=True)

def redirect(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    url = escape(target, quote=True)
    path.write_text(f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={url}"><link rel="canonical" href="{url}"></head><body><a href="{url}">Open report on Baybell</a></body></html>')

for name in ['index.html', 'latest.html', 'latest/index.html']:
    redirect(root / name, 'https://baybell.com/daily-finance/latest.html')
for path in Path('reports').glob('*'):
    if path.suffix == '.html':
        if path.name.startswith('finance-daily-report-'):
            target = 'daily-finance/' + path.name.removeprefix('finance-daily-report-')
        elif path.name.startswith('weekly-market-events-'):
            target = 'weekly-finance/' + path.name.removeprefix('weekly-market-events-')
        else:
            continue
        redirect(root / 'reports' / path.name, 'https://baybell.com/' + target)
    elif path.is_file():
        (root / 'reports').mkdir(exist_ok=True)
        shutil.copy2(path, root / 'reports' / path.name)
(root / '.nojekyll').touch()
