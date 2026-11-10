"""Run every ```python block in MANUAL.md against GUESS (blocks marked
{.python .norun} are skipped). Each chapter starts from a fresh session with
the sample graph; blocks in a chapter run in order, like a reader would.

    cd py && .venv/bin/python ../docs/manual/tools/check_examples.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "py"))
from guess import Session  # noqa: E402

SAMPLE = ROOT / "gdfs" / "sample.gdf"
if not SAMPLE.exists():
    SAMPLE = next(ROOT.glob("**/sample.gdf"))

text = (HERE.parent / "MANUAL.md").read_text()

# run in a scratch folder holding sample.gdf, as the app's file space does, so
# examples can say makeFromGDF("sample.gdf") and write exports without litter
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
_work = tempfile.mkdtemp(prefix="guess-manual-")
shutil.copy(SAMPLE, os.path.join(_work, "sample.gdf"))
os.chdir(_work)

# Graphviz layouts: the page's WebAssembly Graphviz, run through Node
from guess import gv  # noqa: E402
gv._RUNNER[0] = gv.node_runner(ROOT / "web")
if gv._RUNNER[0] is None:
    print("note: Graphviz examples need node and web/node_modules; they will fail")
chapters = re.split(r"^# ", text, flags=re.M)
failures = 0
total = 0
for ch in chapters[1:]:
    title = ch.splitlines()[0]
    blocks = re.findall(r"^```python\n(.*?)^```", ch, flags=re.M | re.S)
    if not blocks:
        continue
    errors = []
    s = Session(lambda m: errors.append(m) if m.get("type") == "error" else None)
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})")
    for b in blocks:
        total += 1
        errors.clear()
        if not s.run(b):
            failures += 1
            msg = errors[-1] if errors else {}
            print(f"FAIL [{title}]\n{b}\n  -> {(msg.get('text') or msg.get('message') or msg)!s:.300}\n")
print(f"{total - failures}/{total} blocks ran")
sys.exit(1 if failures else 0)
