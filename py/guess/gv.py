"""Graphviz layouts (WebAssembly build of Graphviz in the page).

    dotLayout(rankdir="LR", clusters=dept)   layered drawing; clusters kept together, edges routed
    neatoLayout()                            stress majorization: distances follow the graph
    sfdpLayout()                             multilevel force layout for large graphs
    fdpLayout(clusters=dept); circoLayout(); twopiLayout(v1); osageLayout(dept)
    removeOverlap()                          remove node overlaps, keeping the layout's shape
    graphvizLayout("neato", mode="sgd")      any engine with any Graphviz graph attributes

The page loads Graphviz (about 1 MB) in the background after start-up, like
igraph. Positions come back in points; GUESS uses 1 unit = 3 points, the same
scale exportDOT and makeFromDOT use, so node sizes and spacing agree.
"""
import json

import numpy as np

from .dot import PT, _q
from .model import Field, GuessError, Node

_RUNNER = [None]          # set by tests / tools: fn(dot, engine, nop) -> json text


def runner():
    """A function (dot, engine, nop) -> Graphviz json text, or None."""
    if _RUNNER[0] is not None:
        return _RUNNER[0]
    try:
        from js import guessGraphvizLayout       # the page's worker (Pyodide)
    except ImportError:
        return None
    try:
        if guessGraphvizLayout is None or not callable(guessGraphvizLayout):
            return None
    except Exception:  # noqa: BLE001 - a JsProxy for undefined
        return None
    return lambda dot, engine, nop: str(guessGraphvizLayout(dot, engine, int(nop)))


def need():
    r = runner()
    if r is None:
        raise GuessError("Graphviz loads in the background a few seconds after GUESS starts; "
                         "try again in a moment")
    return r


def node_runner(web_dir):
    """A runner that calls the same WebAssembly Graphviz through Node (for the
    Python tests and the manual's example checker). None if unavailable."""
    import pathlib
    import shutil
    import subprocess
    mod = pathlib.Path(web_dir).resolve() / "node_modules" / "@hpcc-js" / "wasm-graphviz" / "dist" / "index.js"
    node = shutil.which("node")
    if not node or not mod.exists():
        return None
    script = (f"import {{ Graphviz }} from {json.dumps(mod.as_uri())};"
              "const chunks=[];for await (const c of process.stdin) chunks.push(c);"
              "const a=JSON.parse(Buffer.concat(chunks).toString());"
              "const gv=await Graphviz.load();"
              "process.stdout.write(gv.layout(a.dot,'json',a.engine,a.nop?{nop:a.nop}:undefined));")

    def run(dot, engine, nop):
        p = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(
            {"dot": dot, "engine": engine, "nop": int(nop)}), capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise GuessError(f"Graphviz: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'failed'}")
        return p.stdout
    return run


_SHAPES = {1: "box", 2: "ellipse", 3: "box", 4: "box", 5: "ellipse", 6: "box",
           11: "triangle", 12: "diamond", 13: "hexagon", 14: "octagon"}


def build_dot(snap, edges, *, directed, graph_attrs, clusters=None, with_pos=False, len_field=None):
    """DOT text for laying out the snapshot's nodes: sizes and shapes, no
    labels (so labels don't change node sizes), pinned nodes for engines that
    honour `pin`, optional cluster subgraphs and edge lengths."""
    out = [f"{'digraph' if directed else 'graph'} {{"]
    for k, v in graph_attrs.items():
        if v is not None:
            out.append(f"  {k}={_q(v)};")
    out.append('  node [label="", fixedsize=true];')
    sizes = snap.size

    def line(i, n):
        w, h = float(sizes[i, 0]), float(sizes[i, 1])
        attrs = [f"width={_q(f'{max(w, 1) * PT / 72:.4f}')}", f"height={_q(f'{max(h, 1) * PT / 72:.4f}')}",
                 f"shape={_q(_SHAPES.get(int(n.style or 2), 'polygon' if 103 <= int(n.style or 2) <= 164 else 'ellipse'))}"]
        if 103 <= int(n.style or 2) <= 164:
            attrs.append(f"sides={int(n.style) - 100}")
        if with_pos or snap.fixed[i]:
            cx, cy = float(snap.pos[i, 0]) + w / 2, float(snap.pos[i, 1]) + h / 2
            attrs.append(f"pos={_q(f'{cx * PT:.3f},{-cy * PT:.3f}' + ('!' if snap.fixed[i] else ''))}")
            if snap.fixed[i]:
                attrs.append('pin="true"')
        return f"{_q(n._id)} [{', '.join(attrs)}];"

    if clusters is not None:
        groups = {}
        for i, n in enumerate(snap.nodes):
            groups.setdefault(clusters.get(n), []).append(i)
        for k, (val, members) in enumerate(groups.items()):
            if val is None:
                out += [f"  {line(i, snap.nodes[i])}" for i in members]
                continue
            out.append(f"  subgraph {_q(f'cluster_{k}')} {{")
            out += [f"    {line(i, snap.nodes[i])}" for i in members]
            out.append("  }")
    else:
        out += [f"  {line(i, n)}" for i, n in enumerate(snap.nodes)]
    arrow = "->" if directed else "--"
    for e in edges:
        attrs = [f"id={_q('e' + str(e._id))}"]
        if directed and not e._directed:
            attrs.append('dir="none"')
        if len_field is not None:
            v = len_field.get(e)
            if v is not None and isinstance(v, (int, float)) and v > 0:
                attrs.append(f"len={_q(f'{float(v) * PT / 72:.4f}')}")
        out.append(f"  {_q(e._n1._id)} {arrow} {_q(e._n2._id)} [{', '.join(attrs)}];")
    out.append("}")
    return "\n".join(out) + "\n"


def parse(text):
    try:
        return json.loads(text)
    except ValueError:
        raise GuessError("Graphviz returned no layout") from None


def positions(result, snap):
    """Node top-left positions (GUESS units) from a Graphviz json result, in snapshot
    order; nodes Graphviz didn't place stay where they are."""
    P = np.array(snap.pos, float, copy=True)
    index = {str(n._id): i for i, n in enumerate(snap.nodes)}
    for o in result.get("objects", []):
        i = index.get(str(o.get("name")))
        if i is None or "pos" not in o:
            continue
        x, y = (float(v) for v in o["pos"].split(",")[:2])
        P[i, 0] = x / PT - snap.size[i, 0] / 2
        P[i, 1] = -y / PT - snap.size[i, 1] / 2
    return P


def _bezier(points, steps=4):
    """Points along a cubic B-spline given as Graphviz control points (3n+1)."""
    out = []
    for k in range(0, len(points) - 3, 3):
        p0, p1, p2, p3 = points[k:k + 4]
        for s in range(1 if k else 0, steps + 1):
            t = s / steps
            a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
            out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def routes(result):
    """{edge id: [bend points in GUESS centre coordinates]} from the edges'
    spline control points (the ends are dropped: edges run from node centres)."""
    out = {}
    for e in result.get("edges", []):
        pos, eid = e.get("pos"), str(e.get("id", ""))
        if not pos or not eid.startswith("e"):
            continue
        ctrl = []
        for part in pos.split():
            if part.startswith(("e,", "s,")):
                continue
            x, y = part.split(",")[:2]
            ctrl.append((float(x), float(y)))
        if len(ctrl) < 4:
            continue
        pts = _bezier(ctrl)[1:-1]
        out[int(eid[1:])] = [(x / PT, -y / PT) for x, y in pts]
    return out


def install(session):
    from .layouts import _Layouts
    lay = _Layouts(session)

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def field(f, kind_ok=("node",)):
        return _field_of(f, kind_ok)

    def _field_of(f, kind_ok=("node",)):
        if f is None:
            return None
        from .model import as_field
        return as_field(g(), f, "this", tuple(kind_ok))

    def run_layout(engine, attrs, *, clusters=None, with_pos=False, nop=0, len_field=None,
                   route=False, align=False):
        run = need()
        s = lay.snap()
        if s.n == 0:
            return
        edges = [e for e in g()._edges_list() if e._n1._id in s.index and e._n2._id in s.index]
        directed = any(e._directed for e in edges)
        text = build_dot(s, edges, directed=directed, graph_attrs=attrs, clusters=clusters,
                         with_pos=with_pos, len_field=len_field)
        result = parse(run(text, engine, nop))
        P = positions(result, s)
        if align:     # keep the drawing where it was (overlap removal shifts and grows it)
            keep = ~s.fixed
            if keep.any():
                P[keep] += (s.pos[keep].mean(0) - P[keep].mean(0))
        lay.apply(s, P)
        if route:
            by_id = {e._id: e for e in edges}
            for eid, pts in routes(result).items():
                e = by_id.get(eid)
                if e is not None and e._n1 is not e._n2:
                    g().set_bends(e, pts)

    def cluster_arg(c):
        f = field(c) if c is not None else None
        if f is not None and f.kind != "node":
            raise GuessError("clusters should be a node field, e.g. clusters=dept")
        return f

    @cmd
    def graphvizLayout(engine="dot", **attrs):
        """graphvizLayout("neato") lays the graph out with any Graphviz engine:
        dot, neato, fdp, sfdp, circo, twopi, osage or patchwork. Keyword
        arguments become Graphviz graph attributes, e.g.
        graphvizLayout("neato", mode="sgd", overlap="prism") or
        graphvizLayout("dot", rankdir="LR", ranksep=1). Pinned (fixed) nodes stay
        put in neato and fdp."""
        engine = str(engine).lower()
        if engine not in ("dot", "neato", "fdp", "sfdp", "circo", "twopi", "osage", "patchwork"):
            raise GuessError("engine should be dot, neato, fdp, sfdp, circo, twopi, osage or patchwork")
        run_layout(engine, {k: str(v).lower() if isinstance(v, bool) else v for k, v in attrs.items()})

    @cmd
    def dotLayout(rankdir="TB", clusters=None, nodesep=0.25, ranksep=0.5, route=True):
        """dotLayout() draws the graph in layers with Graphviz's dot: edges point
        down (rankdir="LR": left to right; "BT", "RL"), crossings are minimised
        and long edges are routed around nodes as smooth bends (route=False:
        straight edges). clusters=dept keeps each value's nodes together in a
        box. nodesep and ranksep are spacings in inches. Best for hierarchies,
        dependency and citation graphs."""
        rd = str(rankdir).upper()
        if rd not in ("TB", "LR", "BT", "RL"):
            raise GuessError('rankdir should be "TB", "LR", "BT" or "RL"')
        run_layout("dot", {"rankdir": rd, "nodesep": nodesep, "ranksep": ranksep, "splines": "true"},
                   clusters=cluster_arg(clusters), route=bool(route))

    @cmd
    def neatoLayout(mode="major", model="shortpath", field=None, overlap="prism"):
        """neatoLayout() places nodes so their distances on screen follow their
        distances in the graph (stress majorization: the best-quality layout up
        to a few thousand nodes). mode: "major" (default), "sgd" (faster),
        "KK" (Kamada-Kawai); model="circuit" uses resistance distance;
        field=weight makes an edge field the preferred edge length;
        overlap="prism" (default) then removes node overlaps (overlap="true"
        leaves them)."""
        lf = _field_of(field, ("edge",)) if field is not None else None
        run_layout("neato", {"mode": mode, "model": model, "overlap": overlap, "sep": "+4"}, len_field=lf)

    @cmd
    def sfdpLayout(overlap="prism", K=None):
        """sfdpLayout() is Graphviz's multilevel force layout: fast on large graphs
        (thousands to tens of thousands of nodes) with good global structure.
        K is the ideal edge length in inches; overlap="prism" removes overlaps."""
        run_layout("sfdp", {"overlap": overlap, "K": K, "sep": "+4"})

    @cmd
    def fdpLayout(clusters=None, overlap="prism"):
        """fdpLayout() is a force layout that can keep clusters together:
        fdpLayout(clusters=louvain_class) gives each community its own box."""
        run_layout("fdp", {"overlap": overlap, "sep": "+4"}, clusters=cluster_arg(clusters))

    @cmd
    def circoLayout():
        """circoLayout() puts the biconnected parts of the graph on circles,
        chained together: shows rings and cycles (pathways, loops)."""
        run_layout("circo", {"overlap": "false"})

    @cmd
    def twopiLayout(root=None):
        """twopiLayout(v1) places nodes on rings by their distance from a root
        (Graphviz's twopi; default root: chosen by Graphviz)."""
        attrs = {"overlap": "false", "ranksep": 1}
        if root is not None:
            if not isinstance(root, Node):
                root = g().getNodeByName(str(root))
                if root is None:
                    raise GuessError("twopiLayout needs a node")
            attrs["root"] = str(root._id)
        run_layout("twopi", attrs)

    @cmd
    def osageLayout(clusters):
        """osageLayout(dept) packs each value's nodes into a rectangle and packs
        the rectangles together: a compact overview of the groups."""
        run_layout("osage", {"pack": "8"}, clusters=cluster_arg(clusters))

    @cmd
    def removeOverlap(method="prism", sep=4):
        """removeOverlap() moves nodes apart until none overlap, keeping the shape
        of the current layout (Graphviz's PRISM). Works after any layout. method:
        "prism" (default), "voronoi", "scale" (spread evenly), "compress";
        sep is the extra margin in points."""
        m = str(method).lower()
        if m not in ("prism", "voronoi", "scale", "scalexy", "compress", "vpsc", "ortho"):
            raise GuessError('method should be "prism", "voronoi", "scale", "compress", "vpsc" or "ortho"')
        run_layout("neato", {"overlap": m, "sep": f"+{float(sep):g}"}, with_pos=True, nop=1, align=True)

