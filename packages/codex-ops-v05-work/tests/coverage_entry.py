"""Test-only coverage snapshots for processes killed by native Windows Jobs."""
from pathlib import Path


def instrument(folder, entry):
    package = Path(__file__).resolve().parents[1]
    wrapper = folder / ('covered_' + entry.name)
    # All values are local paths rendered as Python literals, never shell input.
    source = f'''import runpy, sys, threading
import coverage
sys.path.insert(0, {str(entry.parent)!r})
cov = coverage.Coverage(config_file={str(package / '.coveragerc')!r},
    source=[{str(package)!r}], data_file={str(package / 'verification/quality/.coverage')!r}, data_suffix=True)
cov.set_option('run:patch', [])
cov.start()
stop = threading.Event()
def snapshot():
    while not stop.wait(0.1):
        cov.save()
worker = threading.Thread(target=snapshot, daemon=True)
worker.start()
try:
    runpy.run_path({str(entry)!r}, run_name='__main__')
finally:
    stop.set()
    worker.join(timeout=1)
    cov.stop()
    cov.save()
'''
    wrapper.write_text(source, encoding='utf-8')
    return wrapper
