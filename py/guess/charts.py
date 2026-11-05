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

    def emit(kind, title, xlabel, ylabel, items):
        count[0] += 1
        cid = f"chart{count[0]}"
        session.emit({"type": "chart", "id": cid, "kind": kind, "title": title,
                      "xlabel": xlabel, "ylabel": ylabel, "items": items})
        return Chart(session, cid, title)

    def need_field(f):
        if not isinstance(f, Field):
            raise GuessError(f"expected a field, got {f!r}")
        return f

    def what(f):
        return "nodes" if f.kind == NODE else "edges"

    def plotHistogram(field, bins=10):
        """Histogram of a numeric field's values in `bins` equal-width bins."""
        f = need_field(field)
        elems = [e for e in f.elements() if isinstance(f.get(e), (int, float)) and not isinstance(f.get(e), bool)]
        if not elems:
            raise GuessError(f"field '{f.name}' has no numeric values")
        vals = [float(f.get(e)) for e in elems]
        lo, hi = min(vals), max(vals)
        bins = max(1, int(bins))
        width = (hi - lo) / bins or 1.0
        buckets = [[] for _ in range(bins)]
        for e, v in zip(elems, vals):
            buckets[min(bins - 1, int((v - lo) / width))].append(e)
        items = [{"label": f"{_label(lo + i * width)}–{_label(lo + (i + 1) * width)}",
                  "value": len(b), "color": _color(b), "ids": _ids(b)} for i, b in enumerate(buckets)]
        return emit("bar", f"Histogram of {f.name}", f.name, f"number of {what(f)}", items)

    def _sizes(f):
        groups = sorted(group_by(f.elements(), f), key=len, reverse=True)
        return [{"label": _label(getattr(grp[0], f.name)), "value": len(grp),
                 "color": _color(grp), "ids": _ids(grp)} for grp in groups]

    def plotSizes(field):
        """Bar chart of how many elements share each value of field (largest first)."""
        f = need_field(field)
        return emit("bar", f"{f.name} group sizes", f.name, f"number of {what(f)}", _sizes(f))

    def plotSizesPie(field):
        """Pie chart of how many elements share each value of field."""
        f = need_field(field)
        return emit("pie", f"{f.name} group sizes", f.name, f"number of {what(f)}", _sizes(f))

    def plotDistrib(field, sortField=None):
        """Each element's value of field, in rank order (or ordered by sortField)."""
        f = need_field(field)
        order = sort_by(f.elements(), need_field(sortField) if sortField is not None else f, descending=True)
        items = [{"label": repr(e), "value": f.get(e) if isinstance(f.get(e), (int, float)) else 0,
                  "color": _color([e]), "ids": _ids([e])} for e in order]
        return emit("distrib", f"Distribution of {f.name}", f"rank-ordered {what(f)}", f.name, items)

    for fn in (plotHistogram, plotSizes, plotSizesPie, plotDistrib):
        session.register_command(fn.__name__, fn)
