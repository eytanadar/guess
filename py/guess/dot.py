"""Graphviz DOT reader (https://graphviz.org/doc/info/lang.html).

    digraph G { rankdir=LR; node [shape=box]; a -> b -> c [color=red]; {a b} -> d;
                subgraph cluster_x { label="X"; e; f } }

Handles graph/digraph/strict, node and edge statements (chains, subgraph
operands, ports ignored), default attributes (node [...], edge [...]) with
scoping, subgraphs (members of cluster_* get a `cluster` field), quoted strings
with + concatenation, HTML labels, and comments. Graphviz attributes map to
GUESS ones: pos (points, y up) → x, y; fillcolor/color → color; width/height
(inches) → size; shape → style; label; penwidth → edge width; weight. Other
attributes become fields (numbers when every value is one).
"""
import random
import re

from .model import DOUBLE, INT, STRING, GuessError, coerce

_TOKEN = re.compile(r"""
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<arrow>->|--)
  | (?P<punct>[{}\[\];,=:+])
  | (?P<num>-?(?:\.\d+|\d+(?:\.\d*)?))(?![A-Za-z_\x80-￿])
  | (?P<id>[A-Za-z_\x80-￿][\w\x80-￿]*)
  | (?P<html><)
  | (?P<bad>\S)
""", re.S | re.X)

KEYWORDS = {"strict", "graph", "digraph", "node", "edge", "subgraph"}


def _tokens(text):
    # lines starting with # are C-preprocessor output: ignored
    text = re.sub(r"(?m)^\s*#[^\n]*", "", text)
    out, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        kind = m.lastgroup
        if kind == "html":                       # <...> with nesting
            depth, j = 0, i
            while j < len(text):
                if text[j] == "<":
                    depth += 1
                elif text[j] == ">":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append(("id", re.sub(r"<[^>]*>", "", text[i + 1:j]).strip()))
            i = j + 1
            continue
        if kind == "bad":
            raise GuessError(f"DOT: unexpected {m.group()!r} near {text[max(0, i - 20):i + 20]!r}")
        if kind == "str":
            s = m.group()[1:-1].replace('\\"', '"').replace("\\\n", "")
            out.append(("id", s))
        elif kind == "id":
            low = m.group().lower()
            out.append(("kw", low) if low in KEYWORDS else ("id", m.group()))
        elif kind == "num":
            out.append(("id", m.group()))
        elif kind in ("arrow", "punct"):
            out.append((m.group(), m.group()))
        i = m.end()
    # "a" + "b" concatenation
    merged = []
    for t in out:
        if merged and len(merged) >= 2 and merged[-1][0] == "+" and merged[-2][0] == "id" and t[0] == "id":
            merged.pop()
            merged[-1] = ("id", merged[-1][1] + t[1])
        else:
            merged.append(t)
    return merged


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0
        self.nodes = {}            # name -> attrs (insertion order)
        self.edges = []            # (a, b, attrs)
        self.graph_attrs = {}

    def peek(self, k=0):
        return self.t[self.i + k][0] if self.i + k < len(self.t) else None

    def take(self, kind=None):
        if self.i >= len(self.t):
            raise GuessError("DOT: unexpected end of file")
        tok = self.t[self.i]
        if kind and tok[0] != kind and not (kind == "id" and tok[0] == "kw"):
            raise GuessError(f"DOT: expected {kind!r}, found {tok[1]!r}")
        self.i += 1
        return tok[1]

    def parse(self):
        if self.peek() == "kw" and self.t[self.i][1] == "strict":
            self.i += 1
        kw = self.take("kw") if self.peek() == "kw" else None
        if kw not in ("graph", "digraph"):
            raise GuessError("not a DOT file (needs 'graph' or 'digraph')")
        self.directed = kw == "digraph"
        if self.peek() == "id":
            self.take()
        self.take("{")
        self.stmts({}, {}, None)
        self.take("}")
        return self

    def attr_list(self):
        attrs = {}
        while self.peek() == "[":
            self.take("[")
            while self.peek() != "]":
                k = self.take("id")
                v = "true"
                if self.peek() == "=":
                    self.take("=")
                    v = self.take("id")
                attrs[k] = v
                if self.peek() in (",", ";"):
                    self.take()
            self.take("]")
        return attrs

    def node(self, name, ndef, cluster):
        if name not in self.nodes:
            self.nodes[name] = dict(ndef)
            if cluster:
                self.nodes[name].setdefault("cluster", cluster)
        return name

    def node_id(self):
        name = self.take("id")
        if self.peek() == ":":                  # port (and compass point): ignored
            self.take(":")
            self.take("id")
            if self.peek() == ":":
                self.take(":")
                self.take("id")
        return name

    def operand(self, ndef, edef, cluster):
        """A node id or a subgraph: the set of node names it stands for."""
        if self.peek() in ("{",) or (self.peek() == "kw" and self.t[self.i][1] == "subgraph"):
            return self.subgraph(ndef, edef, cluster)
        return [self.node(self.node_id(), ndef, cluster)]

    def subgraph(self, ndef, edef, cluster):
        name = None
        if self.peek() == "kw":
            self.take("kw")
            if self.peek() == "id":
                name = self.take("id")
        if name and name.startswith("cluster"):
            cluster = name[len("cluster"):].lstrip("_") or name
        self.take("{")
        before = set(self.nodes)
        members = self.stmts(dict(ndef), dict(edef), cluster)
        self.take("}")
        return members + [n for n in self.nodes if n not in before and n not in members]

    def stmts(self, ndef, edef, cluster):
        members = []
        while self.peek() not in ("}", None):
            if self.peek() == ";":
                self.take()
                continue
            tok = self.t[self.i]
            if tok == ("kw", "graph") or tok == ("kw", "node") or tok == ("kw", "edge"):
                self.take()
                attrs = self.attr_list()
                {"node": ndef, "edge": edef}.get(tok[1], self.graph_attrs if cluster is None else {}).update(attrs)
                continue
            if self.peek() == "id" and self.peek(1) == "=":
                k = self.take("id")
                self.take("=")
                v = self.take("id")
                if cluster is None:
                    self.graph_attrs[k] = v
                elif k == "label":
                    pass
                continue
            ops = [self.operand(ndef, edef, cluster)]
            while self.peek() in ("->", "--"):
                self.take()
                ops.append(self.operand(ndef, edef, cluster))
            attrs = self.attr_list()
            if len(ops) == 1:
                if len(ops[0]) == 1 and attrs:
                    self.nodes[ops[0][0]].update(attrs)
            else:
                for a_set, b_set in zip(ops, ops[1:]):
                    for a in a_set:
                        for b in b_set:
                            self.edges.append((a, b, {**edef, **attrs}))
            for o in ops:
                members += [n for n in o if n not in members]
        return members


# --------------------------------------------------------------------------

_SHAPES = {"box": 1, "rect": 1, "rectangle": 1, "square": 1, "ellipse": 2, "oval": 2, "circle": 2,
           "point": 2, "doublecircle": 2, "egg": 2, "triangle": 5, "diamond": 9, "Mrecord": 3, "record": 1}
_NODE_DONE = {"pos", "color", "fillcolor", "label", "width", "height", "shape", "fontcolor", "style"}
_EDGE_DONE = {"color", "label", "penwidth", "weight", "fontcolor", "pos", "style"}
_RESERVED_N = {"name", "x", "y", "visible", "color", "strokecolor", "labelcolor", "fixed", "style", "width",
               "height", "label", "image", "labelvisible", "indegree", "outdegree", "totaldegree"}
_RESERVED_E = {"node1", "node2", "directed", "source", "destination", "color", "labelcolor", "visible",
               "width", "weight", "label", "labelvisible"}


def _color(v):
    """A Graphviz colour: name, #rrggbb[aa], "h,s,v" or "h s v" (0..1), or a list "red:blue"."""
    from . import colors
    v = v.split(":")[0].split(";")[0].strip()
    m = re.fullmatch(r"([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)", v)
    if m:
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(*(min(1.0, float(x)) for x in m.groups()))
        return f"{round(r * 255)},{round(g * 255)},{round(b * 255)}"
    if re.fullmatch(r"#[0-9a-fA-F]{8}", v):
        v = v[:7]
    return v if colors.parse(v) is not None else None


def _type(values):
    def is_int(v):
        return re.fullmatch(r"-?\d+", v) is not None
    def is_num(v):
        return re.fullmatch(r"-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", v) is not None
    vals = [v for v in values if v != ""]
    if vals and all(is_int(v) for v in vals):
        return INT
    if vals and all(is_num(v) for v in vals):
        return DOUBLE
    return STRING


def _field_name(k, reserved):
    k = re.sub(r"\W", "_", k)
    if not k or k[0].isdigit():
        k = "_" + k
    return f"dot_{k}" if k in reserved else k


def read_dot(graph, text):
    p = _Parser(_tokens(text)).parse()
    # fields for the attributes GUESS has no equivalent for
    for recs, done, reserved, schema, add in (
            (list(p.nodes.values()), _NODE_DONE, _RESERVED_N, graph.node_schema, graph.addNodeField),
            ([a for _x, _y, a in p.edges], _EDGE_DONE, _RESERVED_E, graph.edge_schema, graph.addEdgeField)):
        keys = {}
        for r in recs:
            for k, v in r.items():
                if k not in done:
                    keys.setdefault(k, []).append(v)
        for k, vals in keys.items():
            name = _field_name(k, reserved)
            if name not in schema:
                t = _type(vals)
                add(name, t, coerce(t, None))
    has_pos = False
    for name, a in p.nodes.items():
        n = graph.addNode(name)
        if "label" in a and a["label"] not in ("\\N", ""):
            n.label = a["label"].replace("\\N", name).replace("\\n", " ").replace("\\l", " ").replace("\\r", " ").strip()
        m = re.match(r"\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)", a.get("pos", ""))
        if m:
            n.x, n.y = float(m.group(1)), -float(m.group(2))     # Graphviz y points up
            has_pos = True
        filled = "filled" in a.get("style", "")
        c = _color(a["fillcolor"]) if "fillcolor" in a else None
        if c is None and "color" in a and (filled or "fillcolor" not in a):
            c = _color(a["color"])
        if c:
            n.color = c
        for k, attr in (("width", "width"), ("height", "height")):
            try:
                setattr(n, attr, max(1.0, float(a[k]) * 72 / 3))    # inches → a GUESS-sized node
            except (KeyError, ValueError):
                pass
        if a.get("shape") in _SHAPES:
            n.style = _SHAPES[a["shape"]]
        _fields(graph.node_schema, n, a, _NODE_DONE, _RESERVED_N)
    count = 0
    for x, y, a in p.edges:
        e = graph.addEdge(x, y, p.directed)
        if "color" in a and _color(a["color"]):
            e.color = _color(a["color"])
        if "label" in a:
            e.label = a["label"]
        for k, attr in (("penwidth", "width"), ("weight", "weight")):
            try:
                setattr(e, attr, float(a[k]))
            except (KeyError, ValueError):
                pass
        _fields(graph.edge_schema, e, a, _EDGE_DONE, _RESERVED_E)
        count += 1
    if not has_pos:
        for n in graph._nodes_list():
            n.x = random.random() * 500
            n.y = random.random() * 500
    return len(p.nodes), count


def _fields(schema, elem, attrs, done, reserved):
    for k, v in attrs.items():
        if k in done:
            continue
        f = schema.get(_field_name(k, reserved))
        if f is None or f.readonly:
            continue
        try:
            f.set(elem, v)
        except (GuessError, TypeError, ValueError):
            pass
