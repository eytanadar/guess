"""Richer node and edge drawing: pie-chart nodes, borders by field, and edge
bundling (Cytoscape's enhancedGraphics, Gephi's edge bundling).

    pieChart([sales, support, rnd])     each node a pie of those numeric fields
    pieNeighbors(dept)                  each node a pie of its neighbours' depts
    pieOff()
    borderBy(dept)                      a border colour per value (wider borders)
    bundleEdges(modularity_class)       route edges between groups through
                                        their centres, so parallel flows merge
    unbundleEdges()
"""
import math
from collections import Counter

from . import colors
from .model import Field, GuessError, NODE, group_by

MAX_SLICES = 8


def install(session):
    g = session.graph
    view = session.view

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def field(f, what, kind=NODE):
        if not isinstance(f, Field) or f.kind != kind:
            raise GuessError(f"{what} needs a node field")
        return f

    def mark_all():
        for n in g._nodes_list():
            g._mark(n)
        # a legend for the slices (replacing an earlier pie legend)
        from .visuals import Legend
        old = getattr(view, "pie_legend", None)
        if old is not None:
            view.legends.pop(old, None)
        view.pie_legend = None
        if view.pie:
            lg = Legend(view, view.next_id())
            for label, c in zip(view.pie["labels"], view.pie["colors"]):
                lg.add(c, label)
            view.legends[lg._id] = lg
            view.pie_legend = lg._id
        view.changed()

    @cmd
    def pieChart(fields, palette=None):
        """pieChart([f1, f2, ...]) draws each node as a pie whose slices are the
        node's values of those numeric fields; palette=[colors] sets slice colours."""
        fs = [field(f, "pieChart") for f in (fields if isinstance(fields, (list, tuple)) else [fields])]
        if not fs:
            raise GuessError("pieChart needs at least one field")
        cols = list(palette) if palette else colors.distinctColors(len(fs))
        view.pie = {"mode": "fields", "fields": [f.name for f in fs],
                    "labels": [f.name for f in fs], "colors": [colors.normalize(c) for c in cols[:len(fs)]]}
        mark_all()

    @cmd
    def pieNeighbors(fld):
        """pieNeighbors(field) draws each node as a pie of its neighbours' values of
        a categorical field (the most common values; the rest as "other")."""
        f = field(fld, "pieNeighbors")
        common = [v for v, _ in Counter(f.get(n) for n in g._nodes_list()).most_common()]
        keep = common[:MAX_SLICES - 1] if len(common) > MAX_SLICES else common
        labels = [str(v) for v in keep] + (["other"] if len(common) > len(keep) else [])
        cols = colors.distinctColors(len(keep)) + (["200,200,200"] if len(labels) > len(keep) else [])
        view.pie = {"mode": "neighbors", "field": f.name, "values": keep, "labels": labels, "colors": cols}
        mark_all()

    @cmd
    def pieOff():
        """Draw nodes normally again (after pieChart / pieNeighbors)."""
        view.pie = None
        mark_all()

    @cmd
    def borderBy(fld, width=2.5):
        """borderBy(field) gives node borders a distinct colour per value of a
        field (as colorize does for fills) and widens them."""
        f = field(fld, "borderBy")
        grps = sorted(group_by(f.elements(), f), key=len, reverse=True)
        for grp, c in zip(grps, colors.distinctColors(len(grps), seed=7)):
            grp.strokecolor = c
        view.border_width = float(width)
        view.changed()

    @cmd
    def bundleEdges(fld, strength=0.85):
        """bundleEdges(field) routes each edge between two groups (values of a node
        field, e.g. modularity_class) through the groups' centres, so edges
        between the same groups merge into bundles. strength 0..1 (0 = straight).
        Layouts and unbundleEdges() straighten them again."""
        f = field(fld, "bundleEdges")
        beta = min(max(float(strength), 0.0), 1.0)
        cent = {}
        for grp in group_by(f.elements(), f):
            xs = [_c(n, "x") for n in grp]
            ys = [_c(n, "y") for n in grp]
            cent[f.get(grp[0])] = (sum(xs) / len(xs), sum(ys) / len(ys))
        n_bundled = 0
        for e in g._edges_list():
            a, b = e._n1, e._n2
            ga, gb = f.get(a), f.get(b)
            if a is b or ga == gb:
                g.set_bends(e, None)
                continue
            pa, pb = (_c(a, "x"), _c(a, "y")), (_c(b, "x"), _c(b, "y"))
            ctrl = [pa, cent[ga], cent[gb], pb]
            # straighten by (1 - beta) toward the chord (Holten's bundling strength)
            ctrl = [(beta * x + (1 - beta) * (pa[0] + (pb[0] - pa[0]) * i / 3),
                     beta * y + (1 - beta) * (pa[1] + (pb[1] - pa[1]) * i / 3)) for i, (x, y) in enumerate(ctrl)]
            g.set_bends(e, _bspline(ctrl, 14)[1:-1])
            n_bundled += 1
        print(f"bundled {n_bundled} edges between {len(cent)} groups")

    @cmd
    def unbundleEdges():
        """Draw edges straight again after bundleEdges."""
        g.clear_bends()


def _c(n, axis):
    v = n.x if axis == "x" else n.y
    s = n.width if axis == "x" else n.height
    try:
        return float(v) + float(s) / 2
    except (TypeError, ValueError):
        return 0.0


def _bspline(ctrl, samples):
    """Points on a clamped cubic B-spline through the ends of `ctrl`."""
    p = [ctrl[0], ctrl[0]] + list(ctrl) + [ctrl[-1], ctrl[-1]]
    out = []
    segs = len(p) - 3
    for k in range(samples + 1):
        t = k / samples * segs
        i = min(int(t), segs - 1)
        u = t - i
        b0 = (1 - u) ** 3 / 6
        b1 = (3 * u ** 3 - 6 * u ** 2 + 4) / 6
        b2 = (-3 * u ** 3 + 3 * u ** 2 + 3 * u + 1) / 6
        b3 = u ** 3 / 6
        out.append((b0 * p[i][0] + b1 * p[i + 1][0] + b2 * p[i + 2][0] + b3 * p[i + 3][0],
                    b0 * p[i][1] + b1 * p[i + 1][1] + b2 * p[i + 2][1] + b3 * p[i + 3][1]))
    out[0], out[-1] = ctrl[0], ctrl[-1]
    return out


__all__ = ["install", "math"]
