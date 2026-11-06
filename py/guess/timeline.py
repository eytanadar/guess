"""Time: show the graph as it was at a moment (Gephi's timeline).

Time comes from existence ranges (addRange(v1, "1990-1995")) or from a numeric
field such as year. The Timeline panel scrubs and plays through it.

    showTime(1994)                      only what exists in 1994 (ranges)
    showTime(1994, year)                nodes/edges with year <= 1994 (cumulative)
    showTime(1994, year, window=5)      ... with 1989 < year <= 1994
    showAll()                           everything again
"""
import math

from .model import EDGE, NODE, Edge, Field, GuessError, Node


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _inside(iv, t):
    return any(lo <= t <= hi for lo, hi in iv)


def info(graph, field_name=None, bins=60):
    """Time domain and a count per step, for the panel's slider and sparkline."""
    if field_name:
        f = graph.node_schema.get(field_name) or graph.edge_schema.get(field_name)
        if f is None:
            raise GuessError(f"no field {field_name!r}")
        vals = [v for v in (_num(f.get(x)) for x in f.elements()) if v is not None]
        if not vals:
            raise GuessError(f"field {field_name!r} has no numbers")
        lo, hi = min(vals), max(vals)
        steps = _steps(lo, hi, all(float(v).is_integer() for v in vals), bins)
        svals = sorted(vals)
        import bisect
        counts = [bisect.bisect_right(svals, t) for t in steps]
        return {"source": field_name, "min": lo, "max": hi, "steps": steps, "counts": counts,
                "kind": "node" if f.kind == NODE else "edge"}
    ivs = [iv for e, iv in graph.ranges.items() if graph._alive(e)]
    if not ivs:
        return {"source": None, "min": 0, "max": 0, "steps": [], "counts": []}
    lo = min(a for iv in ivs for a, _b in iv)
    hi = max(b for iv in ivs for _a, b in iv)
    steps = _steps(lo, hi, all(float(x).is_integer() for iv in ivs for p in iv for x in p), bins)
    counts = [sum(1 for iv in ivs if _inside(iv, t)) for t in steps]
    return {"source": "ranges", "min": lo, "max": hi, "steps": steps, "counts": counts, "kind": "both"}


def _steps(lo, hi, integer, bins):
    if hi <= lo:
        return [lo]
    if integer and hi - lo <= 400:
        return [float(t) for t in range(int(lo), int(hi) + 1)]
    return [lo + (hi - lo) * k / (bins - 1) for k in range(bins)]


def install(session):
    g = session.graph

    def showTime(t, field=None, window=None):
        """showTime(t) shows only the nodes and edges whose ranges contain time t
        (elements without ranges stay visible); showTime(t, field) shows those
        whose numeric field is <= t (window=w: only within the last w).
        Edges are shown only when both ends are."""
        t = float(t)
        w = None if window is None else float(window)

        def ok(v):
            v = _num(v)
            return v is not None and v <= t and (w is None or v > t - w)

        if isinstance(field, str):            # showTime(1995, "year") as well as showTime(1995, year)
            field = session.ns.get(field, field)
        if field is not None:
            if not isinstance(field, Field):
                raise GuessError("showTime(t, field) needs a field, e.g. year")
            for n in g._nodes_list():
                n.visible = ok(field.get(n)) if field.kind == NODE else True
            for e in g._edges_list():
                ends = e._n1.visible and e._n2.visible
                e.visible = ends and (ok(field.get(e)) if field.kind == EDGE else True)
            return
        for n in g._nodes_list():
            iv = g.ranges.get(n)
            n.visible = True if iv is None else _inside(iv, t)
        for e in g._edges_list():
            iv = g.ranges.get(e)
            e.visible = e._n1.visible and e._n2.visible and (True if iv is None else _inside(iv, t))

    session.register_command("showTime", showTime)


__all__ = ["install", "info", "Node", "Edge"]
