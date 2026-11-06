"""The code examples in docs/manual/MANUAL.md run (see docs/manual/README.md)."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "docs" / "manual" / "tools" / "check_examples.py"


def test_manual_examples_run():
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
