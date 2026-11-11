"""Runtime helpers that compiled Gython code calls (see compiler.py)."""
import operator

from .model import Edge, Field, GSet, GuessError, Node, _like_regex, elements_of

_AUG = {
    "Add": operator.add, "Sub": operator.sub, "Mult": operator.mul, "Div": operator.truediv,
    "FloorDiv": operator.floordiv, "Mod": operator.mod, "Pow": operator.pow,
    "BitAnd": operator.and_, "BitOr": operator.or_, "BitXor": operator.xor,
    "LShift": operator.lshift, "RShift": operator.rshift, "MatMult": operator.matmul,
}


def command(fn):
    """Mark a function as a GUESS command (callable without parentheses)."""
    fn._guess_command = True
    return fn


def _is_plain_seq(o):
    return isinstance(o, (tuple, list)) and not isinstance(o, GSet)


def _graph_of(*objs):
    for o in objs:
        for e in elements_of(o):
            return e._g
    return None


def gop(op, a, b):
    if op in ("dir", "rdir", "bi", "any"):
        g = _graph_of(a, b)
        if g is None:
            if not list(elements_of(a)) or not list(elements_of(b)):
                return GSet()
            raise GuessError(f"graph operator needs nodes on both sides, got {a!r} and {b!r}")
        return g.select_edges(op, a, b)
    if op == "like":
        if isinstance(a, Field):
            return a.like(b)
        if isinstance(a, str):
            return bool(_like_regex(str(b)).fullmatch(a))
        raise GuessError("'like' needs a field or string on the left")
    if op in ("roverlaps", "rcontains", "rexact", "rcontained"):
        from .ranges import query
        return query(a, op, b)
    raise GuessError(f"unknown operator {op!r}")


def ggetattr(o, name):
    try:
        return getattr(o, name)
    except AttributeError:
        if _is_plain_seq(o) and o:
            from .model import Values
            return Values(ggetattr(x, name) for x in o)
        raise


def gsetattr(o, name, value):
    if _is_plain_seq(o):
        for x in o:
            gsetattr(x, name, value)
    else:
        setattr(o, name, value)


def gaugattr(o, name, opname, value):
    op = _AUG[opname]
    if _is_plain_seq(o):
        for x in o:
            gaugattr(x, name, opname, value)
    elif isinstance(o, GSet):
        for x in o:
            gaugattr(x, name, opname, value)
    else:
        setattr(o, name, op(getattr(o, name), value))


def _graphish(o):
    if isinstance(o, (Node, Edge, GSet)):
        return True
    if isinstance(o, (tuple, list)):
        return any(isinstance(x, (Node, Edge, GSet, tuple, list)) for x in o)
    return False


def _precedence_hint(a, b, sym):
    """`dept == "x" & degree > 3` parses as dept == ("x" & degree) > 3."""
    if isinstance(a, Field) or isinstance(b, Field):
        f = a if isinstance(a, Field) else b
        raise GuessError(f"'{sym}' binds tighter than comparisons: put each query in parentheses, "
                         f"e.g. ({f.name} == ...) {sym} (...)")


def _label(a, b, sym):
    la, lb = getattr(a, "annotation", None), getattr(b, "annotation", None)
    if la and lb:
        return f"({la}) {sym} ({lb})"
    return None


def gand(a, b):
    if _graphish(a) and _graphish(b):
        return GSet(GSet(elements_of(a)) & GSet(elements_of(b)), annotation=_label(a, b, "&"))
    _precedence_hint(a, b, "&")
    return a & b


def gor(a, b):
    if _graphish(a) and _graphish(b):
        return GSet(GSet(elements_of(a)) | GSet(elements_of(b)), annotation=_label(a, b, "|"))
    _precedence_hint(a, b, "|")
    return a | b


_CMP = {
    "Eq": operator.eq, "NotEq": operator.ne, "Lt": operator.lt, "LtE": operator.le,
    "Gt": operator.gt, "GtE": operator.ge, "Is": operator.is_, "IsNot": operator.is_not,
    "In": lambda a, b: gin(a, b, False), "NotIn": lambda a, b: gin(a, b, True),
}


def gchain(first, *pairs):
    """``3 < degree < 6``: Python would compute ``(3 < degree) and (degree < 6)``,
    which for query sets is just the second set. Query sets intersect instead;
    plain values compare (and short-circuit) as usual."""
    prev, acc, r = first, None, True
    for opname, thunk in pairs:
        b = thunk()
        r = _CMP[opname](prev, b)
        if isinstance(r, GSet):
            acc = r if acc is None else gand(acc, r)
        elif not r:
            return GSet() if acc is not None else r
        prev = b
    return acc if acc is not None else r


def gin(a, b, negate=False):
    """``degree in (1, 2)``: the elements whose value is one of those."""
    if isinstance(a, Field):
        q = a.isin(b)
        if negate:
            keep = set(map(id, q))
            q = GSet((e for e in a.elements() if id(e) not in keep),
                     annotation=f"{a.name} not in {list(b) if not isinstance(b, str) else b!r}")
        return q
    return (a not in b) if negate else (a in b)


def gbool(op, first, *thunks):
    """``a and b`` / ``a or b`` used as a value: on two query sets, their
    intersection / union (Python would give one of the two sets)."""
    v = first
    for t in thunks:
        if isinstance(v, GSet):
            w = t()
            if isinstance(w, GSet):
                v = gand(v, w) if op == "and" else gor(v, w)
            elif op == "and":
                v = w if v else v
            else:
                v = v if v else w
            continue
        if (op == "and" and not v) or (op == "or" and v):
            return v
        v = t()
    return v


def gsub(a, b):
    """``a - b`` on nodes is the original GUESS edge operator: the undirected
    edges between a and b (same as ``a <-> b``). Use ``.difference()`` or
    ``not`` for sets."""
    if _graphish(a) and _graphish(b):
        out = gop("bi", a, b)
        if isinstance(out, GSet) and not isinstance(a, (Node, Edge)):     # a single edge stays itself
            out.annotation = "edges between (a - b is a <-> b; for a set difference: a.difference(b))"
        return out
    return a - b


def gisub(a, b):
    """``a -= b``: as ``a = a - b`` between node sets, otherwise Python's ``-=``."""
    if _graphish(a) and _graphish(b):
        return gsub(a, b)
    a -= b
    return a


def autocall(x):
    if callable(x) and getattr(x, "_guess_command", False):
        return x()
    return x


HELPERS = {
    "__gop__": gop,
    "__ggetattr__": ggetattr,
    "__gsetattr__": gsetattr,
    "__gaugattr__": gaugattr,
    "__gand__": gand,
    "__gor__": gor,
    "__gchain__": gchain,
    "__gin__": gin,
    "__gbool__": gbool,
    "__gsub__": gsub,
    "__gisub__": gisub,
    "__autocall__": autocall,
}
