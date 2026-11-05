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
            return [ggetattr(x, name) for x in o]
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


def gand(a, b):
    if _graphish(a) and _graphish(b):
        return GSet(elements_of(a)) & GSet(elements_of(b))
    return a & b


def gor(a, b):
    if _graphish(a) and _graphish(b):
        return GSet(elements_of(a)) | GSet(elements_of(b))
    return a | b


def gsub(a, b):
    """``a - b`` on nodes is the original GUESS edge operator: the undirected
    edges between a and b (same as ``a <-> b``). Use ``.difference()`` for sets."""
    if _graphish(a) and _graphish(b):
        return gop("bi", a, b)
    return a - b


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
    "__gsub__": gsub,
    "__autocall__": autocall,
}
