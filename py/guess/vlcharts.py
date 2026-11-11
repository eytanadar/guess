"""Altair (Vega-Lite) charts in the dock, linked to the graph.

    import altair as alt          # or just use alt.…: it's imported on first use
    alt.Chart(nodeData("degree", "dept")).mark_point().encode(x="degree", y="dept")

A cell whose value is an Altair chart shows it in the dock; showChart(chart)
does the same from a script. nodeData()/edgeData() give the rows for a chart:
one per node (edge), carrying its id in `_node` (`_edge`), so marks for single
elements link to them. Marks that summarise many (a bar of count() by dept,
a bin) link through a query built from the fields they're grouped by.
"""
from .model import EDGE, NODE, Edge, Field, GSet, GuessError, Node, elements_of

# Vega-Lite types for GUESS field types
_VL_TYPE = {"INTEGER": "quantitative", "DOUBLE": "quantitative", "BOOLEAN": "nominal", "VARCHAR": "nominal"}
# display plumbing left out of nodeData() unless asked for
_PLUMBING = {"x", "y", "visible", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "image",
             "labelvisible", "labelsize", "labelpos", "node1", "node2", "source", "destination", "label"}


class GraphData(dict):
    """Rows for an Altair chart ({"values": [...]}, which Altair takes as inline
    data). .rows is the list; .types the Vega-Lite type of each field, so
    shorthand like x="degree" knows degree is a number."""

    def __init__(self, rows, types, kind, others=(), call="nodeData"):
        super().__init__(values=rows)
        self.rows = rows
        self.types = types
        self.kind = kind
        self.others = set(others)     # graph fields not in these rows (for a clear error)
        self.call = call

    def __repr__(self):
        cols = list(self.rows[0]) if self.rows else []
        return f"<{len(self.rows)} {'node' if self.kind == NODE else 'edge'} rows: {', '.join(cols)}>"


def _rows(g, kind, elems, fields):
    schema = g.node_schema if kind == NODE else g.edge_schema
    if not fields:
        fields = [name for name in schema if name not in _PLUMBING]
    names = []
    for f in fields:
        if isinstance(f, Field):
            names.append(f.name)
        elif isinstance(f, str):
            if f not in schema and f not in getattr(g, "lazy_fields", {}):
                from .model import as_field
                names.append(as_field(g, f).name)      # raises with "did you mean"
            else:
                names.append(f)
        else:
            raise GuessError(f"nodeData/edgeData take field names or fields, not {type(f).__name__}")
    from .model import as_field
    resolved = [as_field(g, n) for n in names]
    key = "_node" if kind == NODE else "_edge"
    rows = []
    for e in elems:
        r = {key: e._id, "name": e._name if kind == NODE else repr(e)}
        for f in resolved:
            v = f.get(e)
            r[f.name] = v if isinstance(v, (int, float, str, bool)) or v is None else str(v)
        rows.append(r)
    types = {"name": "nominal"}
    for f in resolved:
        types[f.name] = _VL_TYPE.get(f.type, "nominal")
    lazy = [name for (k, name) in getattr(g, "lazy_fields", {}) if k == ("node" if kind == NODE else "edge")]
    others = [n for n in [*schema, *lazy] if n not in types]
    return GraphData(rows, types, kind, others, "nodeData" if kind == NODE else "edgeData")


def _patch_altair(alt):
    """Shorthand on GraphData: Altair can only infer types from data frames, so
    give it the types from the graph's schema."""
    import altair.utils as au
    import altair.utils.core as core
    if getattr(core.parse_shorthand, "_guess", False):
        return
    orig = core.parse_shorthand

    def parse_shorthand(shorthand, data=None, *args, **kwargs):
        if isinstance(data, GraphData):
            out = orig(shorthand, None, *args, **kwargs)
            if "type" not in out and "field" in out and "aggregate" not in out:
                fld = str(out["field"])
                t = data.types.get(fld)
                if t:
                    out["type"] = t
                elif fld in data.others:
                    have = [repr(k) for k in data.types if k != "name"]
                    raise GuessError(f"{fld} isn't in the chart's data: add it, as in "
                                     f"{data.call}({', '.join(have + [repr(fld)])})")
            return out
        return orig(shorthand, data, *args, **kwargs)

    parse_shorthand._guess = True
    core.parse_shorthand = parse_shorthand
    au.parse_shorthand = parse_shorthand
    try:
        from altair.vegalite.v6.schema import channels
        channels.parse_shorthand = parse_shorthand
    except ImportError:   # another Altair major version: shorthand needs explicit types
        pass
    try:
        alt.data_transformers.disable_max_rows()     # graphs often have more than 5000 rows
    except Exception:   # noqa: BLE001
        pass


def is_altair(v):
    """An Altair chart (Chart, LayerChart, HConcatChart, …)."""
    t = type(v)
    return (t.__module__ or "").startswith("altair.") and t.__name__.endswith("Chart") and hasattr(v, "to_dict")


def _fill_types(spec, types):
    """Any encoding field still without a type gets one from the graph schema."""
    if isinstance(spec, dict):
        enc = spec.get("encoding")
        if isinstance(enc, dict):
            for ch in enc.values():
                for d in (ch if isinstance(ch, list) else [ch]):
                    if isinstance(d, dict) and "field" in d and "type" not in d and "aggregate" not in d:
                        t = types.get(str(d["field"]))
                        if t:
                            d["type"] = t
        for v in spec.values():
            _fill_types(v, types)
    elif isinstance(spec, list):
        for v in spec:
            _fill_types(v, types)


def install(session):
    count = [0]

    def nodeData(*args):
        """nodeData(field, ...) or nodeData(nodes, field, ...): one row per node
        for an Altair chart, with `name`, the fields given (all data fields when
        none are) and `_node`, the node's id, which links each mark to its node.
        alt.Chart(nodeData("degree", "dept")).mark_point().encode(x="degree", y="dept")"""
        g = session.graph
        nodes = None
        if args and not isinstance(args[0], (str, Field)):
            nodes, args = args[0], args[1:]
        elems = g._nodes_list() if nodes is None else [x for x in elements_of(nodes) if isinstance(x, Node)]
        return _rows(g, NODE, elems, list(args))

    def edgeData(*args):
        """edgeData(field, ...) or edgeData(edges, field, ...): one row per edge
        (`name` is "a-b"), with `_edge`, the edge's id, for linking."""
        g = session.graph
        edges = None
        if args and not isinstance(args[0], (str, Field)):
            edges, args = args[0], args[1:]
        elems = g._edges_list() if edges is None else [x for x in elements_of(edges) if isinstance(x, Edge)]
        return _rows(g, EDGE, elems, list(args))

    def showChart(chart, title=None):
        """showChart(chart, title=None) shows an Altair chart in the dock (a cell
        whose value is a chart does this by itself). Hovering a mark highlights
        its nodes, clicking selects them, right-click opens the element menu;
        interval selections (brushes) select what they cover."""
        if not is_altair(chart):
            raise GuessError("showChart needs an Altair chart (alt.Chart(...))")
        import altair as alt
        _patch_altair(alt)
        spec = chart.to_dict()
        g = session.graph
        types = {}
        for kind, schema in ((NODE, g.node_schema), (EDGE, g.edge_schema)):
            for name, f in schema.items():
                types.setdefault(name, _VL_TYPE.get(f.type, "nominal"))
        _fill_types(spec, types)
        if title is None:
            t = spec.get("title")
            title = t if isinstance(t, str) else (t.get("text") if isinstance(t, dict) else None) or "Chart"
            if isinstance(title, list):
                title = " ".join(map(str, title))
        cell = session.running_cell
        count[0] += 1
        # the same cell re-run (Run again, a watched or live cell) updates its chart in place
        key = (cell, session.chart_seq)
        session.chart_seq += 1
        cid = f"vega:{cell}:{key[1]}" if cell is not None else f"vega:x{count[0]}"
        session.emit({"type": "vega", "id": cid, "title": str(title), "spec": spec, "cell": cell,
                      "fields": {"n": list(g.node_schema), "e": list(g.edge_schema)}})
        return None

    for fn in (nodeData, edgeData, showChart):
        session.register_command(fn.__name__, fn)


def ensure_alt(session):
    """`alt` used without importing it: import altair as alt (and fix shorthand)."""
    import altair as alt
    _patch_altair(alt)
    session.ns.setdefault("alt", alt)
    return alt


__all__ = ["install", "is_altair", "GraphData", "ensure_alt"]
