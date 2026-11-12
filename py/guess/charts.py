"""Charts linked to the graph (the original's jfreechart plots).

Each bar/slice carries the elements it represents, so hovering it highlights
them in the graph, and hovering elements elsewhere highlights their bar/slice.
Charts are snapshots: re-run the command to refresh.
"""
from . import colors
from .model import NODE, Field, GuessError, Node, group_by, sort_by


class Chart:
    def __init__(self, session, cid, title):
        self._session = session
        self._id = cid
        self.title = title

    def close(self):
        """Remove the chart."""
        self._session.emit({"type": "ui", "op": "close", "id": self._id})

    def __repr__(self):
        return f"<chart {self._id}: {self.title}>"


def _ids(elems):
    return [["n" if isinstance(e, Node) else "e", e._id] for e in elems]


def _color(elems):
    if not elems:
        return 0x9999AA
    return colors.to_rgba_int(elems[0].color, (150, 150, 170, 255))[0]


def _label(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return "(none)" if v is None else str(v)


def install(session):
    count = [0]

    def emit(kind, title, xlabel, ylabel, items, **extra):
        # the same chart (kind + title) re-plotted updates its panel in place
        # (a live chart recomputing, a watched cell, Run again)
        count[0] += 1
        cid = f"chart:{kind}:{title}"
        session.chart_out({"type": "chart", "id": cid, "kind": kind, "title": title,
                      "xlabel": xlabel, "ylabel": ylabel, "items": items,
                      **{k: v for k, v in extra.items() if v not in (None, False)}})
        return Chart(session, cid, title)

    def need_field(f):
        from .model import as_field
        return as_field(session.graph, f)

    def what(f):
        return "nodes" if f.kind == NODE else "edges"

    def _numeric(f):
        elems = [e for e in f.elements() if isinstance(f.get(e), (int, float)) and not isinstance(f.get(e), bool)]
        if not elems:
            raise GuessError(f"field '{f.name}' has no numeric values")
        return elems

    def plotHistogram(field, bins=10, log=False):
        """Histogram of a numeric field's values in `bins` equal-width bins.
        log=true uses bins of equal width on a log scale (for heavy-tailed
        values such as degree; values <= 0 are left out) and a log count axis."""
        f = need_field(field)
        elems = _numeric(f)
        if log:
            elems = [e for e in elems if f.get(e) > 0]
            if not elems:
                raise GuessError(f"field '{f.name}' has no values above 0 for a log histogram")
        vals = [float(f.get(e)) for e in elems]
        lo, hi = min(vals), max(vals)
        bins = max(1, int(bins))
        if log:
            import math
            llo, lhi = math.log10(lo), math.log10(hi)
            step = (lhi - llo) / bins or 1.0
            edges = [10 ** (llo + i * step) for i in range(bins)] + [hi]
            edges[0] = lo
            pick = lambda v: min(bins - 1, int((math.log10(v) - llo) / step))
        else:
            width = (hi - lo) / bins or 1.0
            edges = [lo + i * width for i in range(bins + 1)]
            pick = lambda v: min(bins - 1, int((v - lo) / width))
        buckets = [[] for _ in range(bins)]
        for e, v in zip(elems, vals):
            buckets[pick(v)].append(e)
        def q(i):
            a, b = edges[i], edges[i + 1]
            return f"({f.name} >= {a!r}) & ({f.name} {'<=' if i == bins - 1 else '<'} {b!r})"
        items = [{"label": f"{_label(edges[i])}–{_label(edges[i + 1])}",
                  "value": len(b), "color": _color(b), "ids": _ids(b), "q": q(i)} for i, b in enumerate(buckets)]
        return emit("bar", f"Histogram of {f.name}", f.name, f"number of {what(f)}", items, logY=bool(log))

    def plotFrequency(field, log=False, cumulative=False):
        """plotFrequency(degree) plots, for each value of a numeric field, the
        fraction of nodes (or edges) with that value: the degree distribution
        p(k). log=true draws both axes on log scales (a power law is then a
        straight line; zeros are left out). cumulative=true plots the fraction
        with that value or more (the complementary cumulative distribution,
        smoother for heavy tails). Pointing at the chart highlights the
        elements with that value."""
        f = need_field(field)
        elems = _numeric(f)
        from collections import Counter
        counts = Counter(f.get(e) for e in elems)
        n = len(elems)
        xs = sorted(counts)
        if cumulative:
            pts, left = [], n
            for x in xs:
                pts.append([x, left / n])
                left -= counts[x]
        else:
            pts = [[x, counts[x] / n] for x in xs]
        if log:
            pts = [p for p in pts if p[0] > 0 and p[1] > 0]
        op = ">=" if cumulative else "=="
        ylabel = f"fraction with {f.name} ≥ x" if cumulative else "fraction"
        return emit("line", f"{'Cumulative distribution' if cumulative else 'Distribution'} of {f.name}", f.name, ylabel,
                    [], series=[{"name": f.name, "color": 0x4E79A7, "points": pts}],
                    xq=f"{f.name} {op} {{x}}", logX=bool(log), logY=bool(log), dots=True)

    def plotLine(data, title="Chart", xlabel="x", ylabel="y", log=False, logX=None, logY=None, dots=False):
        """plotLine(points) draws a line chart of [(x, y), ...] pairs;
        plotLine({"infected": pts1, "recovered": pts2}) draws one line per
        series. log=true makes both axes logarithmic (or logX=/logY= one of
        them; points <= 0 are left out). dots=true marks each point. A chart
        with the same title replaces the last one, so calling it in a loop
        updates it."""
        palette = [0x4E79A7, 0xE15759, 0x59A14F, 0xF28E2B, 0x76B7B2, 0xB07AA1, 0xEDC948]
        if isinstance(data, dict):
            named = list(data.items())
        else:
            named = [(ylabel, data)]
        lx = bool(log) if logX is None else bool(logX)
        ly = bool(log) if logY is None else bool(logY)
        series = []
        for i, (name, pts) in enumerate(named):
            clean = []
            for p in pts:
                x, y = float(p[0]), float(p[1])
                if (lx and x <= 0) or (ly and y <= 0):
                    continue
                clean.append([x, y])
            series.append({"name": str(name), "color": palette[i % len(palette)], "points": clean})
        return emit("line", str(title), str(xlabel), str(ylabel), [], series=series, logX=lx, logY=ly,
                    dots=bool(dots))

    def _sizes(f):
        groups = sorted(group_by(f.elements(), f), key=len, reverse=True)
        return [{"label": _label(getattr(grp[0], f.name)), "value": len(grp),
                 "color": _color(grp), "ids": _ids(grp), "q": f"{f.name} == {getattr(grp[0], f.name)!r}"}
                for grp in groups]

    def plotSizes(field):
        """Bar chart of how many elements share each value of field (largest first)."""
        f = need_field(field)
        return emit("bar", f"{f.name} group sizes", f.name, f"number of {what(f)}", _sizes(f))

    def plotSizesPie(field):
        """Pie chart of how many elements share each value of field."""
        f = need_field(field)
        return emit("pie", f"{f.name} group sizes", f.name, f"number of {what(f)}", _sizes(f))

    def plotDistrib(field, sortField=None, log=False):
        """Each element's value of field, in rank order (or ordered by sortField).
        log=true draws the values on a log axis."""
        f = need_field(field)
        order = sort_by(f.elements(), need_field(sortField) if sortField is not None else f, descending=True)
        items = [{"label": repr(e), "value": f.get(e) if isinstance(f.get(e), (int, float)) else 0,
                  "color": _color([e]), "ids": _ids([e])} for e in order]
        return emit("distrib", f"Distribution of {f.name}", f"rank-ordered {what(f)}", f.name, items, logY=bool(log))


    def showMatrix(order=None, weight=None, nodes=None, title=None):
        """showMatrix() draws the adjacency matrix: a row and a column per
        node, and a dark cell where an edge joins them (darker for a bigger
        `weight` field value, when given). order=field sorts the rows and
        columns by that field (a community, a group, a degree), with lines
        between groups, so blocks and nested patterns show; nodes= limits it
        to some nodes. Rows run from the sending node to the receiving one
        for directed edges. Hovering a cell highlights its edge and two
        nodes; clicking selects them. Up to 600 nodes."""
        g = session.graph
        pool = [n for n in (nodes if nodes is not None else g.nodes) if n.visible]
        if len(pool) > 600:
            raise GuessError(f"showMatrix draws at most 600 nodes ({len(pool)} given): pass nodes=")
        f = need_field(order) if order is not None else None
        def key(n):
            v = f.get(n) if f is not None else None
            return (v is None, v if not isinstance(v, str) else v.lower(), n.name)
        try:
            pool.sort(key=key)
        except TypeError:
            pool.sort(key=lambda n: (str(key(n)[1]), n.name))
        at = {n._id: i for i, n in enumerate(pool)}
        w = need_field(weight) if weight is not None else None
        cells = []
        for e in g.edges:
            if not e.visible:
                continue
            a, b = at.get(e._n1._id), at.get(e._n2._id)
            if a is None or b is None:
                continue
            v = w.get(e) if w is not None else 1
            v = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 1.0
            cells.append([a, b, v, e._id])
            if not e.directed and a != b:
                cells.append([b, a, v, e._id])
        groups = [_label(f.get(n)) for n in pool] if f is not None else None
        name = title or (f"Adjacency matrix by {f.name}" if f is not None else "Adjacency matrix")
        return emit("matrix", name, "", "", [], labels=[n.name for n in pool], ids=[n._id for n in pool],
                    cells=cells, groups=groups, weighted=w is not None)

    def liveCharts(on=True):
        """liveCharts() makes every chart live, now and from now on: each is
        recomputed after any command that changes the graph or the display.
        liveCharts(False) turns that off. (The Live button on a chart does it
        for one chart.)"""
        session.all_live = bool(on)
        if on:
            session.live_charts.update(session.chart_recipes)
            session._refresh_live()
        else:
            for cid in list(session.live_charts):
                session.emit({"type": "liveState", "id": cid, "live": False})
            session.live_charts.clear()

    for fn in (plotHistogram, plotFrequency, plotLine, showMatrix, plotSizes, plotSizesPie, plotDistrib, liveCharts):
        session.register_command(fn.__name__, fn)
