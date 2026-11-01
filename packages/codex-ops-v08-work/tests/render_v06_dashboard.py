"""Render the local snapshot with an owned headless browser profile."""
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
browser = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
assert browser.is_file()
page = root / 'verification/dashboard-v06.html'
assert page.is_file()
profile = Path(tempfile.mkdtemp(prefix='codex-ops-v06-dashboard-'))
reports = []
for width in (1280, 420):
    target = root / f'verification/dashboard-v06-{width}.png'
    run = subprocess.run([str(browser), '--headless', '--disable-gpu',
        '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(profile),
        '--window-size=' + str(width) + ',1100', '--screenshot=' + str(target),
        '--timeout=10000', page.as_uri()], capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert run.returncode == 0 and target.is_file(), run.stderr.decode(errors='replace')[-1000:]
    reports.append({'width': width, 'screenshot': str(target), 'bytes': target.stat().st_size})
(root / 'verification/dashboard-v06-render.json').write_text(json.dumps({
    'browser': str(browser), 'ownedProfile': str(profile), 'reports': reports,
    'scope': 'Static local dashboard; live refresh server separately covered by tests'}, indent=2))
print(json.dumps(reports))
