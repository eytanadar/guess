"""Graph model: Graph, Node, Edge, GSet (sets of graph elements) and Field.

Mirrors the semantics of com/hp/hpl/guess/{Graph,Node,Edge,Field}.java, with
field storage held in plain Python dicts instead of HSQLDB.
"""
import operator
import re

from . import colors

# --------------------------------------------------------------------------
# Field types
# --------------------------------------------------------------------------

STRING = "VARCHAR"
INT = "INTEGER"
DOUBLE = "DOUBLE"
BOOL = "BOOLEAN"

_TYPE_ALIASES = {
    "varchar": STRING, "string": STRING, "str": STRING, "longvarchar": STRING, "text": STRING,
    "int": INT, "integer": INT, "tinyint": INT, "smallint": INT, "bigint": INT,
    "double": DOUBLE, "float": DOUBLE, "real": DOUBLE, "decimal": DOUBLE, "numeric": DOUBLE,
    "boolean": BOOL, "bool": BOOL, "bit": BOOL,
}


def normalize_type(t):
    if t in (str,):
        return STRING
    if t in (int,):
        return INT
    if t in (float,):
        return DOUBLE
    if t in (bool,):
        return BOOL
    s = str(t).strip().lower()
    s = s.split("(")[0]
    if s in _TYPE_ALIASES:
        return _TYPE_ALIASES[s]
    raise ValueError(f"unsupported field type: {t!r}")


def coerce(ftype, value):
    if value is None:
        return None
    if ftype == STRING:
        return value if isinstance(value, str) else str(value)
    if ftype == INT:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
            return int(float(value))
        return int(value)
    if ftype == DOUBLE:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        return float(value)
    if ftype == BOOL:
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "t")
        return bool(value)
    return value


class GuessError(Exception):
    """User-facing error raised by GUESS operations."""


# --------------------------------------------------------------------------
# Sets of graph elements
# --------------------------------------------------------------------------

class Values(list):
    """The values of one field over a set, e.g. ``(dept == "x").degree``: a list
    with summaries (.avg, .sum, .min, .max, .median, .distinct, .count)."""

    def _numeric(self):
        return [v for v in self if isinstance(v, (int, float)) and not isinstance(v, bool)]

    @property
    def count(self):
        return len(self)

    @property
    def sum(self):
        return sum(self._numeric())

    @property
    def avg(self):
        vals = self._numeric()
        return sum(vals) / len(vals) if vals else None

    mean = avg

    @property
    def median(self):
        vals = sorted(self._numeric())
        if not vals:
            return None
        m = len(vals) // 2
        return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2

    @property
    def min(self):
        vals = [v for v in self if v is not None]
        return min(vals) if vals else None

    @property
    def max(self):
        vals = [v for v in self if v is not None]
        return max(vals) if vals else None

    @property
    def distinct(self):
        out, seen = [], set()
        for v in self:
            k = v if v.__hash__ is not None else id(v)
            if k not in seen:
                seen.add(k)
                out.append(v)
        return out


class GSet(list):
    """An ordered collection of nodes/edges (or of other GSets).

    Attribute assignment broadcasts: ``g.nodes.color = red``.
    Attribute reads return a list of values: ``(freq > 10).freq``.
    ``&`` / ``|`` are order-preserving intersection / union; ``.difference(other)`` removes
    elements. (In Gython, ``a - b`` between nodes selects edges, as in the original.)
    """

    def __init__(self, items=(), annotation=None):
        super().__init__(items)
        object.__setattr__(self, "annotation", annotation)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return Values(getattr(x, name) for x in self)

    def __setattr__(self, name, value):
        if name == "annotation":
            object.__setattr__(self, name, value)
            return
        for x in self:
            setattr(x, name, value)

    # set algebra -----------------------------------------------------
    def __and__(self, other):
        other = _as_seq(other)
        if other is None:
            return NotImplemented
        keep = set(map(id, _flatten(other)))
        return GSet((x for x in _flatten(self) if id(x) in keep))

    def __rand__(self, other):
        other = _as_seq(other)
        if other is None:
            return NotImplemented
        return GSet(other) & self

    def __or__(self, other):
        other = _as_seq(other)
        if other is None:
            return NotImplemented
        seen = set()
        out = GSet()
        for x in list(_flatten(self)) + list(_flatten(other)):
            if id(x) not in seen:
                seen.add(id(x))
                out.append(x)
        return out

    def __ror__(self, other):
        other = _as_seq(other)
        if other is None:
            return NotImplemented
        return GSet(other) | self

    def difference(self, other):
        """The elements of this set that are not in other (order-preserving)."""
        seq = _as_seq(other)
        if seq is None:
            raise GuessError(f"can't remove {other!r} from a set")
        drop = set(map(id, _flatten(seq)))
        return GSet((x for x in _flatten(self) if id(x) not in drop))

    def __getitem__(self, key):
        r = super().__getitem__(key)
        if isinstance(key, slice):
            return GSet(r, self.annotation)
        return r

    # helpers ----------------------------------------------------------
    def sortBy(self, field, descending=False):
        return sort_by(self, field, descending)

    def groupBy(self, field):
        return group_by(self, field)

    def groupAndSortBy(self, field):
        return group_by(self, field, sort=True)

    @property
    def nodes(self):
        """The nodes in the set plus the endpoints of its edges, e.g.
        (freq > 100).nodes: everyone involved in a heavy edge."""
        out, seen = [], set()
        for x in _flatten(self):
            for n in ((x,) if isinstance(x, Node) else (x._n1, x._n2) if isinstance(x, Edge) else ()):
                if id(n) not in seen:
                    seen.add(id(n))
                    out.append(n)
        return GSet(out, "nodes")

    @property
    def edges(self):
        """The edges in the set plus the edges touching its nodes, e.g.
        (dept == 'dept3').edges: every edge of department three."""
        out, seen = [], set()
        for x in _flatten(self):
            for e in ((x,) if isinstance(x, Edge) else x._inc.values() if isinstance(x, Node) else ()):
                if id(e) not in seen:
                    seen.add(id(e))
                    out.append(e)
        return GSet(out, "edges")


def _as_seq(o):
    if isinstance(o, (Node, Edge)):
        return [o]
    if isinstance(o, (list, tuple, set, frozenset)):
        return list(o)
    return None


def _flatten(seq):
    for x in seq:
        if isinstance(x, (list, tuple, set, frozenset)):
            yield from _flatten(x)
        else:
            yield x


def elements_of(obj):
    """Yield the graph elements contained in obj (node, edge, or nested seqs)."""
    if isinstance(obj, (Node, Edge)):
        yield obj
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for x in obj:
            yield from elements_of(x)


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------

NODE = "node"
EDGE = "edge"

_OPS = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt,
    "<=": operator.le, ">": operator.gt, ">=": operator.ge,
}


class Field:
    """A node or edge attribute. Comparing a field yields the matching elements.

    ``freq > 10`` -> GSet of edges; ``x > y`` -> nodes whose x exceeds y.
    """

    def __init__(self, graph, name, kind, ftype, default=None, *, visual=False,
                 readonly=False, compute=None, builtin=False):
        self.graph = graph
        self.name = name
        self.kind = kind
        self.type = ftype
        self.default = coerce(ftype, default)
        self.visual = visual
        self.readonly = readonly
        self.compute = compute
        self.builtin = builtin
        # computed fields (betweenness, component, ...): the graph version
        # their values describe; reading them on a changed graph recomputes
        # them once. None for ordinary fields and computed ones a user has
        # assigned to (their values are the user's from then on).
        self.lazy_at = None

    __hash__ = object.__hash__

    def __repr__(self):
        return self.name

    # value access -------------------------------------------------------
    def get(self, elem):
        if self.compute is not None:
            return self.compute(elem)
        if self.lazy_at is not None and self.lazy_at != self.graph._version:
            self.graph._refresh_lazy(self)
        return elem._vals.get(self.name, self.default)

    def set(self, elem, value):
        if self.readonly:
            raise GuessError(f"field '{self.name}' is read-only")
        if self.name == "labelpos" and self.kind == NODE and value is not None:
            value = str(value).lower()
            if value not in LABEL_POSITIONS:
                raise GuessError(f"labelpos should be one of {', '.join(LABEL_POSITIONS)}, got {value!r}")
        if self.name == "labelsize" and value is not None and float(value) <= 0:
            raise GuessError("labelsize should be a positive scale (1 = normal)")
        if self.name.endswith("color") and value is not None:
            try:
                value = colors.normalize(value)
            except ValueError as e:
                raise GuessError(str(e)) from None
        try:
            v = coerce(self.type, value)
        except (TypeError, ValueError):
            raise GuessError(
                f"cannot store {value!r} in {self.kind} field '{self.name}' ({self.type})"
            ) from None
        j = self.graph.journal
        if j is not None:
            j.note(elem, self.name)
        if self.lazy_at is not None:
            self.lazy_at = None          # assigned by the user: no longer recomputed
        if self.name == "weight" and self.kind == EDGE:
            self.graph._version += 1     # weighted measures depend on it
        was = elem._vals.get(self.name, self.default) if self.name == "visible" else None
        elem._vals[self.name] = v
        if self.name == "visible" and bool(v) != bool(was):
            self.graph._visibility_cascade(elem, bool(v))
        if self.visual:
            if self.name in ("x", "y") and isinstance(elem, Node):
                self.graph.moved_nodes.add(elem._id)
            else:
                self.graph._mark(elem)

    def elements(self):
        return self.graph._nodes_list() if self.kind == NODE else self.graph._edges_list()

    def values(self):
        return [self.get(e) for e in self.elements()]

    # aggregates ---------------------------------------------------------
    def _numeric(self):
        return [v for v in self.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]

    @property
    def max(self):
        vals = [v for v in self.values() if v is not None]
        return max(vals) if vals else None

    @property
    def min(self):
        vals = [v for v in self.values() if v is not None]
        return min(vals) if vals else None

    @property
    def avg(self):
        vals = self._numeric()
        return sum(vals) / len(vals) if vals else None

    @property
    def sum(self):
        return sum(self._numeric())

    @property
    def median(self):
        return Values(self.values()).median

    @property
    def count(self):
        return len(self.values())

    def __iter__(self):
        """``max(degree)``, ``for v in dept``: the field's values."""
        return iter(self.values())

    @property
    def distinct(self):
        out = []
        seen = set()
        for v in self.values():
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    # queries --------------------------------------------------------------
    def _query(self, sym, other):
        op = _OPS[sym]
        out = GSet(annotation=f"{self.name} {sym} {_fmt(other)}")
        if isinstance(other, Field):
            if other.kind != self.kind:
                raise GuessError(f"cannot compare {self.kind} field '{self.name}' "
                                 f"with {other.kind} field '{other.name}'")
            for e in self.elements():
                a, b = self.get(e), other.get(e)
                if _safe(op, a, b):
                    out.append(e)
        else:
            other = _query_value(self, other)
            for e in self.elements():
                if _safe(op, self.get(e), other):
                    out.append(e)
        return out

    def __eq__(self, other):
        return self._query("==", other)

    def __ne__(self, other):
        return self._query("!=", other)

    def __lt__(self, other):
        return self._query("<", other)

    def __le__(self, other):
        return self._query("<=", other)

    def __gt__(self, other):
        return self._query(">", other)

    def __ge__(self, other):
        return self._query(">=", other)

    def __getitem__(self, state):
        """``freq[1999]``: this field's values in a saved state."""
        from .states import field_in_state
        return field_in_state(self, state)

    def find(self, value):
        """``dept.find('eng')``: the elements whose value is 'eng' (the same
        as ``dept == 'eng'``)."""
        return self._query("==", value)

    def isin(self, values):
        """``dept in ("a", "b")`` in Gython: the elements whose value is one of
        values."""
        if isinstance(values, (str, Field)) or not hasattr(values, "__iter__"):
            values = [values]
        want = [_query_value(self, v) for v in values]
        shown = ", ".join(_fmt(v) for v in values)
        out = GSet(annotation=f"{self.name} in ({shown})")
        for e in self.elements():
            v = self.get(e)
            if any(_safe(operator.eq, v, w) for w in want):
                out.append(e)
        return out

    def like(self, pattern):
        """SQL LIKE: ``%`` matches any run, ``_`` any single character."""
        rx = _like_regex(str(pattern))
        out = GSet(annotation=f"{self.name} like {pattern!r}")
        for e in self.elements():
            v = self.get(e)
            if v is not None and rx.fullmatch(str(v)):
                out.append(e)
        return out


def _fmt(v):
    return v.name if isinstance(v, Field) else repr(v)


def _query_value(field, v):
    if isinstance(v, (Node, Edge)):
        return v
    try:
        return coerce(field.type, v)
    except (TypeError, ValueError):
        return v


def _safe(op, a, b):
    if a is None or b is None:
        if op is operator.eq:
            return a is None and b is None
        if op is operator.ne:
            return not (a is None and b is None)
        return False
    try:
        return op(a, b)
    except TypeError:
        return False


_like_cache = {}


def _like_regex(pattern):
    rx = _like_cache.get(pattern)
    if rx is None:
        parts = []
        for ch in pattern:
            if ch == "%":
                parts.append(".*")
            elif ch == "_":
                parts.append(".")
            else:
                parts.append(re.escape(ch))
        rx = re.compile("".join(parts), re.DOTALL)
        _like_cache[pattern] = rx
    return rx


class FieldNamespace:
    """``Node.width`` / ``Edge.width`` disambiguation objects."""

    def __init__(self, graph, kind):
        object.__setattr__(self, "_graph", graph)
        object.__setattr__(self, "_kind", kind)

    def __getattr__(self, name):
        schema = self._graph.node_schema if self._kind == NODE else self._graph.edge_schema
        f = schema.get(name) or self._graph._lazy_field(self._kind, name)
        if f is None:
            raise AttributeError(f"no {self._kind} field '{name}'")
        return f

    def __setattr__(self, name, value):
        raise GuessError(f"{'Node' if self._kind == NODE else 'Edge'} fields are read-only here")

    def setRangeField(self, field):
        """Node.setRangeField(span): the text field that holds existence ranges
        for `Node rcontains …` etc. (default: a field called range)."""
        if not isinstance(field, Field) or field.kind != self._kind:
            raise GuessError(f"setRangeField needs a {self._kind} field")
        self._graph.range_fields[self._kind] = field.name

    def rebuildRangeIndex(self):
        """Kept for old scripts: ranges are read when queried, so nothing to rebuild."""

    def __dir__(self):
        schema = self._graph.node_schema if self._kind == NODE else self._graph.edge_schema
        return list(schema) + ["setRangeField", "rebuildRangeIndex"]

    def __repr__(self):
        return "Node" if self._kind == NODE else "Edge"


# --------------------------------------------------------------------------
# Nodes and edges
# --------------------------------------------------------------------------

class Node:
    __slots__ = ("_g", "_id", "_name", "_vals", "_inc", "__weakref__")

    def __init__(self, graph, nid, name):
        object.__setattr__(self, "_g", graph)
        object.__setattr__(self, "_id", nid)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_vals", {})
        object.__setattr__(self, "_inc", {})  # edge id -> Edge

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        g = self._g
        f = g.node_schema.get(name) or g._lazy_field(NODE, name)
        if f is None:
            raise AttributeError(f"node '{self._name}' has no field '{name}'")
        return f.get(self)

    def __setattr__(self, name, value):
        if name == "size":
            self.width = value
            self.height = value
            return
        f = self._g.node_schema.get(name)
        if f is None:
            raise GuessError(f"no node field '{name}' (create it with addNodeField)")
        f.set(self, value)

    def __repr__(self):
        return self._name

    def __dir__(self):
        return sorted(set(self._g.node_schema) | {"size"} | {
            k for k in type(self).__dict__ if not k.startswith("_")})

    def __getitem__(self, state):
        from .states import element_in_state
        return element_in_state(self, state)

    @property
    def name(self):
        return self._name

    @property
    def size(self):
        return self.width

    # structure ------------------------------------------------------------
    def getIncidentEdges(self):
        return GSet(self._inc.values())

    def getOutEdges(self):
        return GSet(e for e in self._inc.values() if not e._directed or e._n1 is self)

    def getInEdges(self):
        return GSet(e for e in self._inc.values() if not e._directed or e._n2 is self)

    def getNeighbors(self):
        out = GSet()
        seen = set()
        for e in self._inc.values():
            o = e._n2 if e._n1 is self else e._n1
            if id(o) not in seen:
                seen.add(id(o))
                out.append(o)
        return out

    def getSuccessors(self):
        return GSet(dict.fromkeys(e.opposite(self) for e in self.getOutEdges()))

    def getPredecessors(self):
        return GSet(dict.fromkeys(e.opposite(self) for e in self.getInEdges()))

    neighbors = getNeighbors

    def unweightedShortestPath(self, other):
        """The edges of a shortest path (fewest edges) to ``other``, following edge
        direction, as in the original: (v291.unweightedShortestPath(v376)).color = blue.
        Empty if there is no path; len(...) is the distance."""
        return self._shortest_path(other, weighted=False)

    def dijkstraShortestPath(self, other):
        """The edges of the shortest path to ``other`` using edge weights as lengths."""
        return self._shortest_path(other, weighted=True)

    def _shortest_path(self, other, weighted):
        import heapq
        if not isinstance(other, Node):
            raise GuessError("needs a target node")
        out = GSet(annotation=f"path {self._name} to {other._name}")
        if other is self:
            return out
        def steps(n):
            for e in n._inc.values():
                if e._directed and e._n1 is not n:
                    continue
                m = e.opposite(n)
                if m is not n:
                    yield e, m
        prev = {id(self): None}
        if weighted:
            dist = {id(self): 0.0}
            heap = [(0.0, 0, self)]
            k = 1
            while heap:
                d, _k, n = heapq.heappop(heap)
                if n is other:
                    break
                if d > dist[id(n)]:
                    continue
                for e, m in steps(n):
                    try:
                        w = abs(float(e._vals.get("weight", 1.0)))
                    except (TypeError, ValueError):
                        w = 1.0
                    nd = d + w
                    if nd < dist.get(id(m), float("inf")):
                        dist[id(m)] = nd
                        prev[id(m)] = (n, e)
                        heapq.heappush(heap, (nd, k, m))
                        k += 1
        else:
            frontier = [self]
            while frontier and id(other) not in prev:
                nxt = []
                for n in frontier:
                    for e, m in steps(n):
                        if id(m) not in prev:
                            prev[id(m)] = (n, e)
                            nxt.append(m)
                frontier = nxt
        if id(other) not in prev:
            return out
        path, n = [], other
        while prev[id(n)] is not None:
            n, e = prev[id(n)]
            path.append(e)
        out.extend(reversed(path))
        return out

    # graph elements are handles: copying one (e.g. networkx deep-copying a
    # graph that carries them as attributes) must give back the same element
    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


class Edge:
    __slots__ = ("_g", "_id", "_n1", "_n2", "_directed", "_vals", "__weakref__")

    def __copy__(self):          # a handle, like Node
        return self

    def __deepcopy__(self, memo):
        return self

    def __init__(self, graph, eid, n1, n2, directed):
        object.__setattr__(self, "_g", graph)
        object.__setattr__(self, "_id", eid)
        object.__setattr__(self, "_n1", n1)
        object.__setattr__(self, "_n2", n2)
        object.__setattr__(self, "_directed", bool(directed))
        object.__setattr__(self, "_vals", {})

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        g = self._g
        f = g.edge_schema.get(name) or g._lazy_field(EDGE, name)
        if f is None:
            raise AttributeError(f"edge {self!r} has no field '{name}'")
        return f.get(self)

    def __setattr__(self, name, value):
        f = self._g.edge_schema.get(name)
        if f is None:
            raise GuessError(f"no edge field '{name}' (create it with addEdgeField)")
        f.set(self, value)

    def __repr__(self):
        return f"{self._n1._name}{'->' if self._directed else '-'}{self._n2._name}"

    def __getitem__(self, state):
        from .states import element_in_state
        return element_in_state(self, state)

    def __dir__(self):
        return sorted(set(self._g.edge_schema) | {
            k for k in type(self).__dict__ if not k.startswith("_")})

    def opposite(self, node):
        return self._n2 if node is self._n1 else self._n1

    def getNode1(self):
        return self._n1

    def getNode2(self):
        return self._n2


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------

_NODE_BUILTINS = [
    # name, type, default, visual
    ("name", STRING, None, False),
    ("x", DOUBLE, 500.0, True),
    ("y", DOUBLE, 500.0, True),
    ("visible", BOOL, True, True),
    ("color", STRING, "cornflowerblue", True),
    ("strokecolor", STRING, None, True),
    ("labelcolor", STRING, None, True),
    ("fixed", BOOL, False, False),
    ("style", INT, 2, True),
    ("width", DOUBLE, 10.0, True),
    ("height", DOUBLE, 10.0, True),
    ("label", STRING, None, True),
    ("image", STRING, None, True),
    ("labelvisible", BOOL, False, True),
    ("labelpos", STRING, "right", True),
    ("labelsize", DOUBLE, 1.0, True),
]

# where a node's label goes; "outside" lets GUESS pick a free side
LABEL_POSITIONS = ("right", "left", "above", "below", "inside", "outside")

_EDGE_BUILTINS = [
    ("color", STRING, "dandelion", True),
    ("labelcolor", STRING, None, True),
    ("visible", BOOL, True, True),
    ("width", DOUBLE, 2.0, True),
    ("weight", DOUBLE, 1.0, False),
    ("label", STRING, None, True),
    ("labelvisible", BOOL, False, True),
    ("labelsize", DOUBLE, 1.0, True),
]


_UNSET = object()

class Journal:
    """What one command changed, so it can be undone: structural operations in
    order, each touched field value's previous value (first change only), and
    copies of g.deleted / g.bends if they changed."""

    __slots__ = ("ops", "values", "deleted", "bends")

    def __init__(self):
        self.ops = []          # ("add"|"rem", elem) | ("field"|"unfield", schema, name, Field)
        self.values = {}       # (id(elem), name) -> (elem, name, old value or _UNSET)
        self.deleted = None
        self.bends = None

    def note(self, elem, name):
        key = (id(elem), name)
        if key not in self.values:
            self.values[key] = (elem, name, elem._vals.get(name, _UNSET))

    def __bool__(self):
        return bool(self.ops or self.values) or self.deleted is not None or self.bends is not None

    def size(self):
        return len(self.ops) + len(self.values) + len(self.deleted or ()) + len(self.bends or ())


class Graph:
    """The working graph, bound to ``g`` in the namespace."""

    def __init__(self):
        self._nodes = {}          # name -> Node (insertion order)
        self._node_ids = {}       # id -> Node
        self._edges = {}          # id -> Edge (insertion order)
        self._deleted = {}        # (kind, id) -> removed element, for add()
        self._next_node_id = 0
        self._next_edge_id = 0
        self.node_schema = {}
        self.edge_schema = {}
        self.listeners = []       # objects with optional on_* methods
        self.lazy_fields = {}     # (kind, name) -> callable(graph) -> {elem: value}
        self._version = 0         # bumped by every structural change (computed fields check it)
        self._dropped_lazy = set()   # computed fields in use when the graph was cleared
        self.states = {}          # filled in by states.install
        self.ranges = {}          # element -> [(lo, hi)], filled in by ranges.install
        self.bends = {}           # edge -> [(x, y), ...] route through these points
        self.journal = None       # Journal recording changes while a command runs (undo)
        self.range_fields = {NODE: "range", EDGE: "range"}   # text fields holding ranges
        self._clearing = False
        self._keep_names = False      # set while remove()/removeNode() run (names stay bound)
        self.reset_dirty()
        for name, t, d, vis in _NODE_BUILTINS:
            self.node_schema[name] = Field(self, name, NODE, t, d, visual=vis, builtin=True,
                                           readonly=(name == "name"),
                                           compute=(lambda n: n._name) if name == "name" else None)
        for name, fn in (("indegree", lambda n: len(n.getInEdges())),
                         ("outdegree", lambda n: len(n.getOutEdges())),
                         ("totaldegree", lambda n: len(n._inc)),
                         ("degree", lambda n: len(n._inc))):     # the usual name for totaldegree
            self.node_schema[name] = Field(self, name, NODE, INT, 0, readonly=True,
                                           compute=fn, builtin=True)
        self.edge_schema["node1"] = Field(self, "node1", EDGE, STRING, readonly=True,
                                          compute=lambda e: e._n1, builtin=True)
        self.edge_schema["node2"] = Field(self, "node2", EDGE, STRING, readonly=True,
                                          compute=lambda e: e._n2, builtin=True)
        self.edge_schema["directed"] = Field(self, "directed", EDGE, BOOL, False, readonly=True,
                                             compute=lambda e: e._directed, builtin=True)
        # the manual's (bob->alice).source / .destination (None for undirected edges)
        self.edge_schema["source"] = Field(self, "source", EDGE, STRING, readonly=True,
                                           compute=lambda e: e._n1 if e._directed else None, builtin=True)
        self.edge_schema["destination"] = Field(self, "destination", EDGE, STRING, readonly=True,
                                                compute=lambda e: e._n2 if e._directed else None, builtin=True)
        for name, t, d, vis in _EDGE_BUILTINS:
            self.edge_schema[name] = Field(self, name, EDGE, t, d, visual=vis, builtin=True)

    # change tracking ------------------------------------------------------
    def reset_dirty(self):
        self.dirty_nodes = set()
        self.moved_nodes = set()  # nodes whose only visual change may be x/y
        self.dirty_edges = set()
        self.removed_nodes = set()
        self.removed_edges = set()

    def _mark(self, elem):
        if isinstance(elem, Node):
            self.dirty_nodes.add(elem._id)
        else:
            self.dirty_edges.add(elem._id)

    def set_bends(self, edge, points):
        """Route an edge through intermediate points (centre coordinates)."""
        self._touch("bends")
        if points:
            self.bends[edge] = [(float(x), float(y)) for x, y in points]
        else:
            self.bends.pop(edge, None)
        self._mark(edge)

    def clear_bends(self):
        for e in list(self.bends):
            self.set_bends(e, None)

    def _emit(self, event, *args):
        for listener in self.listeners:
            fn = getattr(listener, event, None)
            if fn is not None:
                fn(*args)

    # collections -----------------------------------------------------------
    @property
    def nodes(self):
        return GSet(self._nodes.values(), "g.nodes")

    @property
    def edges(self):
        return GSet(self._edges.values(), "g.edges")

    def _nodes_list(self):
        return list(self._nodes.values())

    def _edges_list(self):
        return list(self._edges.values())

    def getNodeByName(self, name):
        return self._nodes.get(name)

    def node_by_id(self, nid):
        return self._node_ids.get(nid)

    def edge_by_id(self, eid):
        return self._edges.get(eid)

    def __repr__(self):
        return f"<graph: {len(self._nodes)} nodes, {len(self._edges)} edges>"

    # schema ---------------------------------------------------------------
    def addNodeField(self, name, ftype, default=None):
        return self._add_field(self.node_schema, NODE, name, ftype, default)

    def addEdgeField(self, name, ftype, default=None):
        return self._add_field(self.edge_schema, EDGE, name, ftype, default)

    def _add_field(self, schema, kind, name, ftype, default):
        if not str(name).isidentifier():
            raise GuessError(f"invalid field name: {name!r}")
        if name in schema:
            return schema[name]
        f = Field(self, name, kind, normalize_type(ftype), default)
        schema[name] = f
        if self.journal is not None:
            self.journal.ops.append(("field", schema, name, f))
        self._emit("on_field_added", f)
        return f

    def _lazy_field(self, kind, name):
        """Create computed-on-first-access fields such as betweenness/pagerank."""
        fn = self.lazy_fields.get((kind, name))
        if fn is None:
            return None
        values = fn(self)
        ftype = DOUBLE
        if isinstance(values, tuple):   # (values, type) for integer-valued statistics
            values, ftype = values
        schema = self.node_schema if kind == NODE else self.edge_schema
        f = Field(self, name, kind, ftype, 0 if ftype == INT else 0.0)
        for elem, v in values.items():
            elem._vals[name] = v
        f.lazy_at = self._version
        schema[name] = f
        self._emit("on_field_added", f)
        return f

    def _refresh_lazy(self, f):
        """Recompute a computed field for the current graph (it was computed
        before the graph changed). Values go straight in: not an undo step."""
        fn = self.lazy_fields.get((f.kind, f.name))
        f.lazy_at = self._version          # first, so reads inside fn don't recurse
        if fn is None:
            return
        values = fn(self)
        if isinstance(values, tuple):
            values = values[0]
        elems = self._nodes_list() if f.kind == NODE else self._edges_list()
        for elem in elems:
            elem._vals[f.name] = values.get(elem, f.default)

    def _adopt_computed(self):
        """Fields named like computed ones (from a file, a projection or a
        subgraph) may describe another graph: mark them stale so the first
        read recomputes them."""
        for (kind, name) in self.lazy_fields:
            schema = self.node_schema if kind == NODE else self.edge_schema
            f = schema.get(name)
            if f is not None and f.compute is None and not f.builtin:
                f.lazy_at = -1

    # mutation -------------------------------------------------------------
    def addNode(self, name, **attrs):
        name = str(name)
        if name in self._nodes:
            n = self._nodes[name]
        else:
            n = Node(self, self._next_node_id, name)
            self._next_node_id += 1
            self._nodes[name] = n
            self._node_ids[n._id] = n
            self._version += 1
            self._mark(n)
            if self.journal is not None:
                self.journal.ops.append(("add", n))
            self._emit("on_node_added", n)
        for k, v in attrs.items():
            setattr(n, k, v)
        return n

    def addEdge(self, n1, n2, directed=False, **attrs):
        n1 = self._resolve(n1)
        n2 = self._resolve(n2)
        e = Edge(self, self._next_edge_id, n1, n2, directed)
        self._next_edge_id += 1
        self._edges[e._id] = e
        n1._inc[e._id] = e
        n2._inc[e._id] = e
        self._version += 1
        self._mark(e)
        if self.journal is not None:
            self.journal.ops.append(("add", e))
        for k, v in attrs.items():
            setattr(e, k, v)
        return e

    def addDirectedEdge(self, n1, n2, **attrs):
        return self.addEdge(n1, n2, True, **attrs)

    def addUndirectedEdge(self, n1, n2, **attrs):
        return self.addEdge(n1, n2, False, **attrs)

    def removeEdge(self, e):
        if self._edges.pop(e._id, None) is None:
            return False
        e._n1._inc.pop(e._id, None)
        e._n2._inc.pop(e._id, None)
        self._version += 1
        self.dirty_edges.discard(e._id)
        self.removed_edges.add(e._id)
        if self.journal is not None:
            self.journal.ops.append(("rem", e))
        return True

    def removeNode(self, n):
        n = self._resolve(n)
        for e in list(n._inc.values()):
            self.removeEdge(e)
        del self._nodes[n._name]
        self._version += 1
        del self._node_ids[n._id]
        self.dirty_nodes.discard(n._id)
        self.removed_nodes.add(n._id)
        if self.journal is not None:
            self.journal.ops.append(("rem", n))
        self._emit("on_node_removed", n)
        return True

    def remove(self, seq, keep=True):
        """Remove nodes and/or edges (nodes take their edges with them).

        Removed elements are kept in ``g.deleted`` and can be restored with
        ``add``; pass keep=False (``removeComplete``) to discard them.
        """
        items = list(elements_of(seq))
        removed = GSet(annotation="removed")
        for x in items:
            if isinstance(x, Edge) and x._id in self._edges:
                self.removeEdge(x)
                removed.append(x)
        for x in items:
            if isinstance(x, Node) and self._nodes.get(x._name) is x:
                removed.extend(x._inc.values())
                self.removeNode(x)
                removed.append(x)
        if keep and removed:
            self._touch("deleted")
            for x in removed:
                self._deleted[(type(x).__name__, x._id)] = x
        return removed

    @property
    def deleted(self):
        return GSet(self._deleted.values(), "deleted")

    def add(self, seq):
        """Restore previously removed nodes/edges (see ``remove``)."""
        items = list(elements_of(seq))
        restored = GSet(annotation="restored")
        self._touch("deleted")
        j = self.journal
        for x in items:
            if isinstance(x, Node) and x._name not in self._nodes and x._g is self:
                self._nodes[x._name] = x
                self._node_ids[x._id] = x
                self._version += 1
                object.__setattr__(x, "_inc", {})
                self.removed_nodes.discard(x._id)
                self._mark(x)
                self._deleted.pop(("Node", x._id), None)
                if j is not None:
                    j.ops.append(("add", x))
                self._emit("on_node_added", x)
                restored.append(x)
        for x in items:
            if (isinstance(x, Edge) and x._id not in self._edges and x._g is self
                    and self._nodes.get(x._n1._name) is x._n1 and self._nodes.get(x._n2._name) is x._n2):
                self._edges[x._id] = x
                x._n1._inc[x._id] = x
                x._n2._inc[x._id] = x
                self._version += 1
                self.removed_edges.discard(x._id)
                self._mark(x)
                self._deleted.pop(("Edge", x._id), None)
                if j is not None:
                    j.ops.append(("add", x))
                restored.append(x)
        return restored

    def clear(self):
        """Empty the graph for a new one: every node and edge, and every field
        that isn't built in, so nothing of the old graph lingers. Computed
        fields that were in use (pagerank, ...) are computed again for the new
        graph once it is loaded (Session.scene). Undo restores all of it."""
        self._clearing = True
        try:
            for n in list(self._nodes.values()):
                self.removeNode(n)
        finally:
            self._clearing = False
        for schema in (self.node_schema, self.edge_schema):
            for name, f in reversed(list(schema.items())):     # so undo re-adds them in order
                if f.builtin:
                    continue
                del schema[name]
                if (f.kind, name) in self.lazy_fields:
                    self._dropped_lazy.add((f.kind, name))   # recomputed for the new graph
                if self.journal is not None:
                    self.journal.ops.append(("unfield", schema, name, f))
                self._emit("on_field_removed", f)
        self._touch("deleted")
        self._touch("bends")
        self._deleted.clear()
        self.bends.clear()
        self._emit("on_graph_cleared")

    def _visibility_cascade(self, elem, visible):
        """The visibility rules of the manual (§5), one step deep:
        hiding a node hides its edges; showing a node shows its edges to other
        visible nodes; showing an edge shows its endpoints."""
        def put(x, value):
            if bool(x._vals.get("visible", True)) == value:
                return
            if self.journal is not None:
                self.journal.note(x, "visible")
            x._vals["visible"] = value
            self._mark(x)
        if isinstance(elem, Node):
            for e in elem._inc.values():
                other = e.opposite(elem)
                if not visible:
                    put(e, False)
                elif other is elem or other._vals.get("visible", True):
                    put(e, True)
        elif visible:
            put(elem._n1, True)
            put(elem._n2, True)

    def __getattr__(self, name):
        # g.gemLayout(), g.colorize(…): every command is also a Graph method (compat.py)
        if not name.startswith("_"):
            look = self.__dict__.get("command_lookup")
            fn = look(name) if look else None
            if fn is not None:
                return fn
        raise AttributeError(f"'Graph' object has no attribute {name!r}")

    # undo ------------------------------------------------------------------
    def _touch(self, what):
        """Remember g._deleted / g.bends as they were before this command changed them."""
        j = self.journal
        if j is not None and getattr(j, what) is None:
            setattr(j, what, dict(self._deleted if what == "deleted" else self.bends))

    def _alive(self, x):
        if isinstance(x, Node):
            return self._nodes.get(x._name) is x
        return self._edges.get(x._id) is x

    def revert(self, j):
        """Undo the changes recorded in journal j; returns the journal of the
        reversal (reverting that one redoes)."""
        outer = self.journal
        inv = self.journal = Journal()
        try:
            for op in reversed(j.ops):
                kind, x = op[0], op[1]
                if kind == "add":
                    if self._alive(x):
                        (self.removeNode if isinstance(x, Node) else self.removeEdge)(x)
                elif kind == "rem":
                    if not self._alive(x):
                        self.add([x])
                elif kind == "field":
                    _k, schema, name, f = op
                    if schema.get(name) is f:
                        del schema[name]
                        inv.ops.append(("unfield", schema, name, f))
                        self._emit("on_field_removed", f)
                elif kind == "unfield":
                    _k, schema, name, f = op
                    if name not in schema:
                        schema[name] = f
                        inv.ops.append(("field", schema, name, f))
                        self._emit("on_field_added", f)
            for elem, name, old in j.values.values():
                inv.note(elem, name)
                if old is _UNSET:
                    elem._vals.pop(name, None)
                else:
                    elem._vals[name] = old
                if self._alive(elem):
                    if name in ("x", "y") and isinstance(elem, Node):
                        self.moved_nodes.add(elem._id)
                    else:
                        self._mark(elem)
            if j.deleted is not None:
                self._touch("deleted")
                self._deleted.clear()
                self._deleted.update(j.deleted)
            if j.bends is not None:
                self._touch("bends")
                for e in set(self.bends) | set(j.bends):
                    if self._alive(e):
                        self._mark(e)
                self.bends.clear()
                self.bends.update(j.bends)
        finally:
            self.journal = outer
        return inv

    def _resolve(self, n):
        if isinstance(n, Node):
            if self._nodes.get(n._name) is not n:
                raise GuessError(f"node {n._name} is not in the graph")
            return n
        node = self._nodes.get(str(n))
        if node is None:
            raise GuessError(f"no such node: {n!r}")
        return node

    # edge selection (Gython ->, <-, <->, ?) ---------------------------------
    def select_edges(self, op, a, b):
        left = [x for x in elements_of(a) if isinstance(x, Node)]
        right = [x for x in elements_of(b) if isinstance(x, Node)]
        right_ids = {id(x) for x in right}
        out = GSet(annotation=f"{_side(a)} {_OPSYM[op]} {_side(b)}")
        seen = set()
        for n in left:
            for e in n._inc.values():
                if e._id in seen:
                    continue
                if op == "dir":
                    ok = e._directed and e._n1 is n and id(e._n2) in right_ids
                elif op == "rdir":
                    ok = e._directed and e._n2 is n and id(e._n1) in right_ids
                elif op == "bi":
                    ok = (not e._directed) and id(e.opposite(n)) in right_ids
                else:  # any
                    ok = id(e.opposite(n)) in right_ids
                if ok:
                    seen.add(e._id)
                    out.append(e)
        if isinstance(a, Node) and isinstance(b, Node) and len(out) == 1:
            return out[0]
        return out


_OPSYM = {"dir": "->", "rdir": "<-", "bi": "<->", "any": "?"}


def _side(x):
    if isinstance(x, GSet) and x.annotation:
        return f"({x.annotation})"
    if isinstance(x, (Node, Edge)):
        return repr(x)
    return "(...)"


# --------------------------------------------------------------------------
# Grouping / sorting
# --------------------------------------------------------------------------

def _sort_key(v):
    # None sorts first; mixed types sort by type name then value
    if v is None:
        return (0, "", 0)
    if isinstance(v, (int, float)):
        return (1, "", v)
    return (2, type(v).__name__, str(v))


def sort_by(seq, field, descending=False):
    items = list(elements_of(seq))
    name = field.name if isinstance(field, Field) else str(field)
    items.sort(key=lambda e: _sort_key(getattr(e, name)), reverse=descending)
    return GSet(items, f"sorted by {name}")


def group_by(seq, field, sort=False):
    name = field.name if isinstance(field, Field) else str(field)
    groups = {}
    for e in elements_of(seq):
        v = getattr(e, name)
        groups.setdefault(v, []).append(e)
    keys = list(groups)
    if sort:
        keys.sort(key=_sort_key)
    return GSet((GSet(groups[k], f"{name} == {k!r}") for k in keys), f"grouped by {name}")
