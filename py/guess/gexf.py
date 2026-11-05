"""GEXF (Gephi's native format) and CSV/spreadsheet tables.

GEXF: static graphs, attributes (typed), viz:color / position / size /
shape and edge thickness, weight, label and per-edge type. Gephi's y axis
points up, ours points down, so y is flipped both ways. Dynamic content
(spells, time-varying attributes) is ignored.

CSV, as Gephi's spreadsheet importer reads it:
  - an edge table with Source and Target columns (plus Type =
    Directed/Undirected, Weight, Label, Id and any other columns, which
    become edge fields);
  - a node table with an Id column (plus Label and other columns);
  - an adjacency matrix (empty top-left cell, node names across and down);
  - an adjacency list (each row: a node followed by its neighbours).
The delimiter (comma, semicolon, tab or bar) is detected.
"""
import csv
import io
import math
import random
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from . import colors
from .model import BOOL, DOUBLE, INT, STRING, GuessError, coerce

# --------------------------------------------------------------------------
# GEXF
# --------------------------------------------------------------------------

_GEXF_TYPES = {"integer": INT, "long": INT, "short": INT, "byte": INT, "int": INT,
               "float": DOUBLE, "double": DOUBLE, "bigdecimal": DOUBLE,
               "boolean": BOOL, "string": STRING, "char": STRING, "anyuri": STRING}
_GEXF_OUT = {INT: "integer", DOUBLE: "double", BOOL: "boolean", STRING: "string"}
_SHAPES_IN = {"disc": 2, "square": 1, "diamond": 1, "triangle": 1}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(el, name):
    return next((c for c in el if _local(c.tag) == name), None)


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _field_name(raw, schema):
    name = re.sub(r"\W", "_", str(raw).strip()) or "attr"
    if name[0].isdigit():
        name = "_" + name
    f = schema.get(name)
    if f is not None and (f.builtin or f.compute is not None):
        name += "_"
    return name


def _viz_color(el):
    c = _child(el, "color")
    if c is None:
        return None
    if c.get("hex"):
        h = c.get("hex").lstrip("#")
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            return None
    else:
        try:
            r, g, b = (int(float(c.get(k, 0))) for k in "rgb")
        except ValueError:
            return None
    a = c.get("a")
    if a is not None:
        try:
            return f"{r},{g},{b},{int(round(float(a) * 255))}"
        except ValueError:
            pass
    return f"{r},{g},{b}"


def read_gexf(graph, text):
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    gel = _child(root, "graph")
    if gel is None:
        raise GuessError("no <graph> element in GEXF")
    default_directed = gel.get("defaultedgetype", "undirected").lower() == "directed"
    attrs = {"node": {}, "edge": {}}
    for block in _children(gel, "attributes"):
        cls = block.get("class", "node").lower()
        if cls not in attrs:
            continue
        schema = graph.node_schema if cls == "node" else graph.edge_schema
        for a in _children(block, "attribute"):
            ftype = _GEXF_TYPES.get((a.get("type") or "string").lower(), STRING)
            name = _field_name(a.get("title") or a.get("id"), schema)
            d = _child(a, "default")
            default = None
            if d is not None and d.text is not None:
                try:
                    default = coerce(ftype, d.text)
                except (ValueError, TypeError):
                    default = None
            if name not in schema:
                (graph.addNodeField if cls == "node" else graph.addEdgeField)(name, ftype, default)
            attrs[cls][a.get("id")] = schema[name]

    def set_attvalues(elem, el, cls):
        av = _child(el, "attvalues")
        if av is None:
            return
        for v in _children(av, "attvalue"):
            f = attrs[cls].get(v.get("for") or v.get("id"))
            if f is None or v.get("value") is None:
                continue
            try:
                f.set(elem, v.get("value"))
            except (GuessError, ValueError, TypeError):
                pass

    nodes_el = _child(gel, "nodes")
    edges_el = _child(gel, "edges")
    ids = {}
    has_pos = False
    for el in (_children(nodes_el, "node") if nodes_el is not None else []):
        nid = el.get("id")
        n = graph.addNode(nid)
        ids[nid] = n
        n.label = el.get("label") if el.get("label") is not None else nid
        set_attvalues(n, el, "node")
        col = _viz_color(el)
        if col:
            n.color = col
        size = _child(el, "size")
        if size is not None:
            try:
                n.size = max(float(size.get("value", 10)), 0.1)
            except ValueError:
                pass
        pos = _child(el, "position")
        if pos is not None:   # GEXF positions are node centres; ours are top-left corners
            try:
                n.x = float(pos.get("x", 0)) - n.width / 2
                n.y = -float(pos.get("y", 0)) - n.height / 2
                has_pos = True
            except ValueError:
                pass
        shape = _child(el, "shape")
        if shape is not None and shape.get("value") in _SHAPES_IN:
            n.style = _SHAPES_IN[shape.get("value")]
    ne = 0
    for el in (_children(edges_el, "edge") if edges_el is not None else []):
        s, t = el.get("source"), el.get("target")
        if s is None or t is None:
            continue
        for k in (s, t):
            if k not in ids:
                ids[k] = graph.addNode(k)
        etype = (el.get("type") or "").lower()
        directed = default_directed if etype not in ("directed", "undirected", "mutual") else etype == "directed"
        e = graph.addEdge(ids[s], ids[t], directed)
        if el.get("weight") is not None:
            try:
                e.weight = float(el.get("weight"))
            except ValueError:
                pass
        if el.get("label"):
            e.label = el.get("label")
        set_attvalues(e, el, "edge")
        col = _viz_color(el)
        if col:
            e.color = col
        th = _child(el, "thickness")
        if th is not None:
            try:
                e.width = max(float(th.get("value", 1)), 0.1)
            except ValueError:
                pass
        ne += 1
    if not has_pos:
        for n in graph._nodes_list():
            n.x, n.y = random.random() * 500, random.random() * 500
    return len(ids), ne


def write_gexf(graph):
    nf = [f for f in graph.node_schema.values() if not f.builtin and f.compute is None]
    ef = [f for f in graph.edge_schema.values() if not f.builtin and f.compute is None]
    directed = [e._directed for e in graph._edges_list()]
    default = "directed" if directed and all(directed) else "undirected"
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gexf xmlns="http://gexf.net/1.3" xmlns:viz="http://gexf.net/1.3/viz" version="1.3">',
           '  <meta><creator>GUESS</creator></meta>',
           f'  <graph mode="static" defaultedgetype="{default}">']
    for cls, fields in (("node", nf), ("edge", ef)):
        if fields:
            out.append(f'    <attributes class="{cls}">')
            for k, f in enumerate(fields):
                d = "" if f.default is None else f"<default>{escape(_val(f.default))}</default>"
                out.append(f'      <attribute id="{k}" title={quoteattr(f.name)} type="{_GEXF_OUT[f.type]}">{d}</attribute>')
            out.append("    </attributes>")

    def attvalues(elem, fields):
        vals = [(k, f.get(elem)) for k, f in enumerate(fields)]
        vals = [(k, v) for k, v in vals if v is not None]
        if not vals:
            return []
        return (["        <attvalues>"]
                + [f'          <attvalue for="{k}" value={quoteattr(_val(v))}/>' for k, v in vals]
                + ["        </attvalues>"])

    out.append("    <nodes>")
    for n in graph._nodes_list():
        label = n.label if n.label is not None else n._name
        out.append(f"      <node id={quoteattr(n._name)} label={quoteattr(str(label))}>")
        out += attvalues(n, nf)
        r, g, b, a = colors.parse(n.color, (100, 149, 237, 255))
        out.append(f'        <viz:color r="{r}" g="{g}" b="{b}"' + (f' a="{a / 255:.3f}"' if a < 255 else "") + "/>")
        w, h = _num(n.width, 10), _num(n.height, 10)
        out.append(f'        <viz:position x="{_num(n.x, 0) + w / 2:g}" y="{-(_num(n.y, 0) + h / 2):g}" z="0"/>')
        out.append(f'        <viz:size value="{max(w, h):g}"/>')
        out.append(f'        <viz:shape value="{"disc" if n.style in (2, 5, 9) else "square"}"/>')
        out.append("      </node>")
    out.append("    </nodes>")
    out.append("    <edges>")
    for e in graph._edges_list():
        t = "" if (e._directed == (default == "directed")) else f' type="{"directed" if e._directed else "undirected"}"'
        lab = f" label={quoteattr(str(e.label))}" if e.label else ""
        out.append(f"      <edge id=\"{e._id}\" source={quoteattr(e._n1._name)} target={quoteattr(e._n2._name)}"
                   f'{t} weight="{_num(e.weight, 1):g}"{lab}>')
        out += attvalues(e, ef)
        r, g, b, a = colors.parse(e.color, (252, 216, 112, 255))
        out.append(f'        <viz:color r="{r}" g="{g}" b="{b}"' + (f' a="{a / 255:.3f}"' if a < 255 else "") + "/>")
        out.append(f'        <viz:thickness value="{_num(e.width, 1):g}"/>')
        out.append("      </edge>")
    out += ["    </edges>", "  </graph>", "</gexf>"]
    return "\n".join(out) + "\n"


def _num(v, d):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(d)
    return f if math.isfinite(f) else float(d)


def _val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# --------------------------------------------------------------------------
# CSV tables
# --------------------------------------------------------------------------

def _rows(text):
    text = text.lstrip("﻿")
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "," if "," in sample else ("\t" if "\t" in sample else ";")
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [r for r in rows if any(c for c in r)]


def _infer(values):
    vals = [v for v in values if v != ""]
    if not vals:
        return STRING
    if all(v.lower() in ("true", "false") for v in vals):
        return BOOL
    if all(re.fullmatch(r"[-+]?\d+", v) for v in vals):
        return INT
    try:
        for v in vals:
            float(v)
        return DOUBLE
    except ValueError:
        return STRING


def table_kind(text):
    rows = _rows(text)
    if not rows:
        return "empty", rows
    head = [h.lower() for h in rows[0]]
    if "source" in head and "target" in head:
        return "edges", rows
    if "id" in head:
        return "nodes", rows
    if rows[0] and rows[0][0] == "" and len(rows[0]) == len(rows):
        return "matrix", rows
    return "list", rows


_EDGE_COLS = {"source", "target", "type", "weight", "label", "id"}
_NODE_COLS = {"id", "label"}


def _add_columns(graph, schema_add, schema, head, rows, skip):
    fields = {}
    for k, h in enumerate(head):
        if h.lower() in skip or not h:
            continue
        f = schema.get(h)
        if f is not None and f.builtin:
            if f.compute is None and not f.readonly:   # x, y, color, size, ...: set directly
                fields[k] = h
            continue                                  # computed (indegree, ...): skip
        name = _field_name(h, schema)
        if name in fields.values():
            continue
        ftype = _infer([r[k] if k < len(r) else "" for r in rows])
        if name not in schema:
            schema_add(name, ftype, None)
        fields[k] = name
    return fields


def _place(graph, nodes):
    for n in nodes:
        n.x, n.y = random.random() * 500, random.random() * 500


def read_csv(graph, text, directed=False):
    """Load one table into the graph (see the module docstring). Returns
    (kind, nodes added, edges added)."""
    kind, rows = table_kind(text)
    added = []

    def get(name):
        n = graph._nodes.get(name)
        if n is None:
            n = graph.addNode(name)
            n.label = name
            added.append(n)
        return n

    ne = 0
    if kind == "edges":
        head = rows[0]
        low = [h.lower() for h in head]
        col = {k: low.index(k) for k in _EDGE_COLS if k in low}
        fields = _add_columns(graph, graph.addEdgeField, graph.edge_schema, head, rows[1:], _EDGE_COLS)
        for r in rows[1:]:
            cell = lambda k: r[col[k]] if k in col and col[k] < len(r) else ""  # noqa: E731
            s, t = cell("source"), cell("target")
            if not s or not t:
                continue
            ty = cell("type").lower()
            d = directed if ty not in ("directed", "undirected") else ty == "directed"
            e = graph.addEdge(get(s), get(t), d)
            if cell("weight"):
                try:
                    e.weight = float(cell("weight"))
                except ValueError:
                    pass
            if cell("label"):
                e.label = cell("label")
            for k, name in fields.items():
                if k < len(r) and r[k] != "":
                    _set(e, name, r[k])
            ne += 1
    elif kind == "nodes":
        head = rows[0]
        low = [h.lower() for h in head]
        ic = low.index("id")
        lc = low.index("label") if "label" in low else None
        fields = _add_columns(graph, graph.addNodeField, graph.node_schema, head, rows[1:], _NODE_COLS)
        for r in rows[1:]:
            if ic >= len(r) or not r[ic]:
                continue
            n = get(r[ic])
            if lc is not None and lc < len(r) and r[lc]:
                n.label = r[lc]
            for k, name in fields.items():
                if k < len(r) and r[k] != "":
                    _set(n, name, r[k])
    elif kind == "matrix":
        names = rows[0][1:]
        for name in names:
            get(name)
        cells = {}
        for r in rows[1:]:
            for name, v in zip(names, r[1:]):
                try:
                    cells[(r[0], name)] = float(v) if v else 0.0
                except ValueError:
                    pass
        # a symmetric matrix read as undirected gives one edge per pair
        sym = not directed and all(cells.get((b, a), 0.0) == w for (a, b), w in cells.items())
        order = {name: i for i, name in enumerate(names)}
        for (a, b), w in cells.items():
            if w and not (sym and order.get(b, -1) < order.get(a, -1)):
                graph.addEdge(get(a), get(b), directed, weight=w)
                ne += 1
    elif kind == "list":
        for r in rows:
            a = get(r[0])
            for name in r[1:]:
                if name:
                    graph.addEdge(a, get(name), directed)
                    ne += 1
    _place(graph, added)
    return kind, len(added), ne


def _set(elem, name, raw):
    try:
        setattr(elem, name, raw)
    except (GuessError, ValueError, TypeError):
        pass


def write_csv(graph, which="edges"):
    """Gephi-style tables: which="edges" (Source, Target, Type, Weight, ...) or "nodes" (Id, Label, ...)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if which == "nodes":
        fields = [f for f in graph.node_schema.values() if f.name not in ("name", "label")]
        w.writerow(["Id", "Label"] + [f.name for f in fields])
        for n in graph._nodes_list():
            w.writerow([n._name, n.label if n.label is not None else ""] + [_csvv(f.get(n)) for f in fields])
    else:
        fields = [f for f in graph.edge_schema.values()
                  if f.name not in ("node1", "node2", "directed", "weight", "label")]
        w.writerow(["Source", "Target", "Type", "Weight", "Label"] + [f.name for f in fields])
        for e in graph._edges_list():
            w.writerow([e._n1._name, e._n2._name, "Directed" if e._directed else "Undirected",
                        _csvv(e.weight), e.label or ""] + [_csvv(f.get(e)) for f in fields])
    return buf.getvalue()


def _csvv(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
