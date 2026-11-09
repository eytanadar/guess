"""Readers for Pajek (.net), GraphML, GML and UCINET DL, and a GraphML writer.

Pajek handling follows com/hp/hpl/guess/pajek/GuessPajekReader.java
(node names are "pajek<id>", label from the quoted name, coordinates scaled
by 1000, ``ic``/``lc``/``x_fact``/``y_fact``/shape honoured).
"""
import html
import random
import re
import shlex
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from .model import BOOL, DOUBLE, INT, STRING, GuessError, coerce

# --------------------------------------------------------------------------
# Pajek
# --------------------------------------------------------------------------

_PAJEK_SHAPES = {"box", "ellipse", "triangle", "diamond", "circle"}


def _pajek_tokens(line):
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return line.split()


def read_pajek(graph, text):
    mode = None
    part_name = None
    part_index = 0
    order = []
    edges = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%"):
            continue
        low = line.lower()
        if low.startswith("*vertices"):
            if mode == "partition":
                continue
            mode = "vert"
            continue
        if low.startswith("*arcslist") or low.startswith("*edgeslist"):
            mode = "arcslist" if low.startswith("*arcslist") else "edgeslist"
            continue
        if low.startswith("*arcs"):
            mode = "arcs"
            continue
        if low.startswith("*edges"):
            mode = "edges"
            continue
        if low.startswith("*partition"):
            mode = "partition"
            part_name = _ident(line.split()[-1]) if len(line.split()) > 1 else "partition"
            graph.addNodeField(part_name, BOOL, False)
            part_index = 0
            continue
        if low.startswith("*matrix"):
            mode = "matrix"
            part_index = 0
            continue
        if line.startswith("*"):
            mode = None
            continue
        if mode == "vert":
            order.append(_pajek_vertex(graph, line))
        elif mode in ("edges", "arcs"):
            _pajek_edge(graph, line, mode == "arcs")
            edges += 1
        elif mode in ("edgeslist", "arcslist"):
            toks = line.split()
            for t in toks[1:]:
                graph.addEdge(_pajek_node(graph, toks[0]), _pajek_node(graph, t), mode == "arcslist")
                edges += 1
        elif mode == "partition":
            if part_index < len(order) and line.split()[0] == "1":
                setattr(order[part_index], part_name, True)
            part_index += 1
        elif mode == "matrix":
            vals = line.split()
            src = order[part_index] if part_index < len(order) else None
            for j, v in enumerate(vals):
                if src is not None and j < len(order) and float(v) != 0:
                    graph.addEdge(src, order[j], True, weight=float(v))
                    edges += 1
            part_index += 1
    return len(order), edges


def _pajek_node(graph, ident):
    name = "pajek" + ident
    n = graph.getNodeByName(name)
    if n is None:
        n = graph.addNode(name)
        n.x = random.random() * 1000
        n.y = random.random() * 1000
        n.label = ident
    return n


def _pajek_vertex(graph, line):
    toks = _pajek_tokens(line)
    ident = toks[0]
    label = toks[1] if len(toks) > 1 else ident
    rest = toks[2:]
    p = 0
    x = random.random() * 1000
    y = random.random() * 1000
    if len(rest) >= 2:
        try:
            x = 1000 * float(rest[0])
            y = 1000 * float(rest[1])
            p = 2
        except ValueError:
            pass
    if len(rest) > p:
        try:
            float(rest[p])  # z coordinate, ignored
            p += 1
        except ValueError:
            pass
    shape = "ellipse"
    if len(rest) > p and rest[p].lower() in _PAJEK_SHAPES:
        shape = rest[p].lower()
        p += 1
    x_fact = y_fact = 1.0
    rounded = False
    color = "cornflowerblue"
    labelcolor = None
    while p < len(rest) - 1:
        key, value = rest[p].lower(), rest[p + 1]
        if key == "x_fact":
            x_fact = _float(value, 1.0)
        elif key == "y_fact":
            y_fact = _float(value, 1.0)
        elif key == "s_size":
            x_fact = y_fact = _float(value, 1.0)
        elif key == "sh":
            shape = value.lower()
        elif key == "r":
            rounded = value != "0"
        elif key == "ic":
            color = value
        elif key == "lc":
            labelcolor = value
        p += 2
    style = 2
    if shape == "box":
        style = 3 if rounded else 1
    n = graph.addNode("pajek" + ident)
    n.style = style
    n.x, n.y = x, y
    n.width, n.height = 10 * x_fact, 10 * y_fact
    n.color = color if _valid_color(color) else "cornflowerblue"
    n.strokecolor = "cadetblue"
    n.label = label
    if labelcolor and _valid_color(labelcolor):
        n.labelcolor = labelcolor
    return n


def _pajek_edge(graph, line, directed):
    toks = _pajek_tokens(line)
    if len(toks) < 2:
        return
    s = _pajek_node(graph, toks[0])
    t = _pajek_node(graph, toks[1])
    e = graph.addEdge(s, t, directed)
    p = 2
    if len(toks) > p:
        try:
            e.weight = float(toks[p])
            p += 1
        except ValueError:
            pass
    while p < len(toks) - 1:
        key, value = toks[p].lower(), toks[p + 1]
        if key == "c" and _valid_color(value):
            e.color = value
        elif key == "w" or key == "width":
            e.width = _float(value, 2.0)
        elif key in ("l", "label"):
            e.label = value
        elif key == "lc" and _valid_color(value):
            e.labelcolor = value
        p += 2


def _float(v, default):
    try:
        return float(v)
    except ValueError:
        return default


def _valid_color(c):
    from . import colors
    return colors.parse(c) is not None


def _ident(s):
    s = re.sub(r"\W", "_", s)
    return s if s and not s[0].isdigit() else "_" + s


# --------------------------------------------------------------------------
# GraphML
# --------------------------------------------------------------------------

_GML_TYPES = {"boolean": BOOL, "int": INT, "long": INT, "float": DOUBLE, "double": DOUBLE, "string": STRING}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def read_graphml(graph, text):
    root = ET.fromstring(text)
    keys = {}
    for k in root.iter():
        if _local(k.tag) != "key":
            continue
        kind = k.get("for", "all")
        name = _ident(k.get("attr.name") or k.get("id"))
        ftype = _GML_TYPES.get((k.get("attr.type") or "string").lower(), STRING)
        default = None
        for d in k:
            if _local(d.tag) == "default":
                default = d.text
        keys[k.get("id")] = (name, kind, ftype, default)
        targets = ["node", "edge"] if kind == "all" else [kind]
        for t in targets:
            if t == "node" and name not in graph.node_schema:
                graph.addNodeField(name, ftype, coerce(ftype, default))
            elif t == "edge" and name not in graph.edge_schema:
                graph.addEdgeField(name, ftype, coerce(ftype, default))
    gel = next((e for e in root.iter() if _local(e.tag) == "graph"), None)
    if gel is None:
        raise GuessError("no <graph> element in GraphML")
    default_directed = gel.get("edgedefault", "undirected") == "directed"
    nodes = edges = 0
    has_xy = False
    for el in gel:
        tag = _local(el.tag)
        if tag == "node":
            n = graph.addNode(el.get("id"))
            n.label = el.get("id")
            for d in el:
                if _local(d.tag) == "data" and d.get("key") in keys:
                    name = keys[d.get("key")][0]
                    if name in ("x", "y"):
                        has_xy = True
                    _set_data(n, graph.node_schema.get(name), d.text)
            nodes += 1
    for el in gel:
        if _local(el.tag) != "edge":
            continue
        directed = el.get("directed")
        directed = default_directed if directed is None else directed == "true"
        e = graph.addEdge(el.get("source"), el.get("target"), directed)
        for d in el:
            if _local(d.tag) == "data" and d.get("key") in keys:
                _set_data(e, graph.edge_schema.get(keys[d.get("key")][0]), d.text)
        edges += 1
    if not has_xy:
        for n in graph._nodes_list():
            n.x = random.random() * 500
            n.y = random.random() * 500
    return nodes, edges


def _set_data(elem, field, text):
    if field is None or field.readonly or text is None:
        return
    try:
        field.set(elem, text.strip())
    except GuessError:
        pass


_GML_OUT = {STRING: "string", INT: "int", DOUBLE: "double", BOOL: "boolean"}


def write_graphml(graph):
    nf = [f for f in graph.node_schema.values() if f.compute is None]
    ef = [f for f in graph.edge_schema.values() if f.compute is None]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for f in nf:
        out.append(f'  <key id="n_{f.name}" for="node" attr.name="{f.name}" attr.type="{_GML_OUT[f.type]}"/>')
    for f in ef:
        out.append(f'  <key id="e_{f.name}" for="edge" attr.name="{f.name}" attr.type="{_GML_OUT[f.type]}"/>')
    out.append('  <graph edgedefault="undirected">')
    for n in graph._nodes_list():
        out.append(f"    <node id={quoteattr(n._name)}>")
        for f in nf:
            v = f.get(n)
            if v is not None:
                out.append(f'      <data key="n_{f.name}">{escape(_xml_val(v))}</data>')
        out.append("    </node>")
    for e in graph._edges_list():
        d = ' directed="true"' if e._directed else ""
        out.append(f"    <edge source={quoteattr(e._n1._name)} target={quoteattr(e._n2._name)}{d}>")
        for f in ef:
            v = f.get(e)
            if v is not None:
                out.append(f'      <data key="e_{f.name}">{escape(_xml_val(v))}</data>')
        out.append("    </edge>")
    out += ["  </graph>", "</graphml>"]
    return "\n".join(out) + "\n"


def _xml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# --------------------------------------------------------------------------
# GML (Graph Modelling Language: networkx, igraph, yEd, Cytoscape, Gephi)
#   graph [ directed 1  node [ id 1 label "a" graphics [ x 0 y 0 fill "#ff0000" ] ]
#           edge [ source 1 target 2 weight 3 ] ]
# --------------------------------------------------------------------------

_GML_TOKEN = re.compile(r'\s+|#[^\n]*|"((?:[^"\\]|\\.)*)"|(\[)|(\])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(?![\w.])|([A-Za-z_][\w.]*)|(\S)')


def _gml_parse(text):
    """GML text → nested lists of (key, value); a value is a number, a string
    or such a list. Tolerant: duplicate keys, comments, any key names."""
    stack = [[]]
    key = None
    for m in _GML_TOKEN.finditer(text):
        string, opn, close, number, word, other = m.groups()
        if string is None and not (opn or close or number or word or other):
            continue        # whitespace or a # comment
        if word is not None and key is None:
            key = word
            continue
        if other is not None:
            raise GuessError(f"GML: unexpected {other!r} near {text[max(0, m.start() - 20):m.start() + 20]!r}")
        if close:
            if len(stack) == 1:
                raise GuessError("GML: unbalanced ']'")
            done = stack.pop()
            stack[-1][-1] = (stack[-1][-1][0], done)
            continue
        if key is None:
            raise GuessError(f"GML: a value without a key near {text[max(0, m.start() - 20):m.start() + 20]!r}")
        if opn:
            stack[-1].append((key, None))
            stack.append([])
        elif string is not None:
            stack[-1].append((key, html.unescape(string.replace('\\"', '"'))))
        elif number is not None:
            stack[-1].append((key, float(number) if re.search(r"[.eE]", number) else int(number)))
        else:
            stack[-1].append((key, word))      # a bare word as a value
        key = None
    if len(stack) != 1:
        raise GuessError("GML: missing ']'")
    return stack[0]


_GML_SHAPES = {"ellipse": 2, "oval": 2, "circle": 2, "rectangle": 1, "rect": 1, "box": 1,
               "roundrectangle": 3, "triangle": 5, "diamond": 9}


def _gml_type(values):
    vals = [v for v in values if v is not None]
    if vals and all(isinstance(v, int) for v in vals):
        return INT
    if vals and all(isinstance(v, (int, float)) for v in vals):
        return DOUBLE
    return STRING


def read_gml(graph, text):
    top = _gml_parse(text)
    gl = next((v for k, v in top if k.lower() == "graph" and isinstance(v, list)), None)
    if gl is None:
        raise GuessError("not a GML file (no 'graph [ ... ]')")
    directed = any(k.lower() == "directed" and v == 1 for k, v in gl)
    nodes = [dict(_flat(v)) for k, v in gl if k.lower() == "node" and isinstance(v, list)]
    edges = [dict(_flat(v)) for k, v in gl if k.lower() == "edge" and isinstance(v, list)]
    if not nodes and not edges:
        raise GuessError("GML: no nodes or edges")
    # names: unique labels when every node has one, else the ids ("n" + a numeric id)
    labels = [n.get("label") for n in nodes]
    use_labels = all(isinstance(lbl, str) and lbl for lbl in labels) and len(set(labels)) == len(labels)
    def name_of(n):
        if use_labels:
            return n["label"]
        i = n.get("id")
        return f"n{i}" if isinstance(i, (int, float)) else str(i)
    by_id = {}
    STRUCT_N = {"id", "label", "graphics.x", "graphics.y", "graphics.w", "graphics.h", "graphics.fill",
                "graphics.type", "graphics.outline"}
    STRUCT_E = {"source", "target", "id", "graphics.fill", "graphics.width"}
    _fields(graph, graph.node_schema, graph.addNodeField, nodes, STRUCT_N)
    _fields(graph, graph.edge_schema, graph.addEdgeField, edges, STRUCT_E)
    has_xy = False
    for rec in nodes:
        n = graph.addNode(name_of(rec))
        by_id[rec.get("id")] = n
        if isinstance(rec.get("label"), str):
            n.label = rec["label"]
        if isinstance(rec.get("graphics.x"), (int, float)) and isinstance(rec.get("graphics.y"), (int, float)):
            n.x, n.y = float(rec["graphics.x"]), float(rec["graphics.y"])
            has_xy = True
        for k, attr in (("graphics.w", "width"), ("graphics.h", "height")):
            if isinstance(rec.get(k), (int, float)) and rec[k] > 0:
                setattr(n, attr, float(rec[k]))
        if isinstance(rec.get("graphics.fill"), str) and _valid_color(rec["graphics.fill"]):
            n.color = rec["graphics.fill"]
        shape = _GML_SHAPES.get(str(rec.get("graphics.type", "")).lower())
        if shape:
            n.style = shape
        _set_fields(graph.node_schema, n, rec, STRUCT_N)
    count_e = 0
    for rec in edges:
        a, b = by_id.get(rec.get("source")), by_id.get(rec.get("target"))
        if a is None or b is None:
            continue
        e = graph.addEdge(a._name, b._name, directed)
        if isinstance(rec.get("graphics.fill"), str) and _valid_color(rec["graphics.fill"]):
            e.color = rec["graphics.fill"]
        if isinstance(rec.get("graphics.width"), (int, float)) and rec["graphics.width"] > 0:
            e.width = float(rec["graphics.width"])
        _set_fields(graph.edge_schema, e, rec, STRUCT_E)
        count_e += 1
    if not has_xy:
        for n in graph._nodes_list():
            n.x = random.random() * 500
            n.y = random.random() * 500
    return len(nodes), count_e


def _flat(items, prefix=""):
    """Node/edge attributes, with nested lists one level deep as "graphics.x"."""
    for k, v in items:
        if isinstance(v, list):
            if not prefix:
                yield from _flat(v, k + ".")
        else:
            yield prefix + k, v


def _gml_field_name(key):
    return _ident(key.replace(".", "_"))


def _fields(graph, schema, add, recs, skip):
    keys = {}
    for r in recs:
        for k, v in r.items():
            if k not in skip:
                keys.setdefault(k, []).append(v)
    for k, vals in keys.items():
        name = _gml_field_name(k)
        if name not in schema:
            ftype = _gml_type(vals)
            add(name, ftype, coerce(ftype, None))


def _set_fields(schema, elem, rec, skip):
    for k, v in rec.items():
        if k in skip:
            continue
        f = schema.get(_gml_field_name(k))
        if f is None or f.readonly:
            continue
        try:
            f.set(elem, v)
        except (GuessError, TypeError, ValueError):
            pass


def write_gml(graph):
    """The graph as GML (networkx/igraph/yEd/Cytoscape read it)."""
    def val(v):
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return repr(v)
        return '"' + html.escape(str(v), quote=True) + '"'
    nf = [f for f in graph.node_schema.values() if f.compute is None and f.name not in ("name", "x", "y", "width", "height", "color", "label")]
    ef = [f for f in graph.edge_schema.values() if f.compute is None and f.name not in ("node1", "node2", "source", "destination", "directed", "color", "width")]
    from . import colors
    directed = any(e._directed for e in graph._edges_list())
    out = ["graph [", f"  directed {1 if directed else 0}"]
    ids = {}
    for i, n in enumerate(graph._nodes_list()):
        ids[n] = i
        out += ["  node [", f"    id {i}", f"    label {val(n.label or n._name)}"]
        for f in nf:
            v = f.get(n)
            if v is not None and not (isinstance(v, float) and v != v):
                out.append(f"    {_gml_field_name(f.name)} {val(v)}")
        rgb, _a = colors.to_rgba_int(n.color)
        out += ["    graphics [", f"      x {n.x!r}", f"      y {n.y!r}", f"      w {float(n.width)!r}",
                f"      h {float(n.height)!r}", f'      fill "#{rgb:06x}"', "    ]", "  ]"]
    for e in graph._edges_list():
        out += ["  edge [", f"    source {ids[e._n1]}", f"    target {ids[e._n2]}"]
        for f in ef:
            v = f.get(e)
            if v is not None and not (isinstance(v, float) and v != v):
                out.append(f"    {_gml_field_name(f.name)} {val(v)}")
        rgb, _a = colors.to_rgba_int(e.color)
        out += ["    graphics [", f'      fill "#{rgb:06x}"', f"      width {float(e.width)!r}", "    ]", "  ]"]
    out.append("]")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# UCINET DL (fullmatrix, edgelist1, nodelist1)
# --------------------------------------------------------------------------

def read_dl(graph, text):
    m = re.search(r"\bdata\s*:", text, re.I)
    if not text.lstrip().lower().startswith("dl") or not m:
        raise GuessError("not a DL file (needs 'dl' header and 'data:' section)")
    head, body = text[:m.start()], text[m.end():]
    nm = re.search(r"\bn\s*=\s*(\d+)", head, re.I)
    if not nm:
        raise GuessError("DL file must declare n=")
    n = int(nm.group(1))
    fm = re.search(r"\bformat\s*=\s*(\w+)", head, re.I)
    fmt = fm.group(1).lower() if fm else "fullmatrix"
    lm = re.search(r"\blabels\s*:(.*)", head, re.I | re.S)
    labels = lm.group(1).replace(",", " ").split() if lm else []
    if len(labels) < n:
        labels = [f"n{k + 1}" for k in range(n)]
    nodes = []
    for lab in labels[:n]:
        nd = graph.addNode(_ident(lab))
        nd.label = lab
        nd.x = random.random() * 500
        nd.y = random.random() * 500
        nodes.append(nd)
    by_label = dict(zip(labels, nodes))

    def node_for(tok):
        if tok in by_label:
            return by_label[tok]
        return nodes[int(tok) - 1]

    edges = 0
    if fmt == "fullmatrix":
        vals = body.replace(",", " ").split()
        for k, v in enumerate(vals[: n * n]):
            if float(v) != 0:
                graph.addEdge(nodes[k // n], nodes[k % n], True, weight=float(v))
                edges += 1
    elif fmt == "edgelist1":
        for line in body.splitlines():
            toks = line.replace(",", " ").split()
            if len(toks) >= 2:
                w = float(toks[2]) if len(toks) > 2 else 1.0
                graph.addEdge(node_for(toks[0]), node_for(toks[1]), True, weight=w)
                edges += 1
    elif fmt == "nodelist1":
        for line in body.splitlines():
            toks = line.replace(",", " ").split()
            for t in toks[1:]:
                graph.addEdge(node_for(toks[0]), node_for(t), True)
                edges += 1
    else:
        raise GuessError(f"unsupported DL format: {fmt}")
    return n, edges
