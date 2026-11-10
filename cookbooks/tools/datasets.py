"""Which data files each cookbook uses: every quoted file name in its code
blocks that exists in cookbooks/data or gdfs. Used by the manual's and the
cookbooks' index pages, which link the files (deployed at
manuals/cookbooks/data/ by web/scripts/copy-manuals.mjs)."""
import re
from pathlib import Path

BOOKS = Path(__file__).resolve().parent.parent
ROOT = BOOKS.parent
DIRS = (BOOKS / "data", ROOT / "gdfs")
EXT = (".gdf", ".csv", ".txt")


def available():
    out = {}
    for d in DIRS:
        for f in sorted(d.iterdir()):
            if f.suffix in EXT and f.name not in out:
                out[f.name] = f
    return out


def used_by(volume):
    text = (BOOKS / volume / "cookbook.md").read_text()
    code = "\n".join(re.findall(r"^```[^\n]*\n(.*?)^```", text, flags=re.M | re.S))
    have = available()
    seen = []
    for name in re.findall(r"[\"']([\w.-]+\.(?:gdf|csv|txt))[\"']", code):
        if name in have and name not in seen:
            seen.append(name)
    return seen
