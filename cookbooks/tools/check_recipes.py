"""Run every ```python block in the cookbooks against GUESS. Each recipe (a
## section) starts from a fresh, empty session whose working folder holds
cookbooks/data/, so recipes load their data by name, as a reader would after
opening the file. Blocks in a recipe run in order; {.python .norun} blocks
are skipped.

    cd py && .venv/bin/python ../cookbooks/tools/check_recipes.py          # all volumes
    cd py && .venv/bin/python ../cookbooks/tools/check_recipes.py sna      # one
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOKS = HERE.parent
ROOT = BOOKS.parent
sys.path.insert(0, str(ROOT / "py"))
from guess import Session, gv  # noqa: E402

BLOCK = re.compile(r"^```python\n(.*?)^```", flags=re.M | re.S)


def recipes(text):
    """(title, [code blocks]) for each ## section (and the text before the first)."""
    out = []
    for part in re.split(r"^## ", text, flags=re.M):
        blocks = BLOCK.findall(part)
        if blocks:
            out.append((part.splitlines()[0].strip(), blocks))
    return out


def main(only):
    work = tempfile.mkdtemp(prefix="guess-cookbook-")
    for f in (BOOKS / "data").iterdir():
        if f.is_file() and f.suffix != ".py":
            shutil.copy(f, work)
    for f in (ROOT / "gdfs").glob("*.gdf"):           # sample.gdf, adamic-glance.gdf
        shutil.copy(f, work)
    os.chdir(work)
    gv._RUNNER[0] = gv.node_runner(ROOT / "web")
    total = failures = 0
    for book in sorted(BOOKS.glob("*/cookbook.md")):
        vol = book.parent.name
        if only and vol not in only:
            continue
        for title, blocks in recipes(book.read_text()):
            errors = []
            s = Session(lambda m: errors.append(m) if m.get("type") == "error" else None)
            for b in blocks:
                total += 1
                errors.clear()
                if not s.run(b):
                    failures += 1
                    msg = errors[-1] if errors else {}
                    print(f"FAIL [{vol}: {title}]\n{b}\n  -> {(msg.get('text') or msg)!s:.400}\n")
                    break
    print(f"{total - failures}/{total} blocks ran")
    shutil.rmtree(work, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
