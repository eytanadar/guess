"""Build the "GUESS for X" cookbooks with pandoc: each volume's cookbook.md ->
HTML, PDF and EPUB in cookbooks/build/, plus an index page linking them all.

    py/.venv/bin/python cookbooks/tools/build.py               # every volume, every format
    py/.venv/bin/python cookbooks/tools/build.py sna html      # some volumes / formats

Uses the manual's stylesheet and LaTeX header (docs/manual/tools). Check the
recipes first with tools/check_recipes.py; make the figures with
`cd web && npm run cookbook-shots`.
"""
import datetime
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOKS = HERE.parent
ROOT = BOOKS.parent
OUT = BOOKS / "build"
MANUAL_TOOLS = ROOT / "docs" / "manual" / "tools"
sys.path.insert(0, str(ROOT / "docs" / "manual"))
from build import font_args  # noqa: E402  (the manual's font picker)
sys.path.insert(0, str(HERE))

VOLUMES = ["core", "sna", "biology", "text", "infrastructure", "software", "investigations", "ecology", "epidemiology"]   # reading order


def volumes():
    found = [p.parent.name for p in sorted(BOOKS.glob("*/cookbook.md"))]
    return sorted(found, key=lambda v: VOLUMES.index(v) if v in VOLUMES else len(VOLUMES))


def meta(vol):
    """title/subtitle from the cookbook's YAML block."""
    text = (BOOKS / vol / "cookbook.md").read_text()
    m = re.match(r"---\n(.*?)\n---", text, flags=re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"')
    return out


COMMON = ["--from", "markdown+raw_tex", "--toc", "--toc-depth=2", "--syntax-highlighting=tango",
          "--number-sections"]
FORMATS = {
    "html": ["--standalone", "--embed-resources", "--css", str(MANUAL_TOOLS / "manual.css"),
             "--css", str(HERE / "cookbook.css"),
             "--include-after-body", str(MANUAL_TOOLS / "copy-code.html")],
    "pdf": ["--pdf-engine=xelatex", "-V", "geometry:margin=1in", "-V", "fontsize=11pt",
            "-V", "colorlinks=true", "-V", "linkcolor=[HTML]{1F4E8C}", "-V", "urlcolor=[HTML]{1F4E8C}",
            "-V", "documentclass=article", "-V", "papersize=letter",
            "--include-in-header", str(MANUAL_TOOLS / "header.tex")],
    "epub": ["--css", str(MANUAL_TOOLS / "manual.css"), "--css", str(HERE / "cookbook.css"),
             "--split-level=1"],
}


def build(vol, fmts):
    src = BOOKS / vol / "cookbook.md"
    OUT.mkdir(exist_ok=True)
    for fmt in fmts:
        out = OUT / f"GUESS-for-{vol}.{fmt}"
        extra = font_args() if fmt == "pdf" else []
        cmd = ["pandoc", str(src), "-o", str(out), "--resource-path", f"{BOOKS / vol}:{ROOT}",
               *COMMON, *FORMATS[fmt], *extra]
        print(f"  {out.relative_to(ROOT)}")
        subprocess.run(cmd, check=True, cwd=BOOKS / vol)


def write_index():
    from datasets import used_by
    items = []
    for vol in volumes():
        m = meta(vol)
        links = " · ".join(f'<a href="GUESS-for-{vol}.{f}">{f.upper()}</a>'
                           for f in FORMATS if (OUT / f"GUESS-for-{vol}.{f}").exists())
        if links:
            items.append(f'<li><div class="t">{html.escape(m.get("title", vol))}</div>'
                         f'<div class="note">{html.escape(m.get("subtitle", ""))}</div>'
                         f'<div class="links">{links}</div>'
                         + (f'<div class="data">Data: ' + " · ".join(f'<a href="data/{f}" download>{f}</a>' for f in used_by(vol))
                            + "</div>" if used_by(vol) else "")
                         + "</li>")
    (OUT / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GUESS cookbooks</title>
<style>
  :root {{ --text: #1d1f23; --muted: #5b616b; --bg: #fff; --border: #dfe2e6; --link: #1f4e8c; color-scheme: light dark; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --text: #e4e6ea; --muted: #a0a6b0; --bg: #17181b; --border: #3a3d44; --link: #8ab4f8; }}
  }}
  body {{ margin: 0 auto; max-width: 42rem; padding: 3rem 16px; background: var(--bg); color: var(--text);
         font: 17px/1.55 "Avenir Next", "Helvetica Neue", system-ui, sans-serif; }}
  h1 {{ font-size: 2.2rem; margin: 0; }}
  .sub {{ color: var(--muted); margin: .2rem 0 2rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: .9rem 0; border-top: 1px solid var(--border); }}
  li:last-child {{ border-bottom: 1px solid var(--border); }}
  .t {{ font-weight: 600; font-size: 1.15rem; }}
  .note {{ color: var(--muted); font-size: .95rem; }}
  a {{ color: var(--link); font-weight: 600; }}
  .data {{ font-size: .85rem; color: var(--muted); margin-top: .25rem; }}
  .data a {{ font-weight: 400; }}
  footer {{ color: var(--muted); font-size: .85rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>GUESS cookbooks</h1>
<p class="sub">Short, runnable recipes for network analysis in GUESS, one book per field.
Start with the Kitchen; the field books build on it.</p>
<ul>
{chr(10).join(items)}
</ul>
<footer>Built {datetime.date.today().isoformat()}. Every code sample in these books is run by the build.
In GUESS the data files are already available: open them by name. Sources and licences: <a href="data/README.md">datasets README</a>.
On the GUESS site, <a href="../">the manual</a> is one level up.</footer>
</body>
</html>
""")
    print(f"  {(OUT / 'index.html').relative_to(ROOT)}")


def main(args):
    if not shutil.which("pandoc"):
        sys.exit("pandoc not found (https://pandoc.org/installing.html)")
    vols = [a for a in args if a in volumes()] or volumes()
    fmts = [a for a in args if a in FORMATS] or list(FORMATS)
    for v in vols:
        build(v, fmts)
    write_index()


if __name__ == "__main__":
    main(sys.argv[1:])
