"""Altair (Vega-Lite) charts in the dock, linked to the graph.

    import altair as alt          # or just use alt.…: it's imported on first use
    alt.Chart(nodeData("degree", "dept")).mark_point().encode(x="degree", y="dept")

A cell whose value is an Altair chart shows it in the dock; showChart(chart)
does the same from a script. nodeData()/edgeData() give the rows for a chart:
one per node (edge), carrying its id in `_node` (`_edge`), so marks for single
elements link to them. Marks that summarise many (a bar of count() by dept,
a bin) link through a query built from the fields they're grouped by.
"""
from .model import EDGE, NODE, Edge, Field, GuessError, Node, elements_of

# Vega-Lite types for GUESS field types
_VL_TYPE = {"INTEGER": "quantitative", "DOUBLE": "quantitative", "BOOLEAN": "nominal", "VARCHAR": "nominal"}
# display plumbing left out of nodeData() unless asked for
_PLUMBING = {"x", "y", "visible", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "image",
             "labelvisible", "labelsize", "labelpos", "node1", "node2", "source", "destination", "label"}


class GraphData(dict):
    """Rows for an Altair chart ({"values": [...]}, which Altair takes as inline
    data). .rows is the list; .types the Vega-Lite type of each field, so
    shorthand like x="degree" knows degree is a number."""

    def __init__(self, rows, types, kind, others=(), call="nodeData", remake=None):
        super().__init__(values=rows)
        self._remake = remake
        self.rows = rows
        self.types = types
        self.kind = kind
        self.others = set(others)     # graph fields not in these rows (for a clear error)
        self.call = call

    def refresh(self):
        """Recompute the rows from the graph as it is now (live charts)."""
        if self._remake is not None:
            new = self._remake()
            self["values"] = self.rows = new.rows
            self.types = new.types

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


def _graph_datas(chart):
    """The GraphData rows anywhere in a chart (layers, concatenations, facets)."""
    out, todo, seen = [], [chart], set()
    while todo:
        c = todo.pop()
        if id(c) in seen:
            continue
        seen.add(id(c))
        d = getattr(c, "data", None)
        if isinstance(d, GraphData):
            out.append(d)
        for attr in ("layer", "hconcat", "vconcat", "concat"):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                todo.extend(v)
        sp = getattr(c, "spec", None)
        if sp is not None and hasattr(sp, "to_dict"):
            todo.append(sp)
    return out


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


def _auto_title(spec):
    """A panel title from the encoding: "pagerank vs degree", "count by dept"."""
    enc = spec.get("encoding") or {}
    def name(ch):
        d = enc.get(ch)
        if not isinstance(d, dict):
            return None
        agg, f = d.get("aggregate"), d.get("field")
        if agg == "count":
            return "count"
        if agg and f:
            return f"{agg} of {f}"
        return f
    x, y = name("x"), name("y")
    if x and y:
        return f"{y} by {x}" if enc["y"].get("aggregate") or enc["x"].get("aggregate") == "count" else f"{y} vs {x}"
    return x or y or "Chart"


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
        nodes = None
        if args and not isinstance(args[0], (str, Field)):
            nodes, args = args[0], args[1:]
        fixed = None if nodes is None else [x for x in elements_of(nodes) if isinstance(x, Node)]

        def make():
            gr = session.graph
            elems = gr._nodes_list() if fixed is None else [n for n in fixed if gr._nodes.get(n._name) is n]
            return _rows(gr, NODE, elems, list(args))
        d = make()
        d._remake = make
        return d

    def edgeData(*args):
        """edgeData(field, ...) or edgeData(edges, field, ...): one row per edge
        (`name` is "a-b"), with `_edge`, the edge's id, for linking."""
        edges = None
        if args and not isinstance(args[0], (str, Field)):
            edges, args = args[0], args[1:]
        fixed = None if edges is None else [x for x in elements_of(edges) if isinstance(x, Edge)]

        def make():
            gr = session.graph
            elems = gr._edges_list() if fixed is None else [e for e in fixed if e._id in gr._edges]
            return _rows(gr, EDGE, elems, list(args))
        d = make()
        d._remake = make
        return d

    def showChart(chart, title=None):
        """showChart(chart, title=None) shows an Altair chart in the dock (a cell
        whose value is a chart does this by itself). Hovering a mark highlights
        its nodes, clicking selects them, right-click opens the element menu;
        interval selections (brushes) select what they cover."""
        if not is_altair(chart):
            raise GuessError("showChart needs an Altair chart (alt.Chart(...))")
        import altair as alt
        _patch_altair(alt)
        if session._refreshing is not None:
            for d in _graph_datas(chart):
                d.refresh()
        spec = chart.to_dict()
        g = session.graph
        types = {}
        for kind, schema in ((NODE, g.node_schema), (EDGE, g.edge_schema)):
            for name, f in schema.items():
                types.setdefault(name, _VL_TYPE.get(f.type, "nominal"))
        _fill_types(spec, types)
        if title is None:
            t = spec.get("title")
            title = t if isinstance(t, str) else (t.get("text") if isinstance(t, dict) else None) or _auto_title(spec)
            if isinstance(title, list):
                title = " ".join(map(str, title))
        emit(spec, title)
        return None

    def emit(spec, title):
        """Send a Vega or Vega-Lite spec to the dock (a live chart keeps its panel)."""
        g = session.graph
        cell = session.running_cell
        count[0] += 1
        if session._refreshing is not None:
            cid = session._refreshing               # a live chart recomputing: same panel
        else:
            # the same cell re-run (Run again, a watched cell) updates its chart in place
            cid = f"vega:{cell}:{session.chart_seq}" if cell is not None else f"vega:x{count[0]}"
            session.chart_seq += 1
        session.chart_out({"type": "vega", "id": cid, "title": str(title), "spec": spec, "cell": cell,
                      "fields": {"n": list(g.node_schema), "e": list(g.edge_schema)}})

    def wordCloud(field, top=80, stopwords=None, minLength=3):
        """wordCloud(field) shows the most frequent words in a text field as a
        word cloud in the dock (as Gephi's Word Cloud plugin), sized by how
        many times each occurs. Hovering a word lights up the nodes (or edges)
        whose text contains it; clicking selects them. Common English words
        are left out; stopwords=[...] adds more, top= sets how many words,
        minLength= the shortest word kept."""
        import re
        from .builders import STOPWORDS
        from .model import as_field
        f = as_field(session.graph, field, "wordCloud")
        stop = STOPWORDS | {str(w).lower() for w in (stopwords or [])}
        counts, where = {}, {}
        for x in f.elements():
            v = f.get(x)
            if v is None:
                continue
            for w in re.findall(r"[^\W\d_][\w'-]*", str(v).lower()):
                w = w.strip("'-")
                if len(w) < int(minLength) or w in stop:
                    continue
                counts[w] = counts.get(w, 0) + 1
                where.setdefault(w, []).append(x._id)
        if not counts:
            raise GuessError(f"field '{f.name}' has no words to show")
        words = sorted(counts, key=lambda w: (-counts[w], w))[:max(1, int(top))]
        key = "_nodes" if f.kind == NODE else "_edges"
        rows = [{"text": w, "count": counts[w], "angle": (0, 0, -30, 0, 30)[i % 5],
                 key: sorted(set(where[w]))[:5000]} for i, w in enumerate(words)]
        from . import colors
        palette = ["#" + "".join(f"{int(c):02x}" for c in str(rgb).split(",")[:3])
                   for rgb in colors.distinctColors(min(len(words), 12))]
        spec = {
            "$schema": "https://vega.github.io/schema/vega/v6.json",
            "width": 520, "height": 320, "padding": 4, "autosize": "pad",
            "data": [{"name": "table", "values": rows}],
            "scales": [{"name": "color", "type": "ordinal", "domain": {"data": "table", "field": "text"},
                        "range": palette}],
            "marks": [{
                "type": "text", "from": {"data": "table"},
                "encode": {
                    "enter": {"text": {"field": "text"}, "align": {"value": "center"},
                              "baseline": {"value": "alphabetic"}, "fill": {"scale": "color", "field": "text"},
                              "cursor": {"value": "pointer"},
                              "tooltip": {"signal": "datum.text + ': ' + datum.count"}},
                    "update": {"fillOpacity": {"value": 1}},
                    "hover": {"fillOpacity": {"value": 0.6}},
                },
                "transform": [{"type": "wordcloud", "size": [520, 320], "text": {"field": "text"},
                               "rotate": {"field": "datum.angle"}, "font": "Helvetica Neue, Arial, sans-serif",
                               "fontSize": {"field": "datum.count"}, "fontWeight": "bold",
                               "fontSizeRange": [11, 54], "padding": 2}],
            }],
        }
        emit(spec, f"words in {f.name}")
        return None

    for fn in (nodeData, edgeData, showChart, wordCloud):
        session.register_command(fn.__name__, fn)


def ensure_alt(session):
    """`alt` used without importing it: import altair as alt (and fix shorthand)."""
    import altair as alt
    _patch_altair(alt)
    session.ns.setdefault("alt", alt)
    return alt


__all__ = ["install", "is_altair", "GraphData", "ensure_alt"]
