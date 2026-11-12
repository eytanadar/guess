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


    # ---- Lombardi-style drawings (circular-arc edges, even angles at nodes) ---------------------
    def _arc_setup():
        """Edges between distinct visible nodes, with each end's chord angle."""
        edges = [e for e in g().edges if e.visible and e.node1 is not e.node2 and e.node1.visible and e.node2.visible]
        ends = {}
        for e in edges:
            (x1, y1), (x2, y2) = _centre(e.node1), _centre(e.node2)
            a1 = math.atan2(y2 - y1, x2 - x1)
            # (edge, sign, chord angle): the tangent at this end is chord + sign * theta
            ends.setdefault(e.node1._id, []).append((e, 1, a1))
            ends.setdefault(e.node2._id, []).append((e, -1, a1 + math.pi))
        return edges, ends

    def _wrap(a):
        return (a + math.pi) % (2 * math.pi) - math.pi

    def _tangents(ends, theta):
        return {v: sorted(((c + s * theta[e._id]) % (2 * math.pi), e, s) for e, s, c in lst)
                for v, lst in ends.items()}

    def lombardiness():
        """lombardiness() scores how close the drawing is to a Lombardi drawing,
        0-100: 100 when every node's edges leave it at equal angles (as
        measured by their tangents, so arcs count; see lombardiEdges). Nodes
        with one edge are always perfect (Chernobelskiy et al., GD 2011)."""
        edges, ends = _arc_setup()
        theta = {e._id: math.radians(e.arc or 0.0) for e in edges}
        total, count = 0.0, 0
        for v, tang in _tangents(ends, theta).items():
            d = len(tang)
            if d < 2:
                continue
            angles = [t for t, _, _ in tang]
            for i in range(d):
                gap = (angles[(i + 1) % d] - angles[i]) % (2 * math.pi)
                total += abs(gap - 2 * math.pi / d)
                count += 1
        return 100.0 if not count else 100 - 100 * (total / count) / math.pi

    def lombardiEdges(iterations=300, limit=70):
        """lombardiEdges() turns the edges into circular arcs, without moving
        any node, so that each node's edges leave it as evenly spread as
        possible (a "near-Lombardi" drawing, after the artist Mark Lombardi;
        Chernobelskiy et al., GD 2011). Each edge's bend is the angle, in
        degrees, at which it leaves its ends, stored in its `arc` field (0 =
        straight; at most `limit`). Returns lombardiness() before and after.
        straightenEdges() undoes it."""
        edges, ends = _arc_setup()
        if not edges:
            return (100.0, 100.0)
        before = lombardiness()
        theta = {e._id: math.radians(e.arc or 0.0) for e in edges}
        cap = math.radians(float(limit))
        for it in range(int(iterations)):
            push = {e._id: 0.0 for e in edges}
            for v, tang in _tangents(ends, theta).items():
                d = len(tang)
                if d < 2:
                    continue
                step = 2 * math.pi / d
                # the best evenly spaced fan for this node: rotate the ideal template onto the tangents
                offs = [tang[i][0] - i * step for i in range(d)]
                rot = math.atan2(sum(math.sin(o) for o in offs), sum(math.cos(o) for o in offs))
                for i, (t, e, sg) in enumerate(tang):
                    want = rot + i * step
                    push[e._id] += sg * _wrap(want - t) / 2
            rate = 0.6 * (1 - it / max(1, int(iterations))) + 0.05
            for e in edges:
                theta[e._id] = max(-cap, min(cap, theta[e._id] + rate * push[e._id]))
        for e in edges:
            e.arc = round(math.degrees(theta[e._id]), 2)
        return (round(before, 1), round(lombardiness(), 1))

    def straightenEdges():
        """straightenEdges() makes every edge straight again (arc = 0)."""
        for e in g().edges:
            if e.arc:
                e.arc = 0.0

    def lombardiLayout(iterations=400, seed=0):
        """lombardiLayout() makes a Lombardi-style drawing: circular-arc edges,
        with each node's edges leaving it at (nearly) equal angles. It is the
        tangent-based spring embedder of Chernobelskiy et al. (GD 2011):
        attraction (d - k)/d along edges and repulsion k^2/d^3 between all
        pairs place the nodes, while a tangential force turns each edge's
        chord so that the angles both ends want for it agree, and each
        node's fan of edge tangents turns to fit; edges then get the arc
        that matches (stored in `arc`, as by lombardiEdges). Returns
        lombardiness() of the straight-line drawing it starts from and of
        the result. Best for small and medium graphs (up to a few hundred
        nodes)."""
        import random
        nodes = [n for n in g().nodes if n.visible]
        if not nodes:
            return (100.0, 100.0)
        rnd = random.Random(seed)
        n = len(nodes)
        idx = {nd._id: i for i, nd in enumerate(nodes)}
        pos = [[rnd.uniform(-1, 1), rnd.uniform(-1, 1)] for _ in nodes]
        edges = [e for e in g().edges if e.visible and e.node1._id in idx and e.node2._id in idx and e.node1 is not e.node2]
        pairs = [(idx[e.node1._id], idx[e.node2._id]) for e in edges]
        inc = [[] for _ in nodes]                      # per node: (edge index, sign)
        for k_, (i, j) in enumerate(pairs):
            inc[i].append((k_, 1))
            inc[j].append((k_, -1))
        theta = [0.0] * len(pairs)
        k = 1.0 / math.sqrt(max(n, 1))
        steps = int(iterations)
        t0 = 0.15
        cap = math.radians(75)
        for it in range(steps):
            disp = [[0.0, 0.0] for _ in nodes]
            for i in range(n):
                xi, yi = pos[i]
                for j in range(i + 1, n):
                    dx, dy = xi - pos[j][0], yi - pos[j][1]
                    d = math.hypot(dx, dy) or 1e-6
                    f = k * k / (d * d * d) * 0.05
                    disp[i][0] += dx * f
                    disp[i][1] += dy * f
                    disp[j][0] -= dx * f
                    disp[j][1] -= dy * f
            for i, j in pairs:
                dx, dy = pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]
                d = math.hypot(dx, dy) or 1e-6
                f = (d - k) / d * 0.5
                disp[i][0] -= dx * f
                disp[i][1] -= dy * f
                disp[j][0] += dx * f
                disp[j][1] += dy * f
            if it > steps * 0.25:
                # each node's ideal fan: equal angles, turned to fit its current tangents
                chord = [math.atan2(pos[j][1] - pos[i][1], pos[j][0] - pos[i][0]) for i, j in pairs]
                want = {}
                for v in range(n):
                    d = len(inc[v])
                    if d < 2:
                        continue
                    tang = sorted(((chord[e] + (0 if sg > 0 else math.pi) + sg * theta[e]) % (2 * math.pi), e, sg)
                                  for e, sg in inc[v])
                    step = 2 * math.pi / d
                    offs = [tang[q][0] - q * step for q in range(d)]
                    rot = math.atan2(sum(math.sin(o) for o in offs), sum(math.cos(o) for o in offs))
                    for q, (t, e, sg) in enumerate(tang):
                        want[(e, sg)] = rot + q * step
                for e, (i, j) in enumerate(pairs):
                    cu, cv = chord[e], chord[e] + math.pi
                    wu, wv = want.get((e, 1)), want.get((e, -1))
                    tu = _wrap(wu - cu) if wu is not None else theta[e]          # the arc u would like
                    tv = -_wrap(wv - cv) if wv is not None else theta[e]         # the arc v would like
                    theta[e] = max(-cap, min(cap, theta[e] + 0.5 * ((tu + tv) / 2 - theta[e])))
                    if wu is None or wv is None:
                        continue
                    # tangential force: turn the chord so both ends' wishes agree
                    phi = max(-0.3, min(0.3, (tu - tv) / 2))
                    dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                    c, s_ = math.cos(phi * 0.5), math.sin(phi * 0.5)
                    rx, ry = dx * c - dy * s_ - dx, dx * s_ + dy * c - dy
                    disp[j][0] += 0.9 * rx / 2
                    disp[j][1] += 0.9 * ry / 2
                    disp[i][0] -= 0.9 * rx / 2
                    disp[i][1] -= 0.9 * ry / 2
            temp = t0 * (steps - it) / steps
            for i in range(n):
                dl = math.hypot(*disp[i]) or 1e-9
                m = min(dl, temp)
                pos[i][0] += disp[i][0] / dl * m
                pos[i][1] += disp[i][1] / dl * m
        xs, ys = [p[0] for p in pos], [p[1] for p in pos]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
        scale = 60 * math.sqrt(n) / span
        for nd, (x, y) in zip(nodes, pos):
            nd.x, nd.y = (x - min(xs)) * scale, (y - min(ys)) * scale
        straightenEdges()
        before = lombardiness()
        for e, t in zip(edges, theta):
            e.arc = round(math.degrees(t), 2)
        lombardiEdges(iterations=150)                  # polish the arcs for the final positions
        return (round(before, 1), round(lombardiness(), 1))

    for fn in (makeFromMap, colorGraph, edgeCrossings, expandLayers, spectrum, plotSpectrum, lombardiness,
               lombardiEdges, straightenEdges, lombardiLayout):
        reg(fn.__name__, fn)
