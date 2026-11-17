"""Output formats: how the console shows a value.

Every value shown in the console (a top-level expression, print(), show())
goes through render(). It works out the value's *kind* (a node, a set of
nodes, a set of groups, ...) and the format chosen for it:

  1. the one given for this value      x >> table, show(x, "summary")
  2. the one set for the command       setFormat("louvainClusters", table)
  3. the one set for the kind          setFormat("groups", table)
  4. the default ("list": the linked output GUESS has always printed)

A format is a function from a value to output segments (or None to pass the
value on to the default). Users can register their own: a function taking the
value and returning something printable (strings, nodes, lists, ...), which is
then shown linked as usual.
"""
from .model import DistinctValues, Edge, Field, GSet, GuessError, Node

KINDS = {
    "node": "a node (v4)",
    "edge": "an edge (v4-v7)",
    "set": "a set or list of nodes/edges (dept == 'dept1')",
    "groups": "a set of groups (groupBy(dept), louvainClusters())",
    "values": "the distinct values of a field (dept.values)",
    "fieldvalue": "one element's field value (v4.dept)",
    "dict": "a dict holding nodes/edges",
    "other": "anything else",
}

TABLE_ROWS = 500          # rows sent to the page (the rest are linked, not shown)


class Format:
    """An output format. Call it with options to get a configured copy
    (table(degree, dept), table(sort=degree)); put it after >> to show a
    value with it (louvainClusters() >> table)."""

    def __init__(self, name, fn, doc="", opts=None, kinds=None):
        self.name, self.fn, self.doc = name, fn, doc
        self.opts = dict(opts or {})
        self.kinds = kinds         # kinds it handles (None: any)

    def __call__(self, *fields, **opts):
        if fields:
            opts["fields"] = list(fields) + list(opts.get("fields") or [])
        return Format(self.name, self.fn, self.doc, {**self.opts, **opts}, self.kinds)

    def __rrshift__(self, value):
        return Formatted(value, self)

    def render(self, ctx):
        return self.fn(ctx, **self.opts)

    def __repr__(self):
        extra = ", ".join(f"{k}={_opt_repr(v)}" for k, v in self.opts.items())
        return f"<format {self.name}{'(' + extra + ')' if extra else ''}>"


def _opt_repr(v):
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_opt_repr(x) for x in v) + "]"
    return v.name if isinstance(v, Field) else repr(v)


class Formatted:
    """A value paired with the format to show it in (what x >> table gives)."""

    def __init__(self, value, fmt):
        self.value, self.fmt = value, fmt

    def __repr__(self):
        return plain_text(self.value)


class Ctx:
    """What a format gets: the value, its kind, the command it came from and,
    for a field value (v4.dept), the element and field it was read from."""

    def __init__(self, value, kind, origin=None, obj=None, attr=None):
        self.value, self.kind, self.origin, self.obj, self.attr = value, kind, origin, obj, attr


# ---- kinds -------------------------------------------------------------------

def _is_group(x):
    return (isinstance(x, (GSet, list)) and not isinstance(x, DistinctValues)
            and all(isinstance(y, (Node, Edge)) for y in x))


def kind_of(value):
    from .session import _contains_elements
    if isinstance(value, Node):
        return "node"
    if isinstance(value, Edge):
        return "edge"
    if isinstance(value, DistinctValues) and value.name and value.source is not None and value:
        return "values"
    if isinstance(value, (GSet, list, tuple, set, frozenset)) and _contains_elements(value):
        if isinstance(value, (GSet, list)) and value and all(_is_group(x) and x for x in value):
            return "groups"
        return "set"
    if isinstance(value, dict) and _contains_elements(value):
        return "dict"
    return "other"


# ---- resolution ----------------------------------------------------------------

def as_format(session, f):
    """A Format for f (a Format, a format's name, list, the table command or a
    user function), or None if f isn't one."""
    if isinstance(f, Format):
        return f
    if f is list:
        return session.out_formats["list"]
    if isinstance(f, str):
        return session.out_formats.get(f)
    name = getattr(f, "_guess_format", None)
    if name:
        return session.out_formats.get(name)
    return None


def to_format(session, f):
    fmt = as_format(session, f)
    if fmt is not None:
        return fmt
    if callable(f):
        return custom(f)
    names = ", ".join(sorted(session.out_formats))
    raise GuessError(f"{f!r} is not an output format (formats: {names}, or a function)")


def custom(fn):
    """A format from a user function: fn(value) returns what to show (shown
    linked as usual); returning None falls back to the default."""
    def render(ctx):
        out = fn(ctx.value)
        if out is None:
            return None
        if isinstance(out, str):
            return out                    # text as it is (no quotes)
        if isinstance(out, Formatted):
            return render_value(_session, out.value, fmt=out.fmt)
        return _segment(out)
    name = getattr(fn, "__name__", "custom")
    return Format(name, render, (fn.__doc__ or "").strip())


_session = None   # set by install() (custom formats render through it)


def render(session, value, origin=None, fmt=None, obj=None, attr=None):
    """The output segment for value (see the module docstring)."""
    scalar = isinstance(value, (str, int, float, bool))
    kind = "fieldvalue" if obj is not None and scalar else kind_of(value)
    if kind != "fieldvalue":
        obj = attr = None
    ctx = Ctx(value, kind, origin, obj, attr)
    chosen = [fmt, session.out_settings.get(origin) if origin else None, session.out_settings.get(kind)]
    for f in chosen:
        if f is None or (f.kinds and kind not in f.kinds):
            continue
        seg = f.render(ctx)
        if seg is not None:
            return seg
    return default(ctx)


def render_value(session, value, fmt=None):
    return render(session, value, fmt=fmt)


def _segment(value, *a):
    from .session import segment
    return segment(value, *a)


def default(ctx, **_):
    if ctx.kind == "fieldvalue":
        from .session import _value_seg
        seg = _value_seg(ctx.obj, ctx.attr, ctx.value)
        if seg is not None:
            return seg
    return _segment(ctx.value)


# ---- built-in formats ----------------------------------------------------------

def _all(value):
    from .session import _all_items
    if isinstance(value, DistinctValues) and value.source is not None:
        return _all_items(list(value.source))     # the elements the values came from
    return _all_items(value)


def _ann(value):
    a = value.__dict__.get("annotation") if isinstance(value, GSet) else None
    return a if isinstance(a, str) else None


def folded(ctx, **_):
    if ctx.kind == "groups":
        from .session import _compact_groups
        return _compact_groups(ctx.value)
    if ctx.kind in ("set", "dict", "values"):
        seg = _segment(ctx.value)
        if isinstance(seg, dict) and "g" in seg:
            seg["c"] = 1
        return seg
    return None


def _count_words(items):
    nodes = sum(1 for x in items if isinstance(x, Node))
    edges = sum(1 for x in items if isinstance(x, Edge))
    other = len(items) - nodes - edges
    parts = []
    if nodes:
        parts.append(f"{nodes} node{'s' * (nodes != 1)}")
    if edges:
        parts.append(f"{edges} edge{'s' * (edges != 1)}")
    if other:
        parts.append(f"{other} other")
    return ", ".join(parts) or "empty"


def summary(ctx, **_):
    v, kind = ctx.value, ctx.kind
    ann = _ann(v)
    if kind == "set":
        text = _count_words(list(v))
    elif kind == "groups":
        sizes = [len(x) for x in v]
        text = f"{len(v)} groups, sizes {min(sizes)}–{max(sizes)}" if min(sizes) != max(sizes) \
            else f"{len(v)} groups of {sizes[0]}"
        text += f" ({_count_words([y for x in v for y in x])})"
    elif kind == "values":
        text = f"{len(v)} values of {v.name}"
    elif kind == "dict":
        text = f"{len(v)} entries"
    else:
        return None
    if ann:
        text = f"{ann}: {text}"
    return {"g": [text], "a": ann or text, "x": _all(v)}


def count(ctx, **_):
    v = ctx.value
    if ctx.kind not in ("set", "groups", "values", "dict"):
        return None
    out = {"g": [str(len(v))], "a": _ann(v) or f"{len(v)} items", "x": _all(v)}
    return out


def plain_text(v, depth=0):
    """The value as unlinked text: names, not reprs (v1, v2, v3)."""
    if isinstance(v, Node):
        return v._name
    if isinstance(v, Edge):
        return repr(v)
    if isinstance(v, Formatted):
        return plain_text(v.value, depth)
    if depth < 20 and isinstance(v, dict):
        return ", ".join(f"{plain_text(k, depth + 1)}: {plain_text(x, depth + 1)}" for k, x in v.items())
    if depth < 20 and isinstance(v, (GSet, list, tuple, set, frozenset)):
        if v and all(_is_group(x) for x in v):
            from .session import _group_label
            lines = []
            for i, grp in enumerate(v):
                lab = _group_label(grp, inner=True) or str(i)
                lines.append(f"{lab}: {plain_text(grp, depth + 1)}")
            return "\n".join(lines)
        inner = ", ".join(plain_text(x, depth + 1) for x in v)
        return f"[{inner}]" if depth else inner
    if isinstance(v, str):
        return v
    from .session import _safe_repr
    return _safe_repr(v)


def plain(ctx, **_):
    return plain_text(ctx.value)


def _field_name(f):
    if isinstance(f, Field):
        return f.name
    if isinstance(f, str):
        return f
    raise GuessError(f"table: {f!r} is not a field (use a field like degree, or its name)")


def _read(x, name):
    if name == "name" and isinstance(x, Node):
        return x._name
    try:
        from .runtime import ggetattr
        return ggetattr(x, name)
    except Exception:  # noqa: BLE001
        return None


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (Node, Edge)):
        return _segment(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, str):
        from .session import _color_seg
        cs = _color_seg(v)
        if cs is not None:
            cs["t"] = str(v)
        return cs or v
    from .session import _contains_elements
    if isinstance(v, (list, tuple, set, frozenset, dict, GSet)) and _contains_elements(v):
        return _segment(v, 1)
    from .session import _safe_repr
    return _safe_repr(v)


def _sort_key(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0, v, "")
    return (1, 0, str(v))


def _query_fields(ann, schema):
    """Fields named in a query (degree > 3 and dept == 'x' -> degree, dept)."""
    import re
    if not ann:
        return []
    words = re.findall(r"(?<!['\"\w.])([A-Za-z_]\w*)", re.sub(r"'[^']*'|\"[^\"]*\"", "", ann))
    out = []
    for w in words:
        if w in schema and w not in out and w != "name":
            out.append(w)
    return out


def _sorted_rows(rows, keys, sort, reverse):
    if sort is None:
        return rows
    return [r for _, r in sorted(zip(keys, rows), key=lambda kr: _sort_key(kr[0]), reverse=reverse)]


def _table(cols, rows, ann=None, rest=()):
    out: dict = {"tbl": {"cols": cols, "rows": rows}}
    if ann:
        out["a"] = ann
    if rest:
        from .session import _all_items
        out["x"] = _all_items(list(rest))
    return out


def table(ctx, fields=None, sort=None, reverse=None, rows=TABLE_ROWS, **_):
    v, kind = ctx.value, ctx.kind
    sort_name = _field_name(sort) if sort is not None else None
    if kind == "groups":
        from .session import GROUP_SHOWN, _group_label
        recs = []
        for i, grp in enumerate(v):
            lab = _group_label(grp, inner=True) or str(i)
            members = _segment(list(grp), 1, GROUP_SHOWN)
            if isinstance(members, dict):
                members["c"] = 1
                a = _ann(grp)
                if a:
                    members["a"] = a
            key = lab if sort_name == "label" else len(grp)
            recs.append((key, [lab, str(len(grp)), members], grp))
        if sort_name:
            recs.sort(key=lambda r: _sort_key(r[0]), reverse=True if reverse is None else reverse)
        rest = [y for _, _, grp in recs[rows:] for y in grp]
        return _table(["label", "size", "members"], [r[1] for r in recs[:rows]], ann=_ann(v), rest=rest)
    if kind == "values":
        groups = v.groups()
        recs = []
        for val in v:
            try:
                members = groups.get(val, [])
            except TypeError:
                members = []
            q = f"{v.name} == {val!r}"
            seg = {"g": [_cell(val)], "a": q if v.whole else f"{q} (in the set)",
                   "x": [["n" if isinstance(x, Node) else "e", x._id] for x in members]}
            if v.whole:
                seg["q"] = q
            recs.append((len(members) if sort_name in ("count", "size") else val, [seg, str(len(members))]))
        recs = _sorted_rows([r for _, r in recs], [k for k, _ in recs], sort_name,
                            True if reverse is None and sort_name in ("count", "size") else bool(reverse))
        return _table([v.name, "count"], recs[:rows], ann=f"{len(v)} values of {v.name}")
    if kind == "dict":
        items = list(v.items())
        rws = [[_cell(k), _cell(x)] for k, x in items]
        if sort_name in ("key", "value"):
            keys = [k if sort_name == "key" else x for k, x in items]
            rws = _sorted_rows(rws, keys, sort_name, bool(reverse) if reverse is not None else sort_name == "value")
        return _table(["key", "value"], rws[:rows])
    if kind in ("node", "edge"):
        g = v._g
        schema = g.node_schema if kind == "node" else g.edge_schema
        names = [_field_name(f) for f in fields] if fields else [n for n in schema if not n.startswith("_")]
        return _table(["field", "value"], [[n, _cell(_read(v, n))] for n in names])
    if kind == "set":
        items = list(v)
        els = [x for x in items if isinstance(x, (Node, Edge))]
        if not els:
            return None
        g = els[0]._g
        is_node = isinstance(els[0], Node)
        schema = g.node_schema if is_node else g.edge_schema
        if fields:
            names = [_field_name(f) for f in fields]
        else:
            names = _query_fields(_ann(v), schema)
            if not names:
                names = ["degree"] if is_node else (["weight"] if "weight" in schema else [])
        first = "node" if is_node else "edge"
        rws, keys = [], []
        for x in items:
            rws.append([_cell(x)] + [_cell(_read(x, n)) for n in names])
            keys.append(_read(x, sort_name) if sort_name else None)
        if sort_name:
            rws = _sorted_rows(rws, keys, sort_name, True if reverse is None else reverse)
        rest = items[rows:]
        return _table([first] + names, rws[:rows], ann=_ann(v), rest=rest)
    return None


BUILTIN = [
    ("list", default, "the linked output GUESS prints by default ([v1, v2, …])", None),
    ("folded", folded, "lists start folded ([v1, … +27 more]); one folded list per group", None),
    ("table", table, "a table: a row per element (fields as columns: table(degree, dept), "
                     "sort=degree, reverse=False), a row per group (label, size, members), "
                     "a row per value (value, count) or a node's fields", None),
    ("summary", summary, "a one-line summary (12 nodes; 21 groups, sizes 3–28), linked to the elements", None),
    ("count", count, "just how many, linked to the elements", None),
    ("plain", plain, "unlinked text, easy to copy (v1, v2, v3; a line per group)", None),
]


# ---- commands --------------------------------------------------------------------

def gpipe(session, a, b):
    """``a >> b``: a value shown in a format (louvainClusters() >> table);
    otherwise Python's >>."""
    fmt = as_format(session, b)
    if fmt is None and callable(b) and not isinstance(b, type) and not hasattr(type(b), "__rrshift__"):
        fmt = custom(b)                    # x >> myFormat: a user function as a format
    if fmt is None:
        return a >> b
    from .runtime import autocall
    return Formatted(autocall(a), fmt)


def install(session):
    global _session
    _session = session
    session.out_formats = {name: Format(name, fn, doc, kinds=kinds) for name, fn, doc, kinds in BUILTIN}
    session.out_settings = {}

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    # plain names, not system ones, so scripts can still use count = 0
    for name in ("folded", "summary", "count", "plain"):
        session.ns[name] = session.out_formats[name]
    session.ns["__gpipe__"] = lambda a, b: gpipe(session, a, b)

    def target_name(target):
        if isinstance(target, str):
            return target
        name = getattr(target, "__name__", None)
        if name:
            return name
        raise GuessError(f"setFormat: {target!r} is not a kind or a command (kinds: {', '.join(KINDS)})")

    def showAs(value, format="list"):
        """showAs(value, format) prints value in an output format, as value >> format
        does: showAs(louvainClusters(), table), showAs(sel, "summary"). Formats: list,
        folded, table, summary, count, plain (see formats())."""
        session.display(Formatted(value, to_format(session, format)))

    def setFormat(target, format=None):
        """setFormat(kind, format) shows every value of that kind in format from now
        on: setFormat("groups", table), setFormat("set", summary). The kind can
        instead be a command, for just its results: setFormat(louvainClusters, table).
        Kinds: node, edge, set, groups, values, fieldvalue, dict, other. format can
        be a function: it gets the value and returns what to show.
        setFormat(kind) (or format None) goes back to the default."""
        name = target_name(target)
        if format is None or as_format(session, format) is session.out_formats["list"]:
            session.out_settings.pop(name, None)
            return
        if name not in KINDS and not callable(session.ns.get(name)):
            raise GuessError(f"setFormat: {name!r} is not a kind or a command (kinds: {', '.join(KINDS)})")
        session.out_settings[name] = to_format(session, format)

    def resetFormats():
        """resetFormats() goes back to the default output for everything."""
        session.out_settings.clear()

    def formats():
        """formats() lists the kinds of values, the format each is shown in, and
        the formats there are (see setFormat, showAs and value >> format)."""
        rows = [[k, KINDS[k], _fmt_name(session.out_settings.get(k))] for k in KINDS]
        rows += [[k, "results of " + k, _fmt_name(f)] for k, f in session.out_settings.items() if k not in KINDS]
        fm = [[name, f.doc] for name, f in session.out_formats.items()]
        session.emit({"type": "out", "segs": [_table(["kind", "what", "format"], rows)], "gid": session.graph_gen})
        session.emit({"type": "out", "segs": [_table(["format", "shows"], fm)], "gid": session.graph_gen})

    for fn in (showAs, setFormat, resetFormats, formats):
        cmd(fn)


def _fmt_name(f):
    return "list" if f is None else repr(f)[len("<format "):-1]
