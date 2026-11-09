"""Visual mappings and named styles (Cytoscape styles / Kumu perspectives), and
the data table. The style panel in the page writes these commands.

    labelBy(dept)                      labels from a field
    shapeBy(dept)                      a node shape per value
    legendFor(dept)                    a legend for the current colouring
    defineStyle("dept view", ["colorize(dept)", "legendFor(dept)"])
    applyStyle("dept view")            run a style's commands (one undo step)
    table(dept == 'dept3')             show elements in the data table
"""
import math

from . import colors
from .model import EDGE, NODE, Edge, Field, GSet, GuessError, Node, elements_of, group_by

# node shapes cycled by shapeBy: circle, square, rounded square
SHAPES = [2, 1, 3]


def install(session):
    g = session.graph
    view = session.view

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def field_arg(f, what):
        if not isinstance(f, Field):
            raise GuessError(f"{what} needs a field, e.g. {what}(dept)")
        return f

    @cmd
    def labelBy(field, show=True):
        """labelBy(field) sets each node's (or edge's) label to its value of field
        and shows the labels; labelBy(field, false) sets them without showing."""
        f = field_arg(field, "labelBy")
        for x in f.elements():
            v = f.get(x)
            x.label = "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
            if show:
                x.labelvisible = True

    @cmd
    def shapeBy(field):
        """shapeBy(field) gives each value of a node field its own shape (circle,
        square, rounded square, repeating), the most common value first."""
        f = field_arg(field, "shapeBy")
        if f.kind != NODE:
            raise GuessError("shapeBy needs a node field")
        groups = sorted(group_by(f.elements(), f), key=len, reverse=True)
        for i, grp in enumerate(groups):
            grp.style = SHAPES[i % len(SHAPES)]

    @cmd
    def legendFor(field, title=None):
        """legendFor(field) adds a legend explaining the current colours by field:
        one entry per value (for categories, as after colorize), or a gradient
        from the lowest to the highest value (for numbers, as after colorBy)."""
        f = field_arg(field, "legendFor")
        from .visuals import GradientLegend, Legend
        elems = f.elements()
        vals = [(x, f.get(x)) for x in elems if f.get(x) is not None]
        if not vals:
            raise GuessError(f"field '{f.name}' has no values")
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for _x, v in vals)
        groups = group_by(elems, f)
        if numeric and len(groups) > 12 and _looks_like_gradient(groups, f):
            lo = min(vals, key=lambda p: p[1])
            hi = max(vals, key=lambda p: p[1])
            lg = GradientLegend(view, view.next_id(), lo[0].color, hi[0].color, _num(lo[1]), _num(hi[1]))
        else:
            # categories (e.g. after colorize): one entry per value, the biggest first
            lg = Legend(view, view.next_id())
            groups = sorted(groups, key=len, reverse=True)
            shown = groups if len(groups) <= 16 else groups[:12]
            for grp in shown:
                lg.add(grp[0], f"{title + ': ' if title else ''}{f.get(grp[0])}")
            if len(shown) < len(groups):
                rest = groups[len(shown):]
                lg.note(f"… {len(rest)} more ({sum(map(len, rest))} {'nodes' if f.kind == NODE else 'edges'})")
        view.legends[lg._id] = lg
        view.changed()
        return lg

    # ---- named styles ----------------------------------------------------------
    @cmd
    def defineStyle(name, commands):
        """defineStyle(name, [command, ...]) saves a named style: Gython lines that
        set colours, sizes, labels, legends or display settings. Styles are saved
        with the session; the style panel builds them for you."""
        if isinstance(commands, str):
            commands = [commands]
        lines = [str(c) for c in commands if str(c).strip()]
        if not lines:
            raise GuessError("a style needs at least one command")
        view.styles[str(name)] = lines
        view.changed()

    @cmd
    def applyStyle(name):
        """applyStyle(name) runs a style's commands (one undo step)."""
        lines = view.styles.get(str(name))
        if lines is None:
            raise GuessError(f"no style {name!r} (styles: {', '.join(map(repr, view.styles)) or 'none'})")
        from . import compiler
        for line in lines:
            names = set()
            code = compiler.compile_gython(line, is_protected=session.is_protected, interactive=False,
                                           filename=f"<style {name}>", names=names)
            session._prepare_fields(names)
            exec(code, session.ns)

    @cmd
    def getStyles():
        """The saved styles: {name: [commands]}."""
        return {k: list(v) for k, v in view.styles.items()}

    @cmd
    def removeStyle(name):
        """removeStyle(name) deletes a saved style."""
        if view.styles.pop(str(name), None) is None:
            raise GuessError(f"no style {name!r}")
        view.changed()

    # ---- data table ---------------------------------------------------------------
    @cmd
    def table(seq=None):
        """table() opens the data table of all nodes; table(seq) shows just those
        nodes or edges (e.g. table(sel), table(freq > 10), table(g.edges))."""
        if seq is None:
            session.emit({"type": "table", "kind": "n", "ids": None})
            return
        items = list(elements_of(seq)) if not isinstance(seq, (Node, Edge)) else [seq]
        nodes = [x._id for x in items if isinstance(x, Node)]
        edges = [x._id for x in items if isinstance(x, Edge)]
        if seq is g.edges or (edges and not nodes):
            session.emit({"type": "table", "kind": "e", "ids": None if _is_all(seq, g, EDGE) else edges})
        else:
            session.emit({"type": "table", "kind": "n", "ids": None if _is_all(seq, g, NODE) else nodes})


def _is_all(seq, g, kind):
    return isinstance(seq, GSet) and getattr(seq, "annotation", None) == ("g.nodes" if kind == NODE else "g.edges")


def _looks_like_gradient(groups, f):
    """Do the colours follow the values smoothly (colorBy) rather than jump
    between unrelated colours (colorize)? Walking the values in order, a
    gradient's colours trace a short path (lowest → [middle →] highest); one
    colour per category zigzags all over the colour space."""
    def rgb(x):
        c, _a = colors.to_rgba_int(x.color)
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    pts = [rgb(grp[0]) for grp in sorted(groups, key=lambda grp: f.get(grp[0]))]
    dist = lambda p, q: sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5
    path = sum(dist(p, q) for p, q in zip(pts, pts[1:]))
    lo, hi = pts[0], pts[-1]
    direct = max(dist(lo, m) + dist(m, hi) for m in pts)   # allows one middle stop
    return path <= 1.3 * direct + 10


def _num(v):
    v = float(v)
    return int(v) if v.is_integer() else round(v, 4)


# ---------------------------------------------------------------------------
# data for the page's panels (table, filters, style panel, palette)
# ---------------------------------------------------------------------------

def _jsonv(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    return str(v)


def table_data(graph, kind, ids=None):
    """Fields and rows for the data table: {"fields": [{name, type, editable}],
    "rows": [[id, label, v1, v2, ...], ...]}."""
    schema = graph.node_schema if kind == "n" else graph.edge_schema
    skip = {"name"} if kind == "n" else set()
    fields = [f for f in schema.values() if f.name not in skip]
    if ids is None:
        elems = graph._nodes_list() if kind == "n" else graph._edges_list()
    else:
        look = graph.node_by_id if kind == "n" else graph.edge_by_id
        elems = [x for x in map(look, ids) if x is not None]
    rows = []
    for x in elems:
        head = x._name if kind == "n" else repr(x)
        rows.append([x._id, head] + [_jsonv(f.get(x)) for f in fields])
    return {"fields": [{"name": f.name, "type": f.type, "editable": not f.readonly and f.compute is None}
                       for f in fields], "rows": rows}


def field_info(graph, kind, bins=24):
    """Per field: type, numeric range and histogram, or the most common values
    (for filters, the style panel and the command palette)."""
    schema = graph.node_schema if kind == "n" else graph.edge_schema
    elems = graph._nodes_list() if kind == "n" else graph._edges_list()
    out = []
    for f in schema.values():
        if f.name in ("name", "image", "node1", "node2"):
            continue
        vals = [f.get(x) for x in elems]
        vals = [v for v in vals if v is not None]
        info = {"name": f.name, "type": f.type, "builtin": f.builtin}
        nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(float(v))]
        if nums and len(nums) == len(vals):
            lo, hi = min(nums), max(nums)
            counts = [0] * bins
            for v in nums:
                k = 0 if hi == lo else min(bins - 1, int((v - lo) / (hi - lo) * bins))
                counts[k] += 1
            info.update(numeric=True, min=lo, max=hi, hist=counts, integer=all(float(v).is_integer() for v in nums))
        else:
            freq = {}
            for v in vals:
                key = _jsonv(v)
                freq[key] = freq.get(key, 0) + 1
            top = sorted(freq.items(), key=lambda kv: (-kv[1], str(kv[0])))
            info.update(numeric=False, values=[[k, c] for k, c in top[:60]], distinct=len(freq))
        out.append(info)
    return out


__all__ = ["install", "table_data", "field_info", "colors"]
