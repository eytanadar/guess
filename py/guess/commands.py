"""Global GUESS commands (the equivalents of scripts/Main.py wrappers)."""
import inspect
import math
import os
import random

from . import colors, formats, gdf, gexf
from .model import EDGE, NODE, Edge, Field, GSet, GuessError, Node, elements_of, group_by, sort_by


def install(session):
    g = session.graph

    def cmd(fn, name=None):
        session.register_command(name or fn.__name__, fn)
        return fn

    # ---- loading / saving ------------------------------------------------
    def _load(filename, reader, label):
        with open(filename, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        g.clear()
        nn, ne = reader(g, text)
        session.scene()
        print(f"loaded {nn} nodes, {ne} edges from {os.path.basename(filename)} ({label})")

    @cmd
    def makeFromGDF(filename):
        """Replace the current graph with the contents of a GDF file."""
        _load(filename, gdf.read, "GDF")

    @cmd
    def makeFromPajek(filename):
        """Replace the current graph with a Pajek .net file (nodes are named pajek<id>)."""
        _load(filename, formats.read_pajek, "Pajek")

    @cmd
    def makeFromGML(filename):
        """Replace the current graph with a GraphML file."""
        _load(filename, formats.read_graphml, "GraphML")

    cmd(makeFromGML, "makeFromGraphML")

    @cmd
    def makeFromDL(filename):
        """Replace the current graph with a UCINET DL file (fullmatrix, edgelist1, nodelist1)."""
        _load(filename, formats.read_dl, "DL")

    @cmd
    def makeFromGEXF(filename):
        """Replace the current graph with a GEXF file (Gephi's format): attributes,
        colours, positions, sizes, edge weights and thickness."""
        _load(filename, gexf.read_gexf, "GEXF")

    @cmd
    def makeFromCSV(filename, nodes=None, directed=False):
        """makeFromCSV("edges.csv") replaces the graph with a spreadsheet table as
        Gephi reads it: an edge table (Source, Target[, Type, Weight, Label, ...]),
        an adjacency matrix or an adjacency list. makeFromCSV("edges.csv",
        "nodes.csv") also reads a node table (Id[, Label, ...]). Opening just a node
        table adds its columns to the current graph's nodes (matched by Id).
        Other columns become fields; directed=true makes edges without a Type
        directed."""
        def read(name):
            with open(name, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        text = read(filename)
        kind, _rows = gexf.table_kind(text)
        if kind == "nodes" and nodes is None and len(g._nodes):
            _k, added, _ne = gexf.read_csv(g, text)
            session.scene()
            print(f"node table {os.path.basename(filename)}: {added} new nodes, "
                  f"{len(g._nodes) - added} updated")
            return
        g.clear()
        kind, nn, ne = gexf.read_csv(g, text, bool(directed))
        if nodes is not None:
            _k, more, _ = gexf.read_csv(g, read(nodes))
            nn += more
        session.scene()
        print(f"loaded {len(g._nodes)} nodes, {ne} edges from {os.path.basename(filename)} "
              f"(CSV {'edge table' if kind == 'edges' else 'adjacency ' + kind if kind in ('matrix', 'list') else kind})")

    def _offer(filename, text):
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(text)
        session.emit({"type": "download", "name": os.path.basename(filename), "text": text})

    @cmd
    def exportGEXF(filename="graph.gexf"):
        """Write the graph as GEXF 1.3 for Gephi (offered as a download)."""
        _offer(filename, gexf.write_gexf(g))

    @cmd
    def exportCSV(filename="edges.csv", table="edges"):
        """exportCSV("edges.csv") writes the edge table (Source, Target, Type, Weight,
        Label and edge fields); exportCSV("nodes.csv", "nodes") the node table."""
        if table not in ("edges", "nodes"):
            raise GuessError('table is "edges" or "nodes"')
        _offer(filename, gexf.write_csv(g, table))

    @cmd
    def exportGraphML(filename):
        """Write the graph as GraphML (offered as a download in the browser)."""
        text = formats.write_graphml(g)
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(text)
        session.emit({"type": "download", "name": os.path.basename(filename), "text": text})

    @cmd
    def exportGDF(filename):
        """Write the graph to a GDF file (offered as a download in the browser)."""
        text = gdf.write(g)
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(text)
        session.emit({"type": "download", "name": os.path.basename(filename), "text": text})

    @cmd
    def execfile(filename):
        """Run a Gython script file in the current namespace."""
        with open(filename, encoding="utf-8") as fh:
            src = fh.read()
        from . import compiler
        names = set()
        code = compiler.compile_gython(src, is_protected=session.is_protected,
                                       interactive=False, filename=filename, names=names)
        session._prepare_fields(names)
        exec(code, session.ns)

    # ---- structure -----------------------------------------------------------
    @cmd
    def addNode(name, **attrs):
        """Add a node (or return the existing one with that name)."""
        return g.addNode(name, **attrs)

    @cmd
    def addEdge(node1, node2, **attrs):
        """Add an undirected edge."""
        return g.addEdge(node1, node2, False, **attrs)

    @cmd
    def addUndirectedEdge(node1, node2, **attrs):
        return g.addEdge(node1, node2, False, **attrs)

    @cmd
    def addDirectedEdge(node1, node2, **attrs):
        return g.addEdge(node1, node2, True, **attrs)

    @cmd
    def remove(seq):
        """Remove nodes and/or edges (a node takes its edges). Undo with add(...)."""
        return g.remove(seq)

    @cmd
    def removeComplete(seq):
        """Remove nodes and/or edges permanently (they cannot be re-added)."""
        return g.remove(seq, keep=False)

    @cmd
    def add(seq):
        """Re-add removed nodes/edges, e.g. add(g.deleted)."""
        return g.add(seq)

    @cmd
    def removeNode(n):
        return g.removeNode(n)

    @cmd
    def removeEdge(e):
        return g.removeEdge(e)

    @cmd
    def addNodeField(fieldName, sqlType="VARCHAR", defaultValue=None):
        """Create a node field, e.g. addNodeField("score", DOUBLE, 0)."""
        return g.addNodeField(fieldName, sqlType, defaultValue)

    @cmd
    def addEdgeField(fieldName, sqlType="VARCHAR", defaultValue=None):
        """Create an edge field, e.g. addEdgeField("kind", VARCHAR, "")."""
        return g.addEdgeField(fieldName, sqlType, defaultValue)

    @cmd
    def removeSelfLoops():
        """Remove (and return) all edges whose endpoints are the same node."""
        return g.remove(GSet((e for e in g._edges_list() if e._n1 is e._n2), "self loops"))

    @cmd
    def removeDisconnected():
        """Remove (and return) nodes with no edges other than self loops."""
        lonely = GSet((n for n in g._nodes_list()
                       if all(e._n1 is e._n2 for e in n._inc.values())), "disconnected")
        return g.remove(lonely)

    @cmd
    def hideDisconnected():
        """Hide nodes with no edges other than self loops."""
        for n in g._nodes_list():
            if all(e._n1 is e._n2 for e in n._inc.values()):
                n.visible = False

    @cmd
    def removeLeaves():
        """Repeatedly remove nodes of total degree <= 1. Returns what was removed."""
        out = GSet(annotation="leaves")
        while True:
            leaves = [n for n in g._nodes_list() if len(n._inc) <= 1]
            if not leaves:
                return out
            out.extend(g.remove(leaves))

    @cmd
    def shortcutNodes():
        """Repeatedly replace degree-2 nodes by an edge between their neighbours.
        Returns [removed, added]."""
        removed, added = GSet(annotation="removed"), GSet(annotation="added")
        while True:
            cands = [n for n in g._nodes_list() if len(n._inc) == 2]
            changed = False
            for z in cands:
                if g._nodes.get(z._name) is not z or len(z._inc) != 2:
                    continue
                nbrs = z.getNeighbors()
                if len(nbrs) == 2:
                    a, b = nbrs
                    if not _connected(a, b):
                        added.append(g.addEdge(a, b))
                    removed.extend(g.remove(z))
                    changed = True
            if not changed:
                break
        return GSet([_minus(removed, added), _minus(added, removed)])

    @cmd
    def condenseGraph():
        """removeDisconnected, removeSelfLoops, then alternate removeLeaves and
        shortcutNodes until nothing changes. Returns [removed, added]."""
        removed, added = GSet(), GSet()
        removed.extend(removeDisconnected())
        removed.extend(removeSelfLoops())
        while any(len(n._inc) <= 2 for n in g._nodes_list()):
            before = (len(g._nodes), len(g._edges))
            removed.extend(removeLeaves())
            r, a = shortcutNodes()
            removed.extend(r)
            added.extend(a)
            if (len(g._nodes), len(g._edges)) == before:
                break
        return GSet([_minus(removed, added), _minus(added, removed)])

    @cmd
    def complement(seq):
        """Everything (nodes if seq has nodes, edges if it has edges) not in seq."""
        items = list(elements_of(seq))
        ids = {id(x) for x in items}
        out = GSet(annotation="complement")
        if any(isinstance(x, Node) for x in items) or isinstance(seq, Node):
            out.extend(n for n in g._nodes_list() if id(n) not in ids)
        if any(isinstance(x, Edge) for x in items) or isinstance(seq, Edge):
            out.extend(e for e in g._edges_list() if id(e) not in ids)
        return out

    @cmd
    def ninverse(seq):
        """All nodes not in seq."""
        ids = {id(x) for x in elements_of(seq)}
        return GSet((n for n in g._nodes_list() if id(n) not in ids), "node inverse")

    @cmd
    def einverse(seq):
        """All edges not in seq."""
        ids = {id(x) for x in elements_of(seq)}
        return GSet((e for e in g._edges_list() if id(e) not in ids), "edge inverse")

    @cmd
    def distance(node1, node2):
        """Euclidean distance between two nodes' positions."""
        return math.hypot(node1.x - node2.x, node1.y - node2.y)

    @cmd
    def copyNode(template, name, **extra):
        """Create node `name` with all field values copied from `template`."""
        if not isinstance(template, Node):
            raise TypeError("first argument must be a template node")
        n = g.addNode(name)
        for fname, f in g.node_schema.items():
            if fname != "name" and not f.readonly:
                setattr(n, fname, getattr(template, fname))
        for k, v in extra.items():
            setattr(n, k, v)
        return n

    @cmd
    def averageEdgeColor(edges=None):
        """Color edges the average of their endpoint colors (all edges by default)."""
        for e in elements_of(g.edges if edges is None else edges):
            if isinstance(e, Edge):
                e.color = colors.averageColor(e._n1.color, e._n2.color)

    @cmd
    def skitter(field):
        """Nodes around a circle ordered by field; radius shrinks with outdegree."""
        order = sort_by(g.nodes, _field(field))
        if not order:
            return
        maxdeg = max(len(n.getOutEdges()) for n in order) + 1.0
        for i, n in enumerate(order):
            a = 2 * math.pi * i / len(order)
            r = (1 - math.log((len(n.getOutEdges()) + 1.0) / maxdeg)) * 500.0
            n.x = 500.0 + r * math.cos(a)
            n.y = 500.0 + r * math.sin(a)

    @cmd
    def floatRange(a, b, inc):
        """Like range() but for floats."""
        out = []
        x = float(a)
        while x < b:
            out.append(x)
            x += inc
        return out

    @cmd
    def getNodeSchema():
        """The node fields."""
        return list(g.node_schema.values())

    @cmd
    def getEdgeSchema():
        """The edge fields."""
        return list(g.edge_schema.values())

    @cmd
    def density():
        n = len(g._nodes)
        return 0.0 if n < 2 else len(g._edges) / (n * (n - 1) / 2)

    # ---- grouping --------------------------------------------------------------
    def _seq_field(d, what):
        if len(d) == 1:
            f = d[0]
            return (g.nodes if f.kind == NODE else g.edges), f
        if len(d) == 2:
            return d[0], d[1]
        raise TypeError(f"{what}([seq,] field)")

    @cmd
    def groupBy(*d):
        """groupBy(field) or groupBy(seq, field): groups of elements sharing a value."""
        seq, f = _seq_field(d, "groupBy")
        return group_by(seq, _field(f))

    @cmd
    def groupAndSortBy(*d):
        """Like groupBy, with the groups ordered by value."""
        seq, f = _seq_field(d, "groupAndSortBy")
        return group_by(seq, _field(f), sort=True)

    @cmd
    def sortBy(*d):
        """sortBy(field) or sortBy(seq, field)."""
        seq, f = _seq_field(d, "sortBy")
        return sort_by(seq, _field(f))

    # ---- visual mapping ---------------------------------------------------------
    @cmd
    def colorize(field, *cs):
        """colorize(field) gives each value its own clearly different colour (the
        largest group first; see distinctColors); colorize(field, start, end) or
        colorize(field, start, middle, end) a gradient over the sorted values."""
        field = _field(field)
        if not cs:
            groups = sorted(group_by(field.elements(), field), key=len, reverse=True)
            for grp, c in zip(groups, colors.distinctColors(len(groups))):
                grp.color = c
            return
        if len(cs) not in (2, 3):
            raise TypeError("colorize(field[, start[, middle], end])")
        groups = group_by(field.elements(), field, sort=True)
        if not groups:
            print("No groupings")
            return
        palette = colors.generateColors(*cs, len(groups))
        for grp, c in zip(groups, palette):
            grp.color = c

    @cmd
    def resizeLinear(field, start, end):
        """Size nodes (or edge widths) by rank of field value, from start to end."""
        field = _field(field)
        groups = group_by(field.elements(), field, sort=True)
        k = len(groups)
        attr = "size" if field.kind == NODE else "width"
        for i, grp in enumerate(groups):
            size = start if k == 1 else start + (end - start) * i / (k - 1)
            for e in grp:
                setattr(e, attr, size)

    @cmd
    def resizeRandom(field, start, end):
        field = _field(field)
        attr = "size" if field.kind == NODE else "width"
        for grp in group_by(field.elements(), field):
            size = start + random.random() * (end - start)
            for e in grp:
                setattr(e, attr, size)

    def _numeric(field):
        vals = []
        for e in field.elements():
            v = field.get(e)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                vals.append((e, float(v)))
        if not vals:
            raise GuessError(f"field '{field.name}' has no numeric values")
        return vals

    def _scaler(vals, scale):
        """Map values to 0..1 with a linear, log, sqrt or rank scale."""
        scale = str(scale).lower()
        xs = [v for _, v in vals]
        if scale == "rank":
            order = sorted(set(xs))
            pos = {v: i for i, v in enumerate(order)}
            k = max(len(order) - 1, 1)
            return lambda v: pos[v] / k
        if scale in ("log", "sqrt"):
            lo = min(xs)
            shift = (1 - lo) if (scale == "log" and lo < 1) else (-lo if lo < 0 else 0)
            f = (lambda v: math.log(v + shift)) if scale == "log" else (lambda v: math.sqrt(v + shift))
        elif scale == "linear":
            f = float
        else:
            raise GuessError('scale is "linear", "log", "sqrt" or "rank"')
        a, b = f(min(xs)), f(max(xs))
        return (lambda v: 0.5) if b == a else (lambda v: (f(v) - a) / (b - a))

    @cmd
    def sizeBy(field, smallest, largest, scale="linear"):
        """sizeBy(field, min, max) sizes nodes (or edge widths, for an edge field) in
        proportion to a numeric field's value, from min to max. scale may be
        "linear", "log", "sqrt" or "rank" (as in Gephi's ranking). Compare
        resizeLinear, which spaces distinct values evenly."""
        field = _field(field)
        vals = _numeric(field)
        t = _scaler(vals, scale)
        attr = "size" if field.kind == NODE else "width"
        lo, hi = float(smallest), float(largest)
        for e, v in vals:
            setattr(e, attr, lo + (hi - lo) * t(v))

    @cmd
    def colorBy(field, start, end, scale="linear", middle=None):
        """colorBy(field, startColor, endColor) colours elements along a gradient in
        proportion to a numeric field's value; scale may be "linear", "log",
        "sqrt" or "rank"; middle=color adds a midpoint colour. Compare colorize,
        which spaces distinct values evenly."""
        field = _field(field)
        vals = _numeric(field)
        t = _scaler(vals, scale)
        stops = [colors.parse(start, (255, 0, 0, 255))]
        if middle is not None:
            stops.append(colors.parse(middle, (0, 255, 0, 255)))
        stops.append(colors.parse(end, (0, 0, 255, 255)))
        for e, v in vals:
            e.color = colors.mix_stops(stops, t(v))

    session.register_command("randomColor", colors.randomColor)
    session.register_command("distinctColors", colors.distinctColors)
    session.register_command("generateColors", colors.generateColors)
    session.register_command("averageColor", colors.averageColor)

    # ---- view ---------------------------------------------------------------------
    @cmd
    def center(*d):
        """center() fits the whole graph; center(seq) zooms to the given elements."""
        if not d:
            session.emit({"type": "center", "nodes": [], "edges": []})
            return
        items = list(elements_of(d[0] if len(d) == 1 else d))
        if not items:
            raise GuessError("nothing to center on")
        session.emit({"type": "center",
                      "nodes": [x._id for x in items if isinstance(x, Node)],
                      "edges": [x._id for x in items if isinstance(x, Edge)]})

    # ---- help -------------------------------------------------------------------
    @cmd
    def help(obj=None):
        """help(command) shows documentation; help() lists commands."""
        if obj is None:
            names = sorted(n for n, (_o, k) in session.system.items() if k == "command")
            print("Commands: " + ", ".join(names))
            print("Type help(name) for details, e.g. help(colorize)")
            return
        if isinstance(obj, Field):
            print(f"{obj.kind} field '{obj.name}' ({obj.type}), default {obj.default!r}")
            return
        try:
            sig = str(inspect.signature(obj))
        except (TypeError, ValueError):
            sig = "(...)"
        name = getattr(obj, "__name__", type(obj).__name__)
        print(f"{name}{sig}")
        doc = inspect.getdoc(obj)
        if doc:
            print(doc)

    # Java-style booleans used throughout the original GUESS scripts
    session._bind("true", True, kind="command")
    session._bind("false", False, kind="command")

    # type names for addNodeField(...)
    for tname in ("VARCHAR", "INTEGER", "INT", "DOUBLE", "FLOAT", "BOOLEAN"):
        session.ns.setdefault(tname, tname)


def _connected(a, b):
    return any(e.opposite(a) is b for e in a._inc.values())


def _minus(a, b):
    drop = {id(x) for x in b}
    return GSet(x for x in a if id(x) not in drop)


def _field(f):
    if not isinstance(f, Field):
        raise GuessError(f"expected a field (e.g. dept, freq), got {f!r}")
    return f
