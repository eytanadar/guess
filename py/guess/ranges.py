"""Range (existence-interval) queries.

A range is written "1,5-10,20": time 1, the period 5..10 inclusive, and 20.
Ranges are attached to nodes/edges with addRange(obj, "..."), or kept in any
string field. Queries:

    Node rcontains 5          nodes that exist at time 5
    Edge roverlaps (4, 6)     edges existing at some point in 4..6
    g rcontained "0-10"       nodes and edges that only exist within 0..10
    span rexact "1,3"         elements whose `span` field is exactly 1 and 3
    searchContains("5")       all nodes and edges existing at 5
"""
from .model import EDGE, NODE, Edge, Field, FieldNamespace, Graph, GSet, GuessError, Node, elements_of


def parse(spec):
    """Return sorted, merged [(lo, hi), ...] for a range spec."""
    if spec is None:
        return []
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return [(float(spec), float(spec))]
    if isinstance(spec, tuple) and len(spec) == 2 and all(isinstance(v, (int, float)) for v in spec):
        lo, hi = sorted(map(float, spec))
        return [(lo, hi)]
    if isinstance(spec, (list, tuple)):
        out = []
        for part in spec:
            out += parse(part)
        return _merge(out)
    out = []
    for part in str(spec).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part[1:]:
                k = part.index("-", 1)
                lo, hi = float(part[:k]), float(part[k + 1:])
                out.append((min(lo, hi), max(lo, hi)))
            else:
                out.append((float(part), float(part)))
        except ValueError:
            raise GuessError(f"bad range {spec!r}: use e.g. \"1,5-10,20\"") from None
    return _merge(out)


def _merge(iv):
    iv = sorted(iv)
    out = []
    for lo, hi in iv:
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _inside(inner, outer):
    return all(any(o[0] <= i[0] and i[1] <= o[1] for o in outer) for i in inner)


def _overlaps(a, b):
    return any(x[0] <= y[1] and y[0] <= x[1] for x in a for y in b)


TESTS = {
    "rcontains": lambda elem, q: bool(q) and _inside(q, elem),
    "roverlaps": lambda elem, q: _overlaps(elem, q),
    "rcontained": lambda elem, q: bool(elem) and _inside(elem, q),
    "rexact": lambda elem, q: elem == q,
}


def fmt(iv):
    return ",".join(f"{_n(lo)}" if lo == hi else f"{_n(lo)}-{_n(hi)}" for lo, hi in iv)


def _n(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def query(lhs, op, spec):
    q = parse(spec)
    test = TESTS[op]
    out = GSet(annotation=f"{lhs!r} {op} {spec!r}")
    if isinstance(lhs, Field):
        for e in lhs.elements():
            if test(parse(lhs.get(e)), q):
                out.append(e)
        return out
    if isinstance(lhs, FieldNamespace):
        graph, kinds = lhs._graph, {lhs._kind}
    elif isinstance(lhs, Graph):
        graph, kinds = lhs, {NODE, EDGE}
    else:
        items = list(elements_of(lhs))
        if not items:
            return out
        graph = items[0]._g
        for e in items:
            if test(graph.ranges.get(e, []), q):
                out.append(e)
        return out
    for e, iv in graph.ranges.items():
        kind = NODE if isinstance(e, Node) else EDGE
        if kind in kinds and _alive(graph, e) and test(iv, q):
            out.append(e)
    return out


def _alive(graph, e):
    if isinstance(e, Node):
        return graph._nodes.get(e._name) is e
    return e._id in graph._edges


def install(session):
    g = session.graph
    g.ranges = {}

    def addRange(obj, spec):
        """Attach an existence range like "1,5-10,20" to nodes/edges (adds to any existing range)."""
        iv = parse(spec)
        for e in elements_of(obj):
            if isinstance(e, (Node, Edge)):
                g.ranges[e] = _merge(g.ranges.get(e, []) + iv)

    def getRange(obj):
        """The range of a node or edge as a string."""
        return fmt(g.ranges.get(obj, []))

    def mk(op, name, doc):
        def fn(spec):
            return query(g, op, spec)
        fn.__name__ = name
        fn.__doc__ = doc
        session.register_command(name, fn)

    session.register_command("addRange", addRange)
    session.register_command("getRange", getRange)
    mk("rcontains", "searchContains", "Nodes and edges whose range contains the given range.")
    mk("roverlaps", "searchOverlap", "Nodes and edges whose range overlaps the given range.")
    mk("rcontained", "searchContained", "Nodes and edges whose range lies inside the given range.")
    mk("rexact", "searchExact", "Nodes and edges whose range equals the given range.")
