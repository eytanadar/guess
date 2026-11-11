"""Cytoscape's network formats.

    makeFromSIF("net.sif")          simple interaction format: source type target …
    makeFromNNF("nested.nnf")       nested network format: network node / network a type b
    makeFromCYJS("net.cyjs")        Cytoscape.js JSON (Cytoscape's web export); exportCYJS writes it
    makeFromCX("net.cx2")           CX and CX2 (NDEx and Cytoscape's exchange format)
    makeFromXGMML("net.xgmml")      XGMML, Cytoscape's XML format, with its graphics
    makeFromCYS("session.cys")      the networks in a Cytoscape session file

Every reader keeps the file's attributes as typed GUESS fields, positions as
x and y, and the colours, sizes and shapes the format carries. Names that
two nodes share (two isoforms of one gene, say) get the node's id added, so
every node keeps a distinct name; the original stays in `label`.
"""
import csv
import io
import json
import os
import random
import re
import xml.etree.ElementTree as ET
import zipfile

from . import colors
from .model import BOOL, DOUBLE, INT, STRING, GuessError

# --------------------------------------------------------------------------
# shared: a format-neutral network, and building it into a GUESS graph
# --------------------------------------------------------------------------

_SHAPES = {"ellipse": 2, "circle": 2, "oval": 2, "rectangle": 1, "rect": 1, "box": 1, "square": 1,
           "roundrectangle": 3, "roundrect": 3, "roundedrectangle": 3, "triangle": 11, "diamond": 12,
           "hexagon": 13, "octagon": 14}
_SHAPES_OUT = {2: "ellipse", 1: "rectangle", 3: "round-rectangle", 11: "triangle", 12: "diamond",
               13: "hexagon", 14: "octagon"}

# visual properties (CX, CX2, Cytoscape) -> what they set
_NODE_COLOUR_VP = ("NODE_BACKGROUND_COLOR", "NODE_FILL_COLOR", "NODE_PAINT")
_NODE_SIZE_VP = ("NODE_SIZE",)
_EDGE_COLOUR_VP = ("EDGE_STROKE_UNSELECTED_PAINT", "EDGE_UNSELECTED_PAINT", "EDGE_LINE_COLOR", "EDGE_PAINT")


def _ident(s):
    s = re.sub(r"\W", "_", str(s)).strip("_") or "attr"
    return "_" + s if s[0].isdigit() else s


def _shape(v):
    return _SHAPES.get(re.sub(r"[\s_\-]", "", str(v or "")).lower())


def _colour(v):
    if v is None or v == "":
        return None
    return v if colors.parse(v) is not None else None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


class Net:
    """A network on its way into GUESS. Nodes: dicts with id, want (the name
    wanted), label, attrs, and optionally x, y, w, h, color, stroke, shape.
    Edges: dicts with s, t (node ids), directed, attrs, and optionally color,
    width, label."""

    def __init__(self):
        self.nodes = []
        self.edges = []
        self.types = {"node": {}, "edge": {}}   # declared field types (attribute name -> GUESS type)


def _infer(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return STRING
    if all(isinstance(v, bool) for v in vals):
        return BOOL
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return INT
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return DOUBLE
    return STRING


def _plain(v):
    """A value as a GUESS field can hold it: lists joined with '; ', dicts as JSON."""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(_plain(x)) for x in v)
    if isinstance(v, dict):
        return json.dumps(v)
    return v


def unique_names(pairs):
    """{id: name} for (id, wanted name) pairs: a name two ids want gets the
    id added ('BRCA1_P38398'); an empty name is the id."""
    pairs = [(i, str(w) if w not in (None, "") else str(i)) for i, w in pairs]
    count = {}
    for _i, w in pairs:
        count[w] = count.get(w, 0) + 1
    out, taken = {}, set()
    for i, w in pairs:
        name = w if count[w] == 1 else f"{w}_{i}"
        base, k = name, 2
        while name in taken:
            name, k = f"{base}_{k}", k + 1
        taken.add(name)
        out[i] = name
    return out


# built-in fields an attribute of the same name fills (others get a '_' suffix)
_INTO_BUILTIN = {"node": set(), "edge": {"weight"}}


def build(graph, net, scatter=500):
    """Fill an (empty) graph from a Net; returns (nodes, edges)."""
    builtin_n = set(graph.node_schema)
    builtin_e = set(graph.edge_schema)

    def plan(recs, kind, builtin):
        """attribute name -> (field name, type)"""
        values = {}
        for r in recs:
            for k, v in r["attrs"].items():
                values.setdefault(k, []).append(_plain(v))
        out = {}
        for k, vals in values.items():
            name = _ident(k)
            if name in builtin and not (name in _INTO_BUILTIN[kind]
                                        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                for v in vals if v is not None)):
                name += "_"
            t = net.types[kind].get(k) or _infer(vals)
            out[k] = (name, t)
        return out

    nplan = plan(net.nodes, "node", builtin_n)
    eplan = plan(net.edges, "edge", builtin_e)
    for name, t in nplan.values():
        if name not in graph.node_schema:
            graph.addNodeField(name, t, None)
    for name, t in eplan.values():
        if name not in graph.edge_schema:
            graph.addEdgeField(name, t, None)
    names = unique_names([(r["id"], r.get("want")) for r in net.nodes])
    by_id = {}
    nschema, eschema = graph.node_schema, graph.edge_schema
    for r in net.nodes:
        n = graph.addNode(names[r["id"]])
        by_id[r["id"]] = n
        label = r.get("label")
        if label in (None, "") and names[r["id"]] != str(r.get("want")) and r.get("want") not in (None, ""):
            label = r["want"]                     # a renamed node keeps its own name as its label
        if label not in (None, ""):
            n.label = str(label)
        for k, v in r["attrs"].items():
            f = nschema.get(nplan[k][0])
            if f is not None and v is not None:
                try:
                    f.set(n, _plain(v))
                except (GuessError, TypeError, ValueError):
                    pass
        for key in ("w", "h"):
            v = _num(r.get(key))
            if v is not None and v > 0:
                setattr(n, "width" if key == "w" else "height", v)
        c = _colour(r.get("color"))
        if c:
            n.color = c
        c = _colour(r.get("stroke"))
        if c:
            n.strokecolor = c
        if r.get("shape"):
            n.style = r["shape"]
        x, y = _num(r.get("x")), _num(r.get("y"))
        if x is not None and y is not None:
            n.x, n.y = x, y
        else:
            r["_unplaced"] = True
    for r in net.nodes:
        if r.get("_unplaced"):
            n = by_id[r["id"]]
            n.x, n.y = random.random() * scatter, random.random() * scatter
    count = 0
    for r in net.edges:
        a, b = by_id.get(r["s"]), by_id.get(r["t"])
        if a is None or b is None:
            continue
        e = graph.addEdge(a, b, bool(r.get("directed")))
        for k, v in r["attrs"].items():
            f = eschema.get(eplan[k][0])
            if f is not None and v is not None:
                try:
                    f.set(e, _plain(v))
                except (GuessError, TypeError, ValueError):
                    pass
        c = _colour(r.get("color"))
        if c:
            e.color = c
        w = _num(r.get("width"))
        if w is not None and w > 0:
            e.width = w
        if r.get("label") not in (None, ""):
            e.label = str(r["label"])
        count += 1
    return len(net.nodes), count


# --------------------------------------------------------------------------
# SIF
# --------------------------------------------------------------------------

def read_sif(graph, text, directed=False):
    tabs = "\t" in text
    net = Net()
    seen = {}

    def node(name):
        if name not in seen:
            seen[name] = len(net.nodes)
            net.nodes.append({"id": name, "want": name, "attrs": {}})
        return name

    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip("\r\n")
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("\t")] if tabs else line.split()
        parts = [p for p in parts if p]
        if len(parts) == 1:
            node(parts[0])
        elif len(parts) == 2:
            raise GuessError(f"SIF line {i}: expected 'source type target …' or a single node name, "
                             f"got {line.strip()!r}")
        else:
            a, kind = node(parts[0]), parts[1]
            for t in parts[2:]:
                net.edges.append({"s": a, "t": node(t), "directed": directed, "attrs": {"interaction": kind}})
    if not net.nodes:
        raise GuessError("the SIF file has no nodes")
    return build(graph, net)


# --------------------------------------------------------------------------
# NNF (nested networks)
# --------------------------------------------------------------------------

def read_nnf(graph, text):
    net = Net()
    member = {}          # node -> [networks] in order
    order = []
    networks = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")] if "\t" in line else line.split()
        parts = [p for p in parts if p]
        if len(parts) not in (2, 4):
            raise GuessError(f"NNF line {i}: expected 'network node' or 'network source type target', "
                             f"got {line!r}")
        nw = parts[0]
        if nw not in networks:
            networks.append(nw)
        ends = [parts[1]] if len(parts) == 2 else [parts[1], parts[3]]
        for v in ends:
            if v not in member:
                member[v] = []
                order.append(v)
            if nw not in member[v]:
                member[v].append(nw)
        if len(parts) == 4:
            net.edges.append({"s": parts[1], "t": parts[3], "directed": False,
                              "attrs": {"interaction": parts[2], "network": nw}})
    nets = set(networks)
    for v in order:
        attrs = {"network": "; ".join(member[v])}
        if v in nets:
            attrs["nested"] = v
        net.nodes.append({"id": v, "want": v, "attrs": attrs})
    net.types["node"]["nested"] = STRING
    if not net.nodes:
        raise GuessError("the NNF file has no nodes")
    nn, ne = build(graph, net)
    nested = sorted(nets & set(member))
    roots = [w for w in networks if w not in member]
    return nn, ne, roots, nested


# --------------------------------------------------------------------------
# Cytoscape.js JSON
# --------------------------------------------------------------------------

_CYJS_SKIP_N = {"id", "name", "label", "parent", "isParent", "SUID", "selected", "source", "target"}
_CYJS_SKIP_E = {"id", "source", "target", "SUID", "selected"}


def read_cyjs(graph, text):
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise GuessError(f"not Cytoscape.js JSON: {e.msg} at line {e.lineno}") from None
    el = doc.get("elements", doc) if isinstance(doc, dict) else doc
    if isinstance(el, dict):
        nodes, edges = list(el.get("nodes") or []), list(el.get("edges") or [])
    elif isinstance(el, list):
        nodes, edges = [], []
        for item in el:
            if not isinstance(item, dict):
                continue
            grp = item.get("group")
            d = item.get("data") or {}
            if grp == "edges" or (grp is None and "source" in d and "target" in d):
                edges.append(item)
            else:
                nodes.append(item)
    else:
        raise GuessError("not Cytoscape.js JSON (no elements)")
    if not nodes:
        raise GuessError("no nodes in that Cytoscape.js file")
    linked = set()
    for item in edges:
        d = item.get("data") or {}
        linked.add(str(d.get("source")))
        linked.add(str(d.get("target")))
    parents = {str((item.get("data") or {}).get("parent")) for item in nodes
               if (item.get("data") or {}).get("parent") is not None}
    want = {}
    for item in nodes:
        d = item.get("data") or {}
        i = str(d.get("id"))
        want[i] = d.get("name") if d.get("name") not in (None, "") else d.get("label") or d.get("shared_name") or i
    net = Net()
    for item in nodes:
        d = item.get("data") or {}
        i = str(d.get("id"))
        is_parent = bool(d.get("isParent")) or i in parents
        if is_parent and i not in linked:
            continue                              # a group box only: membership goes to `parent`
        attrs = {}
        name = d.get("name")
        for k, v in d.items():
            if k in _CYJS_SKIP_N or (k == "shared_name" and v == name):
                continue
            if k in ("color", "width", "height"):
                continue
            attrs[k] = v
        if d.get("parent") is not None:
            attrs["parent"] = str(want.get(str(d["parent"]), d["parent"]))
        if item.get("classes"):
            c = item["classes"]
            attrs["classes"] = " ".join(c) if isinstance(c, list) else str(c)
        pos = item.get("position") or {}
        rec = {"id": i, "want": want[i], "attrs": attrs, "x": pos.get("x"), "y": pos.get("y"),
               "color": d.get("color"), "w": d.get("width"), "h": d.get("height"), "shape": _shape(d.get("shape"))}
        if d.get("label") not in (None, "") and d.get("label") != want[i]:
            rec["label"] = d["label"]
        elif want[i] != name and name not in (None, ""):
            rec["label"] = name
        net.nodes.append(rec)
    for item in edges:
        d = item.get("data") or {}
        attrs = {}
        for k, v in d.items():
            if k in _CYJS_SKIP_E or k in ("color", "width", "label", "directed"):
                continue
            if k == "shared_name" and v == d.get("name"):
                continue
            if k == "shared_interaction" and v == d.get("interaction"):
                continue
            attrs[k] = v
        net.edges.append({"s": str(d.get("source")), "t": str(d.get("target")),
                          "directed": d.get("directed") is True, "attrs": attrs,
                          "color": d.get("color"), "width": d.get("width"), "label": d.get("label")})
    return build(graph, net)


def _hex(c):
    rgb, a = colors.to_rgba_int(c, (100, 149, 237, 255))
    return f"#{rgb:06x}"


def write_cyjs(graph, title="GUESS"):
    skip_n = {"x", "y", "visible", "color", "strokecolor", "labelcolor", "fixed", "style", "width", "height",
              "image", "labelvisible", "labelpos", "labelsize", "label", "name", "indegree", "outdegree",
              "totaldegree", "degree"}
    skip_e = {"node1", "node2", "directed", "source", "destination", "color", "labelcolor", "visible",
              "width", "label", "labelvisible", "labelsize"}
    nf = [f for k, f in graph.node_schema.items() if k not in skip_n and f.compute is None]
    ef = [f for k, f in graph.edge_schema.items() if k not in skip_e and f.compute is None]
    nodes, edges = [], []
    ids = {}
    for i, n in enumerate(graph._nodes_list()):
        nid = f"n{n._id}"
        ids[n._id] = nid
        d = {"id": nid, "name": n._name, "color": _hex(n.color),
             "width": float(n.width), "height": float(n.height)}
        if n.label not in (None, "", n._name):
            d["label"] = n.label
        shape = _SHAPES_OUT.get(int(n.style or 2))
        if shape and shape != "ellipse":
            d["shape"] = shape
        for f in nf:
            v = f.get(n)
            if v is not None:
                d[f.name] = v
        nodes.append({"data": d, "position": {"x": float(n.x), "y": float(n.y)}})
    for e in graph._edges_list():
        d = {"id": f"e{e._id}", "source": ids[e._n1._id], "target": ids[e._n2._id],
             "color": _hex(e.color), "width": float(e.width)}
        if e._directed:
            d["directed"] = True
        if e.label not in (None, ""):
            d["label"] = e.label
        for f in ef:
            v = f.get(e)
            if v is not None:
                d[f.name] = v
        edges.append({"data": d})
    doc = {"format_version": "1.0", "generated_by": "GUESS", "target_cytoscapejs_version": "~3.0",
           "data": {"name": title}, "elements": {"nodes": nodes, "edges": edges}}
    return json.dumps(doc, indent=1)


# --------------------------------------------------------------------------
# CX and CX2
# --------------------------------------------------------------------------

_CX_TYPES = {"integer": INT, "long": INT, "double": DOUBLE, "boolean": BOOL, "string": STRING}


def _cx_value(v, d):
    """A CX value of declared type d (CX1 sends many as strings)."""
    if d is None or v is None:
        return v
    if d.startswith("list_of_"):
        return v
    if isinstance(v, str):
        try:
            if d in ("integer", "long"):
                return int(float(v))
            if d == "double":
                return float(v)
            if d == "boolean":
                return v.strip().lower() == "true"
        except ValueError:
            return v
    return v


def _vp_apply(rec, props, kind):
    if not props:
        return
    if kind == "node":
        for k in _NODE_COLOUR_VP:
            if props.get(k):
                rec["color"] = props[k]
                break
        size = _num(props.get("NODE_SIZE"))
        w, h = _num(props.get("NODE_WIDTH")), _num(props.get("NODE_HEIGHT"))
        if size:
            rec["w"] = rec["h"] = size
        if w:
            rec["w"] = w
        if h:
            rec["h"] = h
        if props.get("NODE_SHAPE"):
            s = _shape(props["NODE_SHAPE"])
            if s:
                rec["shape"] = s
        if props.get("NODE_BORDER_PAINT"):
            rec["stroke"] = props["NODE_BORDER_PAINT"]
    else:
        for k in _EDGE_COLOUR_VP:
            if props.get(k):
                rec["color"] = props[k]
                break
        if _num(props.get("EDGE_WIDTH")):
            rec["width"] = _num(props["EDGE_WIDTH"])


def _aspects(cx):
    if isinstance(cx, dict):
        cx = [cx]
    if not isinstance(cx, list):
        raise GuessError("not a CX network (expected a JSON array of aspects)")
    out = {}
    for a in cx:
        if not isinstance(a, dict):
            continue
        for k, v in a.items():
            out.setdefault(k, []).extend(v if isinstance(v, list) else [v])
    return out


def cx_net(cx, names="name", directed=True):
    """A Net from CX2 or CX (version 1), parsed JSON. names="name" names nodes
    by their `name` attribute (made unique), names="id" as n<id> (as
    makeFromNDEx does); the name is the label either way."""
    asp = _aspects(cx)
    version2 = "CXVersion" in asp or "attributeDeclarations" in asp or any(
        isinstance(n, dict) and "v" in n for n in asp.get("nodes", [])[:5])
    net = Net()
    if version2:
        decl = (asp.get("attributeDeclarations") or [{}])[0]
        alias, dtype, default = {"node": {}, "edge": {}}, {"node": {}, "edge": {}}, {"node": {}, "edge": {}}
        for kind, key in (("node", "nodes"), ("edge", "edges")):
            for attr, spec in (decl.get(key) or {}).items():
                spec = spec or {}
                if spec.get("a"):
                    alias[kind][spec["a"]] = attr
                dtype[kind][attr] = spec.get("d", "string")
                if "v" in spec:
                    default[kind][attr] = spec["v"]
                if attr != "name":
                    net.types[kind][attr] = _CX_TYPES.get(spec.get("d"), STRING)
        vp = (asp.get("visualProperties") or [{}])[0] or {}
        vdef = vp.get("default") or {}
        node_def, edge_def = vdef.get("node") or {}, vdef.get("edge") or {}
        nby = {b.get("id"): b.get("v") for b in asp.get("nodeBypasses", []) if isinstance(b, dict)}
        eby = {b.get("id"): b.get("v") for b in asp.get("edgeBypasses", []) if isinstance(b, dict)}
        for rec in asp.get("nodes", []):
            v = {alias["node"].get(k, k): val for k, val in (rec.get("v") or {}).items()}
            for k, val in default["node"].items():
                v.setdefault(k, val)
            label = v.get("name", rec.get("id"))
            r = {"id": rec.get("id"), "want": f"n{rec.get('id')}" if names == "id" else label,
                 "label": label, "attrs": {k: _cx_value(val, dtype["node"].get(k)) for k, val in v.items() if k != "name"},
                 "x": rec.get("x"), "y": rec.get("y")}
            if names == "id":
                r["label"] = str(label)
            _vp_apply(r, node_def, "node")
            _vp_apply(r, nby.get(rec.get("id")), "node")
            net.nodes.append(r)
        for rec in asp.get("edges", []):
            v = {alias["edge"].get(k, k): val for k, val in (rec.get("v") or {}).items()}
            for k, val in default["edge"].items():
                v.setdefault(k, val)
            r = {"s": rec.get("s"), "t": rec.get("t"), "directed": directed,
                 "attrs": {k: _cx_value(val, dtype["edge"].get(k)) for k, val in v.items()}}
            _vp_apply(r, edge_def, "edge")
            _vp_apply(r, eby.get(rec.get("id")), "edge")
            net.edges.append(r)
        title = (asp.get("networkAttributes") or [{}])[0].get("name")
        return net, title
    # CX version 1
    nattr, eattr = {}, {}
    for kind, key, store in (("node", "nodeAttributes", nattr), ("edge", "edgeAttributes", eattr)):
        for a in asp.get(key, []):
            if not isinstance(a, dict) or "n" not in a:
                continue
            if a.get("s") is not None:          # a subnetwork's own value: the shared one comes first
                continue
            d = a.get("d")
            if d and a["n"] != "name":
                net.types[kind].setdefault(a["n"], _CX_TYPES.get(d, STRING))
            po = a.get("po")
            for i in (po if isinstance(po, list) else [po]):
                store.setdefault(i, {}).setdefault(a["n"], _cx_value(a.get("v"), d))
    layout = {}
    for p in asp.get("cartesianLayout", []):
        if isinstance(p, dict) and "node" in p:
            layout.setdefault(p["node"], (p.get("x"), p.get("y")))
    vdef = {"nodes:default": {}, "edges:default": {}}
    nby, eby = {}, {}
    for v in asp.get("cyVisualProperties", []) + asp.get("visualProperties", []):
        if not isinstance(v, dict):
            continue
        of = v.get("properties_of")
        props = v.get("properties") or {}
        if of in vdef:
            vdef[of] = props
        elif of == "nodes":
            nby[v.get("applies_to")] = props
        elif of == "edges":
            eby[v.get("applies_to")] = props
    for rec in asp.get("nodes", []):
        i = rec.get("@id")
        attrs = dict(nattr.get(i, {}))
        label = rec.get("n") if rec.get("n") not in (None, "") else attrs.get("name", i)
        attrs.pop("name", None)
        if rec.get("r"):
            attrs.setdefault("represents", rec["r"])
        x, y = layout.get(i, (None, None))
        r = {"id": i, "want": f"n{i}" if names == "id" else label, "label": label, "attrs": attrs, "x": x, "y": y}
        _vp_apply(r, vdef["nodes:default"], "node")
        _vp_apply(r, nby.get(i), "node")
        net.nodes.append(r)
    for rec in asp.get("edges", []):
        i = rec.get("@id")
        attrs = dict(eattr.get(i, {}))
        if rec.get("i") is not None:
            attrs.setdefault("interaction", rec["i"])
        r = {"s": rec.get("s"), "t": rec.get("t"), "directed": directed, "attrs": attrs}
        _vp_apply(r, vdef["edges:default"], "edge")
        _vp_apply(r, eby.get(i), "edge")
        net.edges.append(r)
    title = None
    for a in asp.get("networkAttributes", []):
        if isinstance(a, dict) and a.get("n") == "name":
            title = a.get("v")
    return net, title


def read_cx(graph, text, directed=True):
    try:
        cx = json.loads(text)
    except json.JSONDecodeError as e:
        raise GuessError(f"not a CX network: {e.msg} at line {e.lineno}") from None
    net, title = cx_net(cx, "name", directed)
    if not net.nodes:
        raise GuessError("no nodes in that CX network")
    return build(graph, net) + (title,)


# --------------------------------------------------------------------------
# XGMML
# --------------------------------------------------------------------------

_AMP = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _lattr(el, name):
    """An attribute by local name, whatever its namespace (cy:directed, xlink:href)."""
    v = el.get(name)
    if v is not None:
        return v
    for k, val in el.attrib.items():
        if _local(k) == name:
            return val
    return None


_XG_TYPES = {"integer": INT, "int": INT, "long": INT, "real": DOUBLE, "double": DOUBLE, "float": DOUBLE,
             "boolean": BOOL, "string": STRING}


def _att_value(a):
    t = (_lattr(a, "type") or "string").lower()
    if t == "list":
        return [_att_value(c) for c in a if _local(c.tag) == "att"]
    v = _lattr(a, "value")
    if v is None:
        return None
    try:
        if t in ("integer", "int", "long"):
            return int(float(v))
        if t in ("real", "double", "float"):
            return float(v)
        if t == "boolean":
            return v.strip().lower() in ("1", "true", "yes")
    except ValueError:
        return v
    return v


def _atts(el, types=None):
    out = {}
    for a in el:
        if _local(a.tag) != "att":
            continue
        name = _lattr(a, "name")
        if name is None or any(_local(c.tag) == "graph" for c in a):
            continue                               # nested networks hang off atts: not data
        out[name] = _att_value(a)
        if types is not None:
            t = (_lattr(a, "type") or "string").lower()
            if t in _XG_TYPES:
                types.setdefault(name, _XG_TYPES[t])
    return out


def _parse_xml(text, what):
    try:
        return ET.fromstring(_AMP.sub("&amp;", text))
    except ET.ParseError as e:
        line = e.position[0] if getattr(e, "position", None) else "?"
        raise GuessError(f"{what}: not well-formed XML at line {line} ({e})") from None


_XG_SKIP = {"selected", "SUID"}


def _xg_node(el, types):
    attrs = _atts(el, types)
    name = attrs.pop("name", None) or attrs.pop("canonicalName", None)
    attrs.pop("canonicalName", None)
    if attrs.get("shared name") == name:
        attrs.pop("shared name", None)
    for k in _XG_SKIP:
        attrs.pop(k, None)
    label = _lattr(el, "label")
    rec = {"id": _lattr(el, "id"), "want": name or label or _lattr(el, "id"), "attrs": attrs}
    if label not in (None, "") and label != rec["want"]:
        rec["label"] = label
    gr = next((c for c in el if _local(c.tag) == "graphics"), None)
    if gr is not None:
        rec.update(x=_lattr(gr, "x"), y=_lattr(gr, "y"), w=_lattr(gr, "w"), h=_lattr(gr, "h"),
                   color=_lattr(gr, "fill"), stroke=_lattr(gr, "outline"), shape=_shape(_lattr(gr, "type")))
    return rec


def _xg_edge(el, types, default_directed):
    attrs = _atts(el, types)
    for k in _XG_SKIP:
        attrs.pop(k, None)
    if attrs.get("shared interaction") == attrs.get("interaction"):
        attrs.pop("shared interaction", None)
    if attrs.get("shared name") == attrs.get("name"):
        attrs.pop("shared name", None)
    d = _lattr(el, "directed")
    directed = default_directed if d is None else d.strip().lower() in ("1", "true")
    rec = {"id": _lattr(el, "id"), "s": _lattr(el, "source"), "t": _lattr(el, "target"),
           "directed": directed, "attrs": attrs}
    lab = _lattr(el, "label")
    # Cytoscape labels edges "a (type) b": that's the name, not a label to show
    if lab and lab != attrs.get("name") and not re.match(r".+ \(.+\) .+", lab):
        rec["label"] = lab
    gr = next((c for c in el if _local(c.tag) == "graphics"), None)
    if gr is not None:
        rec.update(color=_lattr(gr, "fill"), width=_lattr(gr, "width"))
    return rec


def read_xgmml(graph, text):
    root = _parse_xml(text, "XGMML")
    if _local(root.tag) != "graph":
        root = next((e for e in root.iter() if _local(e.tag) == "graph"), None)
        if root is None:
            raise GuessError("not XGMML (no <graph> element)")
    directed = (_lattr(root, "directed") or "0").strip().lower() in ("1", "true")
    net = Net()
    for el in root:
        tag = _local(el.tag)
        if tag == "node" and _lattr(el, "href") is None:
            net.nodes.append(_xg_node(el, net.types["node"]))
        elif tag == "edge" and _lattr(el, "href") is None:
            net.edges.append(_xg_edge(el, net.types["edge"], directed))
    for t in net.types.values():
        for k in list(t):
            if k in ("name", "canonicalName"):
                del t[k]
    if not net.nodes:
        raise GuessError("no nodes in that XGMML file")
    return build(graph, net) + (_lattr(root, "label"),)


# --------------------------------------------------------------------------
# Cytoscape sessions (.cys)
# --------------------------------------------------------------------------

_TYPE_ROW = re.compile(r"^(java\.lang\.)?(long|integer|int|double|string|boolean|list.*|float)$", re.I)


def _read_cytable(text):
    """{SUID: {column: value}} from a Cytoscape session table (CSV)."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    head = rows[0]
    body = rows[1:]
    types = None
    while body and body[0] and all(_TYPE_ROW.match(c.strip()) or c.strip() == "" for c in body[0]):
        types = types or body[0]
        body = body[1:]
    key = head.index("SUID") if "SUID" in head else 0
    out = {}
    for r in body:
        if len(r) <= key:
            continue
        rec = {}
        for j, col in enumerate(head):
            if j == key or j >= len(r) or col in ("selected",):
                continue
            v = r[j]
            if v == "":
                continue
            t = (types[j] if types and j < len(types) else "").lower()
            try:
                if "long" in t or "integer" in t or t == "int":
                    v = int(float(v))
                elif "double" in t or "float" in t:
                    v = float(v)
                elif "boolean" in t:
                    v = v.lower() == "true"
            except ValueError:
                pass
            rec[col] = v
        out[r[key]] = rec
    return out


def cys_networks(data):
    """The networks in a .cys session: a list of dicts with name, nodes and
    edges (ids), definitions, attributes and view positions."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise GuessError("not a Cytoscape session (.cys is a zip file)") from None
    names = z.namelist()
    net_files = sorted(n for n in names if "/networks/" in "/" + n and n.endswith(".xgmml"))
    view_files = sorted(n for n in names if "/views/" in "/" + n and n.endswith(".xgmml"))
    if not net_files:
        raise GuessError("no networks in that Cytoscape session")
    node_tab, edge_tab = {}, {}
    for n in names:
        low = n.lower()
        if not low.endswith(".cytable"):
            continue
        target = node_tab if ("cynode" in low or "node" in os.path.basename(low)) else \
            edge_tab if ("cyedge" in low or "edge" in os.path.basename(low)) else None
        if target is None:
            continue
        for k, rec in _read_cytable(z.read(n).decode("utf-8", errors="replace")).items():
            target.setdefault(k, {}).update(rec)
    # views: network id -> {node id: (x, y, w, h, fill, outline, shape)}
    views = {}
    for vf in view_files:
        root = _parse_xml(z.read(vf).decode("utf-8", errors="replace"), vf)
        nid = _lattr(root, "networkId")
        pos = {}
        for el in root.iter():
            if _local(el.tag) != "node":
                continue
            ref = _lattr(el, "nodeId") or _lattr(el, "id")
            gr = next((c for c in el if _local(c.tag) == "graphics"), None)
            if ref is not None and gr is not None:
                pos[ref] = dict(x=_lattr(gr, "x"), y=_lattr(gr, "y"), w=_lattr(gr, "w"), h=_lattr(gr, "h"),
                                color=_lattr(gr, "fill"), stroke=_lattr(gr, "outline"),
                                shape=_shape(_lattr(gr, "type")))
        if nid is not None:
            views.setdefault(nid, pos)
    out = []
    for nf in net_files:
        root = _parse_xml(z.read(nf).decode("utf-8", errors="replace"), nf)
        types = {"node": {}, "edge": {}}
        directed = (_lattr(root, "directed") or "1").strip().lower() in ("1", "true")
        ndef, edef = {}, {}
        for el in root.iter():
            tag = _local(el.tag)
            if _lattr(el, "href") is not None or _lattr(el, "id") is None:
                continue
            if tag == "node":
                ndef[_lattr(el, "id")] = _xg_node(el, types["node"])
            elif tag == "edge":
                edef[_lattr(el, "id")] = _xg_edge(el, types["edge"], directed)
        subs = [el for el in root.iter() if _local(el.tag) == "graph" and el is not root
                and (_lattr(el, "registered") or "0") in ("1", "true")]
        graphs = subs or [root]
        for gel in graphs:
            gid = _lattr(gel, "id")
            if gel is root:
                nodes, edges = list(ndef), list(edef)
            else:
                nodes = [(_lattr(c, "href") or _lattr(c, "id") or "").lstrip("#") for c in gel
                         if _local(c.tag) == "node"]
                edges = [(_lattr(c, "href") or _lattr(c, "id") or "").lstrip("#") for c in gel
                         if _local(c.tag) == "edge"]
            name = _atts(gel).get("name") or _lattr(gel, "label") or os.path.splitext(os.path.basename(nf))[0]
            out.append(dict(name=str(name), id=gid, nodes=nodes, edges=edges, ndef=ndef, edef=edef,
                            types=types, view=views.get(gid) or views.get(_lattr(root, "id")) or {}))
    return out, node_tab, edge_tab


def cys_net(info, node_tab, edge_tab):
    net = Net()
    net.types = {k: dict(v) for k, v in info["types"].items()}
    for i in info["nodes"]:
        base = info["ndef"].get(i)
        if base is None:
            continue
        rec = dict(base)
        rec["attrs"] = dict(base["attrs"])
        tab = dict(node_tab.get(i, {}))
        nm = tab.pop("name", None)
        if tab.get("shared name") == nm:
            tab.pop("shared name", None)
        if nm and rec["want"] == i:
            rec["want"] = nm
        for k, v in tab.items():
            rec["attrs"].setdefault(k, v)
        v = info["view"].get(i)
        if v:
            rec.update({k: val for k, val in v.items() if val is not None})
        net.nodes.append(rec)
    keep = {r["id"] for r in net.nodes}
    for i in info["edges"]:
        base = info["edef"].get(i)
        if base is None or base["s"] not in keep or base["t"] not in keep:
            continue
        rec = dict(base)
        rec["attrs"] = dict(base["attrs"])
        tab = dict(edge_tab.get(i, {}))
        if tab.get("shared interaction") == tab.get("interaction"):
            tab.pop("shared interaction", None)
        if tab.get("shared name") == tab.get("name"):
            tab.pop("shared name", None)
        for k, v in tab.items():
            rec["attrs"].setdefault(k, v)
        net.edges.append(rec)
    return net


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def text_of(filename):
        with open(filename, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def done(filename, label, nn, ne, extra=""):
        session.scene()
        print(f"loaded {nn} nodes, {ne} edges from {os.path.basename(str(filename))} ({label}){extra}")

    @cmd
    def makeFromSIF(filename, directed=False):
        """makeFromSIF("network.sif") replaces the graph with a Cytoscape SIF
        file (simple interaction format): each line is `source type target
        [target …]`, or a lone node name. If the file has tabs, fields are
        tab-separated and names may contain spaces; otherwise names are
        separated by spaces. The type goes in the edge field `interaction`
        (colorize(interaction) shows it). directed=true makes every edge run
        from source to target."""
        text = text_of(filename)
        g = session.graph
        g.clear()
        nn, ne = read_sif(g, text, bool(directed))
        done(filename, "SIF", nn, ne)

    @cmd
    def makeFromNNF(filename):
        """makeFromNNF("nested.nnf") replaces the graph with a Cytoscape nested
        network file: lines `network node` (a node in a network) and `network
        source type target` (an edge), # comments. Every network's nodes and
        edges are loaded together: `network` says which network(s) each node
        and edge is in, and a node named after a network (one that stands for
        it, nested inside another) has that name in `nested`. So
        showOnly(network == 'M1') shows one network, and
        collapse(network == 'M1') folds a nested network into a node."""
        text = text_of(filename)
        g = session.graph
        g.clear()
        nn, ne, roots, nested = read_nnf(g, text)
        extra = ""
        if nested:
            extra = f"; nested networks: {', '.join(nested)} (field nested)"
        done(filename, "NNF", nn, ne, extra)

    @cmd
    def makeFromCYJS(filename):
        """makeFromCYJS("network.cyjs") replaces the graph with Cytoscape.js
        JSON, as Cytoscape exports for the web (File → Export → Network to
        File → Cytoscape.js JSON) and as Cytoscape.js uses: each node's and
        edge's data become fields, positions are kept, and compound (group)
        nodes become the field `parent` of their members. Nodes are named by
        their `name` (or label); a name two nodes share gets the node's id
        added. exportCYJS writes the format."""
        text = text_of(filename)
        g = session.graph
        g.clear()
        nn, ne = read_cyjs(g, text)
        done(filename, "Cytoscape.js JSON", nn, ne)

    @cmd
    def exportCYJS(filename="graph.cyjs"):
        """exportCYJS("graph.cyjs") writes the graph as Cytoscape.js JSON, which
        Cytoscape (File → Import → Network from File) and Cytoscape.js read:
        every field as data, positions, and each node's colour, size and
        shape as data (color, width, height, shape) for a style to map."""
        from .persist import _write_and_offer
        _write_and_offer(session, str(filename), write_cyjs(session.graph))

    @cmd
    def makeFromCX(filename, directed=True):
        """makeFromCX("network.cx2") replaces the graph with a network in CX2
        or CX (version 1), the formats of NDEx and Cytoscape's exchange
        format: attributes (typed as declared), node positions, and the
        default and per-node colours, sizes and shapes. Nodes are named by
        their `name` (a name two nodes share gets the id added). CX edges have
        a direction, as in Cytoscape; directed=false loads them undirected."""
        text = text_of(filename)
        g = session.graph
        g.clear()
        nn, ne, title = read_cx(g, text, bool(directed))
        done(filename, "CX", nn, ne, f": {title!r}" if title else "")

    @cmd
    def makeFromXGMML(filename):
        """makeFromXGMML("network.xgmml") replaces the graph with an XGMML file,
        Cytoscape's XML format: node and edge attributes (typed: string,
        integer, real, boolean; lists joined with '; '), and each node's
        graphics: position, size, fill and outline colour and shape. Files
        with bare '&' characters (a common fault) are repaired as they are
        read."""
        text = text_of(filename)
        g = session.graph
        g.clear()
        nn, ne, title = read_xgmml(g, text)
        done(filename, "XGMML", nn, ne, f": {title!r}" if title else "")

    @cmd
    def makeFromCYS(filename, network=None):
        """makeFromCYS("session.cys") opens a network from a Cytoscape session
        file: its attributes, and positions, colours, sizes and shapes from
        its view. A session can hold several networks: the first opens and
        the others are listed; makeFromCYS(file, "name") or
        makeFromCYS(file, 2) opens another, and makeFromCYS(file, "all") opens
        each as a graph of its own (tabs above the graph; use(name) switches).
        Styles (Cytoscape's visual mappings) aren't read."""
        with open(filename, "rb") as fh:
            data = fh.read()
        nets, node_tab, edge_tab = cys_networks(data)
        listing = [f"{i}: {n['name']} ({len(n['nodes'])} nodes)" for i, n in enumerate(nets)]
        if network == "all":
            picks = list(range(len(nets)))
        elif network is None:
            picks = [0]
        elif isinstance(network, int) and not isinstance(network, bool):
            if not 0 <= network < len(nets):
                raise GuessError(f"the session has networks 0 to {len(nets) - 1}: " + "; ".join(listing))
            picks = [network]
        else:
            want = str(network)
            picks = [i for i, n in enumerate(nets) if n["name"] == want] or \
                    [i for i, n in enumerate(nets) if n["name"].lower() == want.lower()]
            if not picks:
                raise GuessError(f"no network {want!r} in the session: " + "; ".join(listing))
            picks = picks[:1]
        first_graph = None
        for k, i in enumerate(picks):
            info = nets[i]
            if k > 0:
                session.ns["newGraph"](info["name"])
            g = session.graph
            g.clear()
            nn, ne = build(g, cys_net(info, node_tab, edge_tab))
            if network == "all":
                if k == 0:
                    try:
                        session.ns["renameGraph"](info["name"])
                    except GuessError:
                        pass
                    first_graph = session.workspaces["current"]
            done(filename, f"Cytoscape session: {info['name']}", nn, ne)
        if network == "all" and len(picks) > 1 and first_graph:
            session.ns["use"](first_graph)
        elif len(nets) > 1 and network != "all":
            print("networks in this session: " + "; ".join(listing)
                  + "\nmakeFromCYS(file, n) opens another; makeFromCYS(file, 'all') opens them all")


__all__ = ["install", "Net", "build", "unique_names", "read_sif", "read_nnf", "read_cyjs", "write_cyjs",
           "cx_net", "read_cx", "read_xgmml", "cys_networks", "cys_net"]
