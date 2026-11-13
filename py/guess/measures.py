"""More measures, field tools and generators — what several Gephi plugins add
(Katz Centrality, Prestige, Bridging Centrality, Weighted Clustering, Clique
Detector, MdsMetric, VectorStatistics, KBrace Filter, Recast column,
FilterFromFile, Node Color Manager, Complex Generators).

Node fields computed on first use (like betweenness; recompute(...) after
editing the graph):

    katz                    Katz centrality (alpha = 0.1, or less when needed to converge)
    domain_prestige         share of the other nodes that can reach it (directed)
    proximity_prestige      Lin's proximity prestige: domain size over mean distance
    rank_prestige           Katz status: how prestigious the nodes pointing at it are
    bridging_coef           Hwang's bridging coefficient
    bridging                betweenness x bridging_coef (bridging centrality)
    wclustering             weighted clustering coefficient (edge weights)

Commands: weightedBridging, cliques, mds, geoVectors, kBrace, castField,
readNames, copyColors, makeWattsStrogatz, makeBarabasiAlbertAging,
makeGeometricRandom, makePowerlawCluster, evaluateLinks.
"""
import math
import random
import re

import numpy as np

from .algorithms import _betweenness_nodes, _nx, to_networkx
from .analysis import _arrays, _weight
from .model import BOOL, DOUBLE, EDGE, INT, NODE, STRING, Edge, Field, GSet, GuessError, Node, elements_of, normalize_type

KATZ_ALPHA = 0.1


# --------------------------------------------------------------------------
# Katz and prestige
# --------------------------------------------------------------------------

def _spectral_radius(n, src, dst):
    """The largest eigenvalue of the adjacency matrix (power iteration on edge arrays)."""
    if not len(src):
        return 0.0
    x = np.ones(n) / math.sqrt(n)
    lam = 0.0
    for _ in range(500):
        # (A^T + I) has the same leading eigenvector and doesn't oscillate on bipartite graphs
        y = _apply(n, src, dst, x) + x
        norm = float(np.linalg.norm(y))
        new = norm - 1.0
        if abs(new - lam) < 1e-10 * max(1.0, abs(new)):
            return max(new, 0.0)
        lam, x = new, y / norm
    return max(lam, 0.0)


def _apply(n, src, dst, x):
    """(A^T x): each node gets the sum over its in-neighbours."""
    y = np.zeros(n)
    np.add.at(y, dst, x[src])
    return y


def katz_alpha(n, src, dst):
    """0.1 (networkx's default) unless that's too big to converge (1/lambda_max)."""
    lam = _spectral_radius(n, src, dst)
    return KATZ_ALPHA if lam * KATZ_ALPHA < 0.95 else 0.9 / lam


def _katz_core(graph, baseline):
    """x = alpha A^T x + baseline, iterated; edges follow their direction
    (undirected ones both ways). Returns (nodes, x, alpha)."""
    nodes, src, dst, _w, _d = _arrays(graph)
    n = len(nodes)
    if n == 0:
        return nodes, np.zeros(0), KATZ_ALPHA
    alpha = katz_alpha(n, src, dst)
    x = np.zeros(n)
    for _ in range(2000):
        new = alpha * _apply(n, src, dst, x) + 1.0
        if np.abs(new - x).max() < 1e-10 * max(1.0, float(np.abs(new).max())):
            x = new
            break
        x = new
    x = x - 1.0 + baseline  # baseline 1: Katz; 0: status (only what is passed on)
    return nodes, x, alpha


def _katz(graph):
    nodes, x, _alpha = _katz_core(graph, 1.0)
    norm = float(np.linalg.norm(x)) or 1.0
    return {v: float(x[i] / norm) for i, v in enumerate(nodes)}     # unit length, as networkx


def _rank_prestige(graph):
    nodes, x, _alpha = _katz_core(graph, 0.0)
    top = float(x.max()) if len(x) else 0.0
    return {v: float(x[i] / top) if top > 0 else 0.0 for i, v in enumerate(nodes)}


def _in_distances(graph):
    """For each node, {u: hops from u to it} over the nodes that can reach it
    (edges followed in their direction; undirected ones both ways)."""
    preds = {v: [] for v in graph._nodes_list()}
    for e in graph._edges_list():
        if e._n1 is e._n2:
            continue
        preds[e._n2].append(e._n1)
        if not e._directed:
            preds[e._n1].append(e._n2)
    out = {}
    for v in preds:
        dist, frontier = {v: 0}, [v]
        while frontier:
            nxt = []
            for x in frontier:
                for u in preds[x]:
                    if u not in dist:
                        dist[u] = dist[x] + 1
                        nxt.append(u)
            frontier = nxt
        del dist[v]
        out[v] = dist
    return out


def _domain_prestige(graph):
    n = len(graph._nodes)
    if n < 2:
        return {v: 0.0 for v in graph._nodes_list()}
    return {v: len(d) / (n - 1) for v, d in _in_distances(graph).items()}


def _proximity_prestige(graph):
    n = len(graph._nodes)
    out = {}
    for v, d in _in_distances(graph).items():
        if not d or n < 2:
            out[v] = 0.0
            continue
        share = len(d) / (n - 1)
        mean = sum(d.values()) / len(d)
        out[v] = share / mean
    return out


# --------------------------------------------------------------------------
# bridging and weighted clustering
# --------------------------------------------------------------------------

def _neighbours(graph):
    nb = {v: set() for v in graph._nodes_list()}
    for e in graph._edges_list():
        if e._n1 is not e._n2:
            nb[e._n1].add(e._n2)
            nb[e._n2].add(e._n1)
    return nb


def _bridging_coef(graph):
    nb = _neighbours(graph)
    out = {}
    for v, ns in nb.items():
        if not ns:
            out[v] = 0.0
            continue
        denom = sum(1.0 / len(nb[u]) for u in ns)
        out[v] = (1.0 / len(ns)) / denom
    return out


def _bridging(graph):
    bc = _bridging_coef(graph)
    btw = _betweenness_nodes(graph)
    return {v: float(btw.get(v, 0.0)) * bc[v] for v in bc}


def _wclustering(graph):
    nx = _nx()
    G = to_networkx(graph, directed=False)
    for _a, _b, d in G.edges(data=True):
        w = d.get("weight", 1.0)
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = 1.0
        d["weight"] = w if math.isfinite(w) and w > 0 else 0.0
    return {v: float(c) for v, c in nx.clustering(G, weight="weight").items()}


LAZY = {
    "katz": _katz,
    "domain_prestige": _domain_prestige,
    "proximity_prestige": _proximity_prestige,
    "rank_prestige": _rank_prestige,
    "bridging_coef": _bridging_coef,
    "bridging": _bridging,
    "wclustering": _wclustering,
}


# --------------------------------------------------------------------------
# link prediction scores (shared with evaluateLinks)
# --------------------------------------------------------------------------

METHODS = ("adamic_adar", "jaccard", "common", "resource")


def link_scores(nbrs, method):
    """{(a, b): score} for unlinked pairs a < b sharing a neighbour; nbrs is a
    list of neighbour sets indexed 0..n-1."""
    m = str(method).lower()
    if m not in METHODS:
        raise GuessError('method should be "adamic_adar", "jaccard", "common" or "resource"')
    scores = {}
    for z, ns in enumerate(nbrs):
        d = len(ns)
        if d < 2:
            continue
        inc = {"adamic_adar": 1 / math.log(d), "resource": 1 / d}.get(m, 1.0)
        ns = sorted(ns)
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                if b not in nbrs[a]:
                    scores[(a, b)] = scores.get((a, b), 0.0) + inc
    if m == "jaccard":
        scores = {(a, b): c / len(nbrs[a] | nbrs[b]) for (a, b), c in scores.items()}
    return scores


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    for name, fn in LAZY.items():
        session.graph.lazy_fields[(NODE, name)] = fn

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def gr():
        return session.graph

    def field_of(f, kinds=(NODE, EDGE), what="this"):
        from .model import as_field
        return as_field(gr(), f, what, kinds)

    # ---- bridging ------------------------------------------------------------------
    @cmd
    def weightedBridging(weight="weight", name="wbridging"):
        """weightedBridging() is bridging centrality for weighted networks: a
        strong tie (big weight) counts as a short one (distance 1/weight), so
        shortest paths prefer strong ties. Stores the weighted betweenness in
        `wbetweenness` and weighted betweenness x bridging_coef in `wbridging`
        (or name=...). Edges with weight 0 or less are left out."""
        nx = _nx()
        g = gr()
        wf = None if weight == "weight" else field_of(weight, (EDGE,), "weightedBridging")
        G = nx.Graph()
        G.add_nodes_from(g._nodes_list())
        for e in g._edges_list():
            if e._n1 is e._n2:
                continue
            try:
                w = float(wf.get(e) if wf is not None else _weight(e))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(w) or w <= 0:
                continue
            d = 1.0 / w
            if G.has_edge(e._n1, e._n2):
                d = min(d, G[e._n1][e._n2]["dist"])       # parallel edges: the strongest
            G.add_edge(e._n1, e._n2, dist=d)
        btw = nx.betweenness_centrality(G, weight="dist", normalized=False)
        bc = _bridging_coef(g)
        fb = g.addNodeField("wbetweenness", DOUBLE, 0.0)
        fw = g.addNodeField(str(name), DOUBLE, 0.0)
        for v in g._nodes_list():
            fb.set(v, float(btw.get(v, 0.0)))
            fw.set(v, float(btw.get(v, 0.0)) * bc[v])
        top = max(g._nodes_list(), key=lambda v: fw.get(v), default=None)
        if top is not None:
            print(f"highest weighted bridging centrality: {top._name} ({fw.get(top):.4g})")
        return fw

    # ---- cliques -------------------------------------------------------------------
    @cmd
    def cliques(minSize=3, limit=1000):
        """cliques(minSize=3) finds every maximal clique (a group where everyone
        is linked to everyone, that no other node could join) with at least
        minSize nodes, ignoring edge direction; largest first, up to `limit`.
        largestCliques() gives just the biggest ones."""
        nx = _nx()
        G = nx.Graph(to_networkx(gr(), directed=False))
        G.remove_edges_from(nx.selfloop_edges(G))
        found = []
        for c in nx.find_cliques(G):
            if len(c) >= int(minSize):
                found.append(sorted(c, key=lambda n: n._id))
        found.sort(key=lambda c: (-len(c), c[0]._id))
        more = len(found) > int(limit)
        found = found[:int(limit)]
        note = f"{len(found)} cliques of {int(minSize)}+ nodes" + (" (limit reached)" if more else "")
        return GSet((GSet(c, f"clique {i} ({len(c)})") for i, c in enumerate(found)), note)

    # ---- MDS -----------------------------------------------------------------------
    @cmd
    def mds(dims=2, weight=None, name="mds"):
        """mds(dims=2) places the nodes in `dims` dimensions by classical
        multidimensional scaling of their shortest-path distances (hops; with
        weight=... an edge field read as a distance), storing the coordinates
        in fields mds1, mds2, ... (or name=...). Unreachable pairs count as one
        more than the longest distance. scatterLayout(mds1, mds2) draws them;
        mdsLayout() does both in one go."""
        g = gr()
        dims = int(dims)
        if dims < 1 or dims > 10:
            raise GuessError("mds needs dims between 1 and 10")
        nodes = g._nodes_list()
        n = len(nodes)
        if n < 2:
            raise GuessError("mds needs at least two nodes")
        if n > 4000:
            raise GuessError(f"mds compares every pair of nodes; {n} is too many (4000 at most)")
        nx = _nx()
        G = to_networkx(g, directed=False)
        wname = None
        if weight is not None:
            wf = field_of(weight, (EDGE,), "mds")
            wname = "dist"
            for a, b, d in G.edges(data=True):
                try:
                    v = float(wf.get(d["edge"]))
                except (TypeError, ValueError):
                    v = 1.0
                d["dist"] = v if math.isfinite(v) and v > 0 else 1.0
        idx = {v: i for i, v in enumerate(nodes)}
        D = np.full((n, n), np.inf)
        paths = (nx.all_pairs_dijkstra_path_length(G, weight=wname) if wname
                 else nx.all_pairs_shortest_path_length(G))
        for a, row in paths:
            for b, d in row.items():
                D[idx[a], idx[b]] = d
        finite = D[np.isfinite(D)]
        far = (finite.max() if finite.size else 0.0) + 1.0
        D[~np.isfinite(D)] = far
        J = np.eye(n) - 1.0 / n
        B = -0.5 * J @ (D ** 2) @ J
        vals, vecs = np.linalg.eigh(B)
        order = np.argsort(vals)[::-1]
        vals, vecs = vals[order], vecs[:, order]
        pos = np.clip(vals[:dims], 0, None)
        coords = vecs[:, :dims] * np.sqrt(pos)
        total = float(np.clip(vals, 0, None).sum()) or 1.0
        for k in range(dims):
            f = g.addNodeField(f"{name}{k + 1}", DOUBLE, 0.0)
            for v, i in idx.items():
                f.set(v, float(coords[i, k]))
        share = 100 * float(pos.sum()) / total
        fields = ", ".join(f"{name}{k + 1}" for k in range(dims))
        print(f"{fields}: {share:.0f}% of the distances' variance")

    # ---- geography -----------------------------------------------------------------
    @cmd
    def geoVectors(edges=None, lat=None, lon=None):
        """geoVectors() stores each edge's compass bearing (degrees from north,
        from node1 to node2) in `bearing` and its great-circle length in `km`,
        and summarises the edges (all, or the given ones): their mean length and
        its standard deviation, and the resultant vector (the edges added up
        as arrows, as east and north kilometres) with its size and bearing.
        Latitude and longitude fields are found as geoLayout finds them, or
        named: geoVectors(lat=y, lon=x). Returns the summary as a dict."""
        from .geo import LAT_NAMES, LON_NAMES
        g = gr()

        def coord(f, names, what):
            if f is not None:
                return field_of(f, (NODE,), "geoVectors")
            for nm in names:
                if nm in g.node_schema:
                    return g.node_schema[nm]
            raise GuessError(f"geoVectors needs a {what} field (looked for {', '.join(names)}); "
                             "name it, e.g. geoVectors(lat=lat, lon=lon)")
        flat, flon = coord(lat, LAT_NAMES, "latitude"), coord(lon, LON_NAMES, "longitude")

        def num(v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v if math.isfinite(v) else None
        chosen = g._edges_list() if edges is None else [e for e in elements_of(edges) if isinstance(e, Edge)]
        fb = g.addEdgeField("bearing", DOUBLE, None)
        fk = g.addEdgeField("km", DOUBLE, None)
        lengths, east, north, missing = [], 0.0, 0.0, 0
        for e in g._edges_list():
            a1, o1, a2, o2 = num(flat.get(e._n1)), num(flon.get(e._n1)), num(flat.get(e._n2)), num(flon.get(e._n2))
            if None in (a1, o1, a2, o2):
                missing += 1
                continue
            p1, p2, dl = math.radians(a1), math.radians(a2), math.radians(o2 - o1)
            c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
            km = 6371.0088 * math.acos(max(-1.0, min(1.0, c)))
            brg = (math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                           math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))
                   + 360) % 360
            fk.set(e, km)
            fb.set(e, brg)
        for e in chosen:
            km, brg = fk.get(e), fb.get(e)
            if km is None or brg is None:
                continue
            lengths.append(km)
            east += km * math.sin(math.radians(brg))
            north += km * math.cos(math.radians(brg))
        if missing:
            print(f"{missing} edges have an end without coordinates (left empty)")
        if not lengths:
            raise GuessError("geoVectors: no edges with coordinates at both ends")
        mean = sum(lengths) / len(lengths)
        sd = math.sqrt(sum((x - mean) ** 2 for x in lengths) / len(lengths))
        size = math.hypot(east, north)
        direction = (math.degrees(math.atan2(east, north)) + 360) % 360
        out = {"edges": len(lengths), "mean_km": mean, "sd_km": sd, "east_km": east, "north_km": north,
               "resultant_km": size, "resultant_bearing": direction}
        print(f"{len(lengths)} edges: mean length {mean:.1f} km (sd {sd:.1f}); "
              f"resultant {size:.1f} km towards {direction:.0f}°")
        return out

    # ---- k-brace -------------------------------------------------------------------
    @cmd
    def kBrace(k=2):
        """kBrace(k) is the k-brace: what's left after repeatedly removing every
        edge whose two ends have fewer than k neighbours in common (an edge's
        embeddedness), ignoring direction. Weakly embedded ties go; the dense
        core stays. showOnly(kBrace(2)) shows it. (It equals the (k+2)-truss:
        each remaining edge lies in at least k triangles.) Returns the edges."""
        k = int(k)
        if k < 0:
            raise GuessError("kBrace needs k >= 0")
        g = gr()
        pairs = {}
        for e in g._edges_list():
            if e._n1 is e._n2:
                continue
            key = frozenset((e._n1, e._n2))
            pairs.setdefault(key, []).append(e)
        nb = {}
        for key in pairs:
            a, b = tuple(key)
            nb.setdefault(a, set()).add(b)
            nb.setdefault(b, set()).add(a)
        alive = set(pairs)
        todo = set(alive)
        while todo:
            key = todo.pop()
            if key not in alive:
                continue
            a, b = tuple(key)
            if len(nb[a] & nb[b]) < k:
                alive.discard(key)
                nb[a].discard(b)
                nb[b].discard(a)
                for c in nb[a] | nb[b]:          # their embeddedness may have dropped
                    for x in (a, b):
                        other = frozenset((x, c))
                        if other in alive:
                            todo.add(other)
        out = sorted((e for key in alive for e in pairs[key]), key=lambda e: e._id)
        return GSet(out, f"{k}-brace: {len(out)} edges")

    # ---- field tools ---------------------------------------------------------------
    @cmd
    def castField(field, type):  # noqa: A002
        """castField(field, INTEGER) changes a field's type (INTEGER, DOUBLE,
        BOOLEAN or VARCHAR) and converts its values: "12" becomes 12, 3.7
        becomes 3, "yes" becomes true. Values that can't be converted are
        counted and left empty. One undo step."""
        g = gr()
        f = field_of(field, what="castField")
        if f.builtin or f.compute is not None or f.readonly:
            raise GuessError(f"'{f.name}' is built in; castField changes fields you added")
        try:
            new_type = normalize_type(type)
        except Exception:  # noqa: BLE001
            new_type = None
        if new_type not in (INT, DOUBLE, BOOL, STRING):
            raise GuessError("castField needs a type: INTEGER, DOUBLE, BOOLEAN or VARCHAR")
        schema = g.node_schema if f.kind == NODE else g.edge_schema
        elems = g._nodes_list() if f.kind == NODE else g._edges_list()
        if new_type == f.type:
            print(f"{f.name} is already {new_type}")
            return f

        def convert(v):
            if v is None:
                return None
            if new_type == INT:
                if isinstance(v, str):
                    s = v.strip()
                    if s.lower() in ("true", "false"):
                        return int(s.lower() == "true")
                    x = float(s)
                else:
                    x = float(v)
                if not math.isfinite(x):
                    raise ValueError
                return int(x)
            if new_type == DOUBLE:
                x = float(v.strip() if isinstance(v, str) else v)
                return x
            if new_type == BOOL:
                if isinstance(v, str):
                    s = v.strip().lower()
                    if s in ("true", "1", "yes", "t", "y"):
                        return True
                    if s in ("false", "0", "no", "f", "n", ""):
                        return False
                    raise ValueError
                return bool(v)
            if isinstance(v, float) and v.is_integer() and f.type == DOUBLE:
                return str(v)
            return str(v)

        try:
            default = convert(f.default)
        except (TypeError, ValueError):
            default = None
        values, bad = {}, 0
        for x in elems:
            if f.name not in x._vals:
                continue
            try:
                values[x] = convert(x._vals[f.name])
            except (TypeError, ValueError):
                values[x] = None
                bad += 1
        new = Field(g, f.name, f.kind, new_type, default)
        j = g.journal
        del schema[f.name]
        if j is not None:
            j.ops.append(("unfield", schema, f.name, f))
        g._emit("on_field_removed", f)
        schema[f.name] = new
        if j is not None:
            j.ops.append(("field", schema, f.name, new))
        g._emit("on_field_added", new)
        for x, v in values.items():
            if j is not None:
                j.note(x, f.name)
            if v is None:
                x._vals.pop(f.name, None)
            else:
                x._vals[f.name] = v
            g._mark(x)
        msg = f"{f.name} is now {new_type}"
        if bad:
            msg += f"; {bad} value{'s' if bad != 1 else ''} couldn't be converted (left empty)"
        print(msg)
        return new

    @cmd
    def readNames(filename, field="name"):
        """readNames("keep.txt") is the nodes whose name (or field=...) appears
        in a text file: one per line, or separated by commas, semicolons, tabs
        or spaces. showOnly(readNames("keep.txt")) keeps just them (Gephi's
        FilterFromFile). Says how many listed names matched no node."""
        g = gr()
        f = field_of(field, (NODE,), "readNames")
        try:
            with open(str(filename), encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as ex:
            raise GuessError(f"can't read {filename}: {ex.strerror or ex}") from None
        index = {}
        for n in g._nodes_list():
            v = f.get(n)
            if v is not None:
                index.setdefault(str(v).strip(), []).append(n)
        found, unmatched = {}, 0
        for line in text.splitlines():
            for tok in re.split(r"[,;\t]+", line):
                tok = tok.strip().strip('"').strip("'")
                if not tok:
                    continue
                if tok in index:
                    for n in index[tok]:
                        found[n._id] = n
                    continue
                parts = tok.split()
                hits = [p for p in parts if p in index]
                for p in hits:
                    for n in index[p]:
                        found[n._id] = n
                unmatched += len(parts) - len(hits)
        if unmatched:
            print(f"{unmatched} listed name{'s' if unmatched != 1 else ''} matched no node")
        out = sorted(found.values(), key=lambda n: n._id)
        return GSet(out, f"{len(out)} nodes listed in {filename}")

    @cmd
    def copyColors(fromGraph, field="name"):
        """copyColors("other") gives each node the colour of the node with the
        same name (or the same value of field=...) in another graph of this
        session, so the same people look the same in both (Gephi's Node Color
        Manager). Nodes with no match keep their colour. One undo step."""
        ws = getattr(session, "workspaces", None)
        src = str(fromGraph)
        if ws is None or src not in ws["stored"]:
            if ws is not None and src == ws["current"]:
                raise GuessError(f"{src!r} is the graph you're in; copyColors takes colours from another one")
            names = [ws["current"], *ws["stored"]] if ws else []
            raise GuessError(f"no graph {src!r} (graphs: {', '.join(map(repr, names))})")
        g = gr()
        f = field_of(field, (NODE,), "copyColors")
        data = ws["stored"][src]
        default = g.node_schema["color"].default      # a colour never set is the default
        colours = {}
        for rec in data.get("nodes", []):
            if not rec.get("alive", True):
                continue
            key = rec.get("name") if f.name == "name" else (rec.get("vals") or {}).get(f.name)
            col = (rec.get("vals") or {}).get("color", default)
            if key is not None and col is not None:
                colours[str(key)] = col
        cf = g.node_schema["color"]
        done = 0
        for n in g._nodes_list():
            v = f.get(n)
            if v is not None and str(v) in colours:
                cf.set(n, colours[str(v)])
                done += 1
        print(f"coloured {done} of {len(g._nodes)} nodes from {src!r}")

    # ---- generators ----------------------------------------------------------------
    def make_from(G, label, positions=None):
        g = gr()
        g.clear()
        born = any("born" in d for _v, d in G.nodes(data=True))
        if born:                                  # growth models: when each node and edge arrived
            g.addNodeField("born", "INTEGER", 0)
            g.addEdgeField("born", "INTEGER", 0)
        index = {}
        for i, v in enumerate(G.nodes):
            n = g.addNode(f"nd{i}")
            n.label = f"nd{i}"
            if born:
                n.born = G.nodes[v].get("born", 0)
            if positions is not None:
                x, y = positions[v]
                n.x, n.y = 50 + 900 * x, 50 + 900 * y
            else:
                n.x, n.y = random.random() * 500, random.random() * 500
            index[v] = n
        for a, b in G.edges():
            e = g.addEdge(index[a], index[b], False)
            if born:
                e.born = G.edges[a, b].get("born", 0)
        session.scene()
        print(f"generated {label}: {len(g._nodes)} nodes, {len(g._edges)} edges")

    def ring(G):
        n = max(G.number_of_nodes(), 1)
        return {v: (0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 + 0.5 * math.sin(2 * math.pi * i / n))
                for i, v in enumerate(G.nodes)}

    def positive(name, **vals):
        for k, v in vals.items():
            if v < 1:
                raise GuessError(f"{name}: {k} should be at least 1")

    @cmd
    def makeWattsStrogatz(n, k, p, seed=0):
        """makeWattsStrogatz(n, k, p) replaces the graph with a Watts-Strogatz
        small world: n nodes on a ring, each linked to its k nearest
        neighbours, then each edge rewired with probability p (0 keeps the
        ring lattice; 1 is close to random). Nodes are drawn on the ring."""
        nx = _nx()
        n, k, p = int(n), int(k), float(p)
        positive("makeWattsStrogatz", n=n, k=k)
        if not 0 <= p <= 1:
            raise GuessError("makeWattsStrogatz: p should be between 0 and 1")
        if k >= n:
            raise GuessError("makeWattsStrogatz: k should be smaller than n")
        G = nx.watts_strogatz_graph(n, k, p, seed=seed)
        make_from(G, "makeWattsStrogatz", ring(G))

    @cmd
    def makeBarabasiAlbertAging(n, m, aging=1.0, seed=0):
        """makeBarabasiAlbertAging(n, m, aging=1) grows a preferential-attachment
        network in which old nodes lose their appeal: each new node links to m
        existing ones, chosen with probability proportional to degree x
        age^-aging (age in steps since the node arrived). aging=0 is plain
        Barabási-Albert; larger values favour recent nodes (Dorogovtsev and
        Mendes' model). The field `born` records the step each node and edge
        arrived (0 for the starting clique), for revealUpTo."""
        nx = _nx()
        n, m, aging = int(n), int(m), float(aging)
        positive("makeBarabasiAlbertAging", n=n, m=m)
        if m >= n:
            raise GuessError("makeBarabasiAlbertAging: m should be smaller than n")
        rng = np.random.default_rng(seed)
        G = nx.complete_graph(m + 1)
        nx.set_node_attributes(G, 0, "born")
        nx.set_edge_attributes(G, 0, "born")
        born = {v: 0 for v in G.nodes}
        for t in range(m + 1, n):
            olds = list(G.nodes)
            deg = np.array([G.degree(v) for v in olds], float)
            age = np.array([t - born[v] for v in olds], float)
            w = deg * age ** (-aging)
            w = w / w.sum()
            picks = rng.choice(len(olds), size=m, replace=False, p=w)
            step = t - m                         # the seed clique is step 0
            G.add_node(t, born=step)
            born[t] = t
            for i in picks:
                G.add_edge(t, olds[int(i)], born=step)
        make_from(G, "makeBarabasiAlbertAging")

    @cmd
    def makeGeometricRandom(n, radius, seed=0):
        """makeGeometricRandom(n, radius) scatters n nodes in the unit square
        and links every two closer than radius (a random geometric graph:
        sensor and contact networks). Nodes are drawn where they fell."""
        nx = _nx()
        n, radius = int(n), float(radius)
        positive("makeGeometricRandom", n=n)
        if radius <= 0:
            raise GuessError("makeGeometricRandom: radius should be positive")
        G = nx.random_geometric_graph(n, radius, seed=seed)
        make_from(G, "makeGeometricRandom", {v: G.nodes[v]["pos"] for v in G.nodes})

    @cmd
    def makePowerlawCluster(n, m, p, seed=0):
        """makePowerlawCluster(n, m, p) grows a scale-free network with
        clustering (Holme and Kim): preferential attachment with m edges per
        new node, each followed with probability p by a triangle-closing edge."""
        nx = _nx()
        n, m, p = int(n), int(m), float(p)
        positive("makePowerlawCluster", n=n, m=m)
        if m >= n:
            raise GuessError("makePowerlawCluster: m should be smaller than n")
        if not 0 <= p <= 1:
            raise GuessError("makePowerlawCluster: p should be between 0 and 1")
        make_from(nx.powerlaw_cluster_graph(n, m, p, seed=seed), "makePowerlawCluster")

    # ---- link prediction evaluation --------------------------------------------------
    @cmd
    def evaluateLinks(method="adamic_adar", hide=0.1, seed=0, show=True):
        """evaluateLinks() tests how well predictLinks would have done: it hides
        a share of the edges (hide=0.1), scores the unlinked pairs from what's
        left, and reports precision (of the top-scored pairs, as many as were
        hidden, how many are hidden edges) and AUC (how often a hidden edge
        outscores a pair that was never linked; 0.5 is chance). The graph
        isn't changed. method as in predictLinks, or "all" to compare them."""
        g = gr()
        nodes = g._nodes_list()
        idx = {v: i for i, v in enumerate(nodes)}
        pairs = sorted({(min(idx[e._n1], idx[e._n2]), max(idx[e._n1], idx[e._n2]))
                        for e in g._edges_list() if e._n1 is not e._n2})
        hide = float(hide)
        if not 0 < hide < 1:
            raise GuessError("evaluateLinks: hide should be between 0 and 1, e.g. 0.1")
        k = max(1, int(round(hide * len(pairs))))
        if len(pairs) < 10 or k >= len(pairs):
            raise GuessError("evaluateLinks needs a graph with at least 10 edges")
        rng = random.Random(seed)
        hidden = set(rng.sample(pairs, k))
        nbrs = [set() for _ in nodes]
        for a, b in pairs:
            if (a, b) not in hidden:
                nbrs[a].add(b)
                nbrs[b].add(a)
        everything = set(pairs)
        methods = METHODS if str(method).lower() == "all" else (str(method).lower(),)
        results = {}
        n = len(nodes)
        for m in methods:
            scores = link_scores(nbrs, m)
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
            precision = sum(1 for p, _s in ranked if p in hidden) / k
            # AUC by sampling: a hidden edge against a pair that was never linked
            wins, trials = 0.0, 0
            hid = sorted(hidden)
            for _ in range(min(10000, max(1000, 20 * k))):
                h = hid[rng.randrange(len(hid))]
                for _try in range(1000):
                    a, b = rng.randrange(n), rng.randrange(n)
                    if a != b and (min(a, b), max(a, b)) not in everything:
                        break
                else:
                    break                     # (almost) complete graph: no non-edges to compare
                sh, sn = scores.get(h, 0.0), scores.get((min(a, b), max(a, b)), 0.0)
                wins += 1.0 if sh > sn else 0.5 if sh == sn else 0.0
                trials += 1
            results[m] = {"precision": precision, "auc": wins / trials if trials else None}
        if show:
            print(f"hid {k} of {len(pairs)} edges")
            for m, r in results.items():
                auc = "n/a" if r["auc"] is None else f"{r['auc']:.3f}"
                print(f"{m:>12}: precision {r['precision']:.3f}, AUC {auc}")
        return results if len(methods) > 1 else results[methods[0]]


__all__ = ["install", "LAZY", "link_scores", "METHODS"]
