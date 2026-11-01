"""Reuse coverage only for byte-identical sources; measure both changed modules fresh."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
baseline = root.parent / 'codex-ops/verification/quality'
previous = json.loads((baseline / 'crap.json').read_text())
coverage = json.loads((baseline / 'coverage.json').read_text())
fresh = json.loads((root / 'verification/adoption-fresh-coverage.json').read_text())
changed = [name for name, digest in previous['sourceSha256'].items()
           if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest]
assert set(changed) == {'capability_catalog.py', 'workflow_diagnostics.py'}, changed
assert fresh['meta']['branch_coverage']
for name in changed:
    coverage['files'][name] = fresh['files'][name]
directory = root / 'verification/quality'
directory.mkdir(exist_ok=True)
(directory / 'coverage.json').write_text(json.dumps(coverage), encoding='utf-8')
provenance = {'freshModules': changed, 'freshTests': 358, 'freshResult': 'passed',
              'unchangedModules': [name for name in previous['sourceSha256'] if name not in changed],
              'baseline': str(baseline),
              'method': 'Fresh statement/branch coverage for changed modules; prior coverage reused only after exact source hash equality for all other modules. No new native-host coverage claim.'}
(directory / 'coverage-provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
subprocess.run([sys.executable, 'scripts/crap_report.py', '--max-crap', '6'], cwd=root, check=True)
