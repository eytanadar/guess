"""Build the GUESS manual: MANUAL.md plus generated appendices -> PDF, HTML,
EPUB and Word, with pandoc.

    python3 docs/manual/build.py              # all formats
    python3 docs/manual/build.py pdf html     # some

Output goes to docs/manual/build/, with an index.html that links the formats
(the deploy scripts copy it all to manuals/ on the site). The colour table (Appendix A) comes from
py/guess/colors.py and the command reference (Appendix D) from docs/API.md
(regenerate that with py/tools/gen_api_docs.py), so both follow the code.

Needs pandoc 3; the PDF also needs XeLaTeX (TeX Live / MacTeX). Figures are
made by `cd web && npm run manual-shots` (docs/manual/img) and
`npm run help-shots` (web/public/help).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "build"
sys.path.insert(0, str(ROOT / "py"))


def color_table():
    from guess import colors
    items = sorted(colors.COLORS.items(), key=lambda kv: kv[0].lower())
    cols = 3
    rows = (len(items) + cols - 1) // cols
    head = "| " + " | ".join(["name", "r, g, b"] * cols) + " |\n|" + "---|" * (2 * cols) + "\n"
    lines = []
    for r in range(rows):
        cells = []
        for c in range(cols):
            i = c * rows + r
            if i < len(items):
                name, rgb = items[i]
                cells += [f"`{name.lower()}`", ", ".join(str(int(v)) for v in rgb[:3])]
            else:
                cells += ["", ""]
        lines.append("| " + " | ".join(cells) + " |")
    return head + "\n".join(lines) + "\n"


def api_reference():
    text = (ROOT / "docs" / "API.md").read_text()
    # drop the title, intro and contents; keep the sections
    body = text[text.index("\n## ", text.index("## Contents") + 5):]
    body = re.sub(r"^(#{2,}) ", lambda m: m.group(1) + " ", body, flags=re.M)
    intro = ("Every command, generated from the code's own documentation (the same text "
             "as `help(name)` and the Help panel).\n")
    return "# Appendix D. Command reference\n\n" + intro + body


def assemble():
    src = (HERE / "MANUAL.md").read_text()
    src = src.replace("<!-- COLOR-TABLE -->", color_table())
    src = src.replace("<!-- API-REFERENCE -->", "\\newpage\n\n" + api_reference())
    OUT.mkdir(exist_ok=True)
    full = OUT / "GUESS-manual.md"
    full.write_text(src)
    return full


def font_args():
    """Fonts for the PDF: nicer ones when installed, LaTeX defaults otherwise."""
    try:
        have = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return []
    args = []
    for var, choices in (("mainfont", ["Charter", "STIX Two Text", "DejaVu Serif"]),
                         ("sansfont", ["Avenir Next", "Helvetica Neue", "DejaVu Sans"]),
                         ("monofont", ["Menlo", "DejaVu Sans Mono"])):
        for f in choices:
            if re.search(rf"^{re.escape(f)}(,|$)", have, flags=re.M):
                args += ["-V", f"{var}={f}"]
                break
    return args


COMMON = ["--from", "markdown+raw_tex", "--resource-path", f"{HERE}:{ROOT}", "--toc", "--toc-depth=2",
          "--syntax-highlighting=tango"]

FORMATS = {
    "pdf": ["--pdf-engine=xelatex", "-V", "geometry:margin=1in", "-V", "fontsize=11pt",
            "-V", "colorlinks=true", "-V", "linkcolor=[HTML]{1F4E8C}", "-V", "urlcolor=[HTML]{1F4E8C}",
            "-V", "documentclass=article", "-V", "papersize=letter",
            "--include-in-header", str(HERE / "tools" / "header.tex")],
    "html": ["--standalone", "--embed-resources", "--css", str(HERE / "tools" / "manual.css"),
             "--include-after-body", str(HERE / "tools" / "copy-code.html"),
             "--metadata", "pagetitle=GUESS manual"],
    "epub": ["--css", str(HERE / "tools" / "manual.css"), "--split-level=1"],
    "docx": [],
}


LABELS = {
    "html": ("Web page", "one self-contained page; read it in the browser"),
    "pdf": ("PDF", "for printing and reading offline"),
    "epub": ("EPUB", "for e-readers (Apple Books, Kobo, …)"),
    "docx": ("Word", "to edit or excerpt"),
}


def write_index():
    """build/index.html: links to whichever formats have been built."""
    import datetime
    rows = []
    for fmt, (label, note) in LABELS.items():
        f = OUT / f"GUESS-manual.{fmt}"
        if f.exists():
            mb = f.stat().st_size / 1e6
            rows.append(f'<li><a href="{f.name}">{label}</a> <span class="meta">{f.name} · {mb:.1f} MB</span>'
                        f'<div class="note">{note}</div></li>')
    date = datetime.date.today().isoformat()
    (OUT / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GUESS manual</title>
<style>
  :root {{ --text: #1d1f23; --muted: #5b616b; --bg: #fff; --border: #dfe2e6; --link: #1f4e8c; color-scheme: light dark; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --text: #e4e6ea; --muted: #a0a6b0; --bg: #17181b; --border: #3a3d44; --link: #8ab4f8; }}
  }}
  body {{ margin: 0 auto; max-width: 40rem; padding: 3rem 16px; background: var(--bg); color: var(--text);
         font: 17px/1.55 "Avenir Next", "Helvetica Neue", system-ui, sans-serif; }}
  h1 {{ font-size: 2.2rem; margin: 0; }}
  .sub {{ color: var(--muted); margin: .2rem 0 2rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: .9rem 0; border-top: 1px solid var(--border); }}
  li:last-child {{ border-bottom: 1px solid var(--border); }}
  a {{ color: var(--link); font-weight: 600; font-size: 1.1rem; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-left: .5rem; }}
  .note {{ color: var(--muted); font-size: .95rem; }}
  footer {{ color: var(--muted); font-size: .85rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>GUESS manual</h1>
<p class="sub">The Graph Exploration System, for the web</p>
<ul>
{chr(10).join(rows)}
</ul>
<footer>Built {date}. The same manual in each format, including the full command reference (Appendix D).</footer>
</body>
</html>
""")
    print(f"  {(OUT / 'index.html').relative_to(ROOT)}")


def main(which):
    if not shutil.which("pandoc"):
        sys.exit("pandoc not found (https://pandoc.org/installing.html)")
    full = assemble()
    for fmt in which:
        out = OUT / f"GUESS-manual.{fmt}"
        extra = font_args() if fmt == "pdf" else []
        cmd = ["pandoc", str(full), "-o", str(out), *COMMON, *FORMATS[fmt], *extra]
        print(f"  {out.relative_to(ROOT)}")
        subprocess.run(cmd, check=True, cwd=HERE)
    write_index()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in FORMATS] or list(FORMATS)
    main(args)
