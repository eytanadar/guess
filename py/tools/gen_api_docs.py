"""Generate docs/API.md from the live session: every Gython command with its
signature and docstring, grouped by the module that defines it, plus the
built-in fields. Run from py/:  .venv/bin/python tools/gen_api_docs.py
"""
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from guess import Session  # noqa: E402
from guess.analysis import LAZY  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "API.md"

SECTIONS = [
    ("commands", "Graph structure, loading and saving, mapping, view"),
    ("session", "Undo, redo, history and logging"),
    ("analysis", "Statistics, communities, filters and paths"),
    ("algorithms", "Clustering and generators"),
    ("layouts", "Layouts"),
    ("visuals", "Display: hulls, legends, background, edges, labels, selection, export"),
    ("states", "States and morphing"),
    ("ranges", "Ranges (existence intervals)"),
    ("charts", "Charts"),
    ("gui", "Interface building (panels, widgets, timers, events)"),
    ("persist", "Sessions and apps"),
    ("sqlquery", "SQL"),
    ("colors", "Colors"),
]


def signature(name, fn):
    try:
        sig = str(inspect.signature(fn))
    except (TypeError, ValueError):
        sig = "(...)"
    return f"{name}{sig}"


def main():
    s = Session(lambda m: None)
    groups = {}
    for name, (obj, kind) in sorted(s.system.items(), key=lambda kv: kv[0].lower()):
        if kind != "command" or not callable(obj):
            continue
        mod = getattr(obj, "__module__", "") or ""
        key = mod.rsplit(".", 1)[-1] if mod.startswith("guess") else "commands"
        if getattr(obj, "__qualname__", "").startswith("Session.__init__"):
            key = "session"
        groups.setdefault(key, []).append((name, obj))
    lines = [
        "# Gython API reference",
        "",
        "Generated from the docstrings by `py/tools/gen_api_docs.py`; do not edit by hand.",
        "In the console, `help(name)` shows the same text, and hovering a command name",
        "in an executed cell shows it as a tooltip.",
        "",
        "Commands can be called without parentheses when they take no arguments",
        "(`gemLayout` is `gemLayout()`). Colors are names (`red`), `\"r,g,b[,a]\"` or `\"#rrggbb\"`.",
        "",
        "## Contents",
        "",
    ]
    order = [k for k, _ in SECTIONS] + sorted(set(groups) - {k for k, _ in SECTIONS})
    titles = dict(SECTIONS)
    for k in order:
        if k in groups:
            title = titles.get(k, k)
            anchor = title.lower().replace(",", "").replace("(", "").replace(")", "").replace(":", "").replace(" ", "-")
            lines.append(f"- [{title}](#{anchor}) ({len(groups[k])})")
    lines += ["- [Fields](#fields)", "- [Gython syntax](#gython-syntax)", ""]
    for k in order:
        if k not in groups:
            continue
        lines += [f"## {titles.get(k, k)}", ""]
        for name, fn in groups[k]:
            doc = inspect.getdoc(fn) or ""
            lines += [f"### `{signature(name, fn)}`", ""]
            lines += [doc if doc else "_(no description)_", ""]
    g = s.graph
    lines += ["## Fields", "", "Built-in node fields:", "", "| field | type | default |", "|---|---|---|"]
    for f in g.node_schema.values():
        lines.append(f"| `{f.name}` | {f.type} | {f.default!r}{' (read-only)' if f.readonly else ''} |")
    lines += ["", "Built-in edge fields:", "", "| field | type | default |", "|---|---|---|"]
    for f in g.edge_schema.values():
        lines.append(f"| `{f.name}` | {f.type} | {f.default!r}{' (read-only)' if f.readonly else ''} |")
    lines += ["", "Computed node fields (calculated the first time they are used, by name or",
              "as `n.<field>`; `recompute()` after editing the graph): "
              + ", ".join(f"`{k}`" for k in LAZY) + "; edge field `betweenness`.", ""]
    lines += [
        "## Gython syntax", "",
        "Gython is Python 3 plus these graph operators (see the CHI 2006 paper):", "",
        "| expression | meaning |", "|---|---|",
        "| `freq > 10` | elements whose field matches (`==`, `!=`, `<`, `>`, `<=`, `>=`, `like`) |",
        "| `(freq > 10).color = blue` | setting a field on a set sets it on every element |",
        "| `a & b`, `a \\| b` | intersection / union of element sets |",
        "| `a -> b`, `a <- b` | directed edges from a to b / from b to a |",
        "| `a <-> b`, `a - b` | undirected edges between a and b |",
        "| `a ? b` | any edges between a and b |",
        "| `s.difference(t)` | set difference |",
        "| `bob[1999].color` | a value in a saved state |",
        "| `Node rcontains 5` | range queries (`rcontains`, `roverlaps`, `rcontained`) |",
        "| `g.nodes`, `g.edges` | all nodes / edges |",
        "| `sel` | the current display selection |",
        "",
    ]
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({sum(len(v) for v in groups.values())} commands)")


if __name__ == "__main__":
    main()
