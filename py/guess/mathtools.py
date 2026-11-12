"""Tools for the mathematics of networks (Newman, Networks, ch. 6): region
adjacency networks from maps, graph colouring, edge crossings, expanding a
multiplex network into layers, and spectra."""
import math

from .model import GuessError, Node


def install(session):
    reg = session.register_command

    def g():
        return session.graph

    def makeFromMap(region="usa"):
        """makeFromMap("usa") makes the network of the lower 48 US states, an
        edge wherever two share a border (touching at a single point, like
        the Four Corners, doesn't count); makeFromMap("world") does the same
        for countries.
        Nodes get `abbrev`, `latitude`, `longitude` (and `continent` for
        countries) and are placed on a map. Such networks are planar (when
        each region is one piece of land), which is why four colours always
        suffice to colour a map. Data: Natural Earth 1:50m, public domain."""
        from . import regiondata
        key = str(region).lower()
        data = {"usa": regiondata.USA, "us": regiondata.USA, "world": regiondata.WORLD}.get(key)
        if data is None:
            raise GuessError('makeFromMap knows "usa" and "world"')
        import networkx as nx
        G = nx.Graph()
        for name, info in data["nodes"].items():
            attrs = {"label": name, "abbrev": info["abbrev"], "longitude": info["pos"][0], "latitude": info["pos"][1]}
            if "continent" in info:
                attrs["continent"] = info["continent"]
            G.add_node(name.replace(" ", "_").replace(".", "").replace("'", "").replace("-", "_").replace(",", ""),
                       **attrs)
        ident = {name: name.replace(" ", "_").replace(".", "").replace("'", "").replace("-", "_").replace(",", "")
                 for name in data["nodes"]}
        G.add_edges_from((ident[a], ident[b]) for a, b in data["edges"])
        session.ns["fromNetworkX"](G)
        if key in ("usa", "us"):
            session.ns["geoLayout"](projection="albers", map="usa")
        else:
            session.ns["geoLayout"](projection="equirectangular", map="world")

    def colorGraph(strategy="DSATUR", show=True):
        """colorGraph() gives every node a colour class (`color_class`, 0, 1,
        2, ...) so that no two neighbours share one, using as few as it can
        find (greedy colouring; strategy "DSATUR" (default),
        "largest_first", "smallest_last" or "random_sequential"); show=true
        also colours the nodes by class. Returns the number of colours used.
        Planar networks (maps) never need more than four, though greedy
        methods sometimes use five."""
        import networkx as nx
        strategies = {"dsatur": "saturation_largest_first", "largest_first": "largest_first",
                      "smallest_last": "smallest_last", "random_sequential": "random_sequential"}
        st = strategies.get(str(strategy).lower())
        if st is None:
            raise GuessError('strategy is "DSATUR", "largest_first", "smallest_last" or "random_sequential"')
        G = session.ns["toNetworkX"](directed=False)
        col = nx.coloring.greedy_color(G, strategy=st)
        session.ns["setField"]({k: int(v) for k, v in col.items()}, "color_class")
        if show:
            session.ns["colorize"](g().node_schema["color_class"])
        return (max(col.values()) + 1) if col else 0

    def _centre(n):
        return n.x + n.width / 2, n.y + n.height / 2

    def edgeCrossings(pairs=False):
        """edgeCrossings() counts the pairs of edges that cross in the current
        drawing (straight edges between node centres; edges sharing a node
        don't count). pairs=true returns the crossing pairs instead, e.g.
        for e1, e2 in edgeCrossings(pairs=true): e1.color = red. A planar
        network can be drawn with no crossings; finding such a drawing is
        another matter."""
        edges = [e for e in g().edges if e.visible and e.node1.visible and e.node2.visible and e.node1 is not e.node2]
        segs = []
        for e in edges:
            (x1, y1), (x2, y2) = _centre(e.node1), _centre(e.node2)
            segs.append((e, x1, y1, x2, y2, min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)))
        segs.sort(key=lambda s: s[5])

        def orient(ax, ay, bx, by, cx, cy):
            v = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
        out, count = [], 0
        for i in range(len(segs)):
            e, x1, y1, x2, y2, lx, hx, ly, hy = segs[i]
            for j in range(i + 1, len(segs)):
                f, u1, v1, u2, v2, lx2, hx2, ly2, hy2 = segs[j]
                if lx2 > hx:
                    break                                   # sorted by left end: no more overlaps in x
                if hy2 < ly or ly2 > hy:
                    continue
                if {e.node1, e.node2} & {f.node1, f.node2}:
                    continue
                if (orient(x1, y1, x2, y2, u1, v1) * orient(x1, y1, x2, y2, u2, v2) < 0 and
                        orient(u1, v1, u2, v2, x1, y1) * orient(u1, v1, u2, v2, x2, y2) < 0):
                    count += 1
                    if pairs:
                        out.append((e, f))
        return out if pairs else count

    def expandLayers(field, order=None, directed=False, name="layers"):
        """expandLayers(kind) turns a multiplex network (one set of nodes,
        several kinds of edge, told apart by the edge field `kind`) into a
        multilayer one in a new graph tab: a copy of every node in each layer
        it has edges in, the layer's edges between the copies, and
        "interlayer" edges joining each node's copies in consecutive layers
        (order= a list of the layer values; default sorted). directed=true
        points the interlayer edges forward, as for time: a temporal network
        where nothing travels back in time. Copies keep the node's position
        and get `layer` and `original`; run isometricLayout(layer) to stack
        the layers. use() goes back to the original."""
        from .model import as_field
        gr = g()
        f = as_field(gr, field, "expandLayers")
        if f.kind == "node":
            raise GuessError("expandLayers needs an edge field, e.g. expandLayers(kind)")
        values = sorted({f.get(e) for e in gr.edges if f.get(e) is not None}, key=str) if order is None else list(order)
        if not values:
            raise GuessError(f"no edges have a value of {f.name}")
        import networkx as nx
        H = nx.DiGraph() if directed else nx.Graph()
        present = {}
        for e in gr.edges:
            lay = f.get(e)
            if lay not in values:
                continue
            for n in (e.node1, e.node2):
                present.setdefault(n.name, set()).add(lay)
        nodes = {n.name: n for n in gr.nodes}

        def cid(v, lay):
            return f"{v}__{values.index(lay)}"
        for v, lays in present.items():
            n = nodes[v]
            for lay in lays:
                H.add_node(cid(v, lay), original=v, layer=str(lay), label=n.label or v, pos=(n.x, n.y))
        for e in gr.edges:
            lay = f.get(e)
            if lay in values:
                a, b = cid(e.node1.name, lay), cid(e.node2.name, lay)
                H.add_edge(a, b, kind="intralayer", layer=str(lay))
                if directed and not e.directed:
                    H.add_edge(b, a, kind="intralayer", layer=str(lay))
        for v, lays in present.items():
            seq = [lay for lay in values if lay in lays]
            for a, b in zip(seq, seq[1:]):
                H.add_edge(cid(v, a), cid(v, b), kind="interlayer", layer="")
        session.ns["fromNetworkX"](H, str(name))
        for e in g().edges:
            if e.kind == "interlayer":
                e.linestyle = "dashed"
        print(f"{len(values)} layers: {', '.join(map(str, values))}")

    def spectrum(matrix="laplacian"):
        """spectrum() returns the eigenvalues of the graph Laplacian L = D - A,
        smallest first; spectrum("adjacency") those of A (largest first),
        spectrum("normalized") of the normalised Laplacian I - D^-1/2 A D^-1/2.
        Direction and weights are ignored (edges count once each way). The
        Laplacian has as many zero eigenvalues as the network has
        components; the second smallest is the algebraic connectivity."""
        import numpy as np
        nodes = [n for n in g().nodes if n.visible]
        idx = {n._id: i for i, n in enumerate(nodes)}
        A = np.zeros((len(nodes), len(nodes)))
        for e in g().edges:
            a, b = idx.get(e._n1._id), idx.get(e._n2._id)
            if a is None or b is None or a == b or not e.visible:
                continue
            A[a, b] = A[b, a] = 1
        m = str(matrix).lower()
        k = A.sum(axis=1)
        if m == "laplacian":
            M = np.diag(k) - A
        elif m == "adjacency":
            M = A
        elif m in ("normalized", "normalised"):
            d = np.where(k > 0, 1 / np.sqrt(np.where(k > 0, k, 1)), 0)
            M = np.eye(len(nodes)) - d[:, None] * A * d[None, :]
        else:
            raise GuessError('matrix is "laplacian", "adjacency" or "normalized"')
        vals = np.linalg.eigvalsh(M) if len(nodes) else np.array([])
        vals = [0.0 if abs(v) < 1e-9 else float(v) for v in vals]
        return sorted(vals, reverse=(m == "adjacency"))

    def plotSpectrum(matrix="laplacian"):
        """plotSpectrum() charts the eigenvalues of the Laplacian (or
        "adjacency", "normalized") in order, one dot each: count the zeros
        to count components; a small second eigenvalue means the network
        nearly splits in two."""
        vals = spectrum(matrix)
        name = {"laplacian": "Laplacian", "adjacency": "adjacency matrix"}.get(str(matrix).lower(), "normalised Laplacian")
        return session.ns["plotLine"]([(i + 1, v) for i, v in enumerate(vals)], title=f"Eigenvalues of the {name}",
                                      xlabel="rank", ylabel="eigenvalue", dots=True)

    for fn in (makeFromMap, colorGraph, edgeCrossings, expandLayers, spectrum, plotSpectrum):
        reg(fn.__name__, fn)
