"""Network statistics, communities, structural filters and path tools — the
Gephi "Statistics" and "Filters" panels as Gython commands and fields.

Node fields computed on first use (like betweenness; ``recompute(...)`` after
editing the graph):

    pagerank, hub, authority, eigenvector     link analysis (numpy; no scipy)
    closeness, harmonic, eccentricity         hop distances, ignoring direction
    clustering, triangles, coreness           local structure
    strength                                  weighted degree (sum of weights)
    component, strongcomponent                component index (0 = largest)

Commands: louvainClusters, modularity, diameter, radius, averagePathLength,
averageClustering, graphStats, recompute; kCore, egoNetwork, giantComponent,
intraEdges, interEdges, mutualEdges, groupsOfSize, showOnly, showAll;
shortestPath, heatMap, paint.
"""
import math

import numpy as np

from . import colors, igr
from .algorithms import _betweenness_edges, _betweenness_nodes, _nx, to_networkx
from .model import EDGE, INT, NODE, Edge, Field, GSet, GuessError, Node, elements_of

# --------------------------------------------------------------------------
# arrays
# --------------------------------------------------------------------------


def _arrays(graph, directed=None):
    """(nodes, src, dst, weight, directed?) with undirected edges doubled when
    the graph is treated as directed; self-loops dropped."""
    nodes = graph._nodes_list()
    idx = {n._id: i for i, n in enumerate(nodes)}
    edges = [e for e in graph._edges_list() if e._n1 is not e._n2]
    if directed is None:
        directed = any(e._directed for e in edges)
    s, t, w = [], [], []
    for e in edges:
        a, b = idx[e._n1._id], idx[e._n2._id]
        wt = _weight(e)
        s.append(a); t.append(b); w.append(wt)
        if not directed or not e._directed:
            s.append(b); t.append(a); w.append(wt)
    return (nodes, np.array(s, np.intp), np.array(t, np.intp), np.array(w, float), directed)


def _weight(e):
    v = e._vals.get("weight", 1.0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.0
    return v if math.isfinite(v) else 1.0


def _power(step, n, tol=1e-10, max_iter=1000):
    x = np.full(n, 1.0 / n)
    for _ in range(max_iter):
        nx_ = step(x)
        if np.abs(nx_ - x).sum() < n * tol:
            return nx_
        x = nx_
    return x


def _pagerank(graph, alpha=0.85):
    nodes, s, t, w, _d = _arrays(graph)
    n = len(nodes)
    if n == 0:
        return {}
    w = np.abs(w)
    out = np.bincount(s, w, n)
    dangling = out == 0
    share = np.divide(w, out[s], out=np.zeros_like(w), where=out[s] > 0)

    def step(x):
        y = alpha * np.bincount(t, x[s] * share, n)
        y += (alpha * x[dangling].sum() + 1 - alpha) / n
        return y
    return dict(zip(nodes, _power(step, n).tolist()))


def _hits(graph):
    nodes, s, t, w, _d = _arrays(graph)
    n = len(nodes)
    if n == 0:
        return {}, {}
    w = np.abs(w)
    h = np.full(n, 1.0 / n)
    for _ in range(1000):
        a = np.bincount(t, w * h[s], n)
        a /= a.sum() or 1
        h2 = np.bincount(s, w * a[t], n)
        h2 /= h2.sum() or 1
        if np.abs(h2 - h).sum() < n * 1e-10:
            h = h2
            break
        h = h2
    a = np.bincount(t, w * h[s], n)
    a /= a.sum() or 1
    return dict(zip(nodes, h.tolist())), dict(zip(nodes, a.tolist()))


def _eigenvector(graph):
    """Eigenvector centrality (in-links for directed graphs), as networkx's
    eigenvector_centrality: power iteration on A^T + I, unit length."""
    nodes, s, t, w, _d = _arrays(graph)
    n = len(nodes)
    if n == 0:
        return {}
    w = np.abs(w)
    x = np.full(n, 1.0 / n)
    for _ in range(1000):
        y = x + np.bincount(t, w * x[s], n)
        y /= np.linalg.norm(y) or 1
        if np.abs(y - x).sum() < n * 1e-8:
            x = y
            break
        x = y
    return dict(zip(nodes, x.tolist()))


# --------------------------------------------------------------------------
# hop distances (undirected), in blocks of sources
# --------------------------------------------------------------------------

def _csr(graph):
    from .layouts import _Snapshot
    snap = _Snapshot(graph)
    return snap


def _distance_stats(graph):
    """Per node: eccentricity, reachable count, sum of distances, harmonic sum."""
    if igr.module():
        return igr.distance_stats(graph)
    from .layouts import _bfs_hops
    snap = _csr(graph)
    n = snap.n
    indptr, ind = snap.csr
    ecc = np.zeros(n, np.int64)
    reach = np.zeros(n, np.int64)
    total = np.zeros(n, np.int64)
    harm = np.zeros(n)
    block = max(1, 4_000_000 // max(n, 1))
    for b0 in range(0, n, block):
        src = np.arange(b0, min(n, b0 + block))
        D = _bfs_hops(indptr, ind, n, src).astype(np.int64)
        ok = D > 0
        ecc[src] = np.where(ok, D, 0).max(1)
        reach[src] = ok.sum(1)
        total[src] = np.where(ok, D, 0).sum(1)
        harm[src] = np.where(ok, 1.0 / np.where(ok, D, 1), 0).sum(1)
    return snap.nodes, ecc, reach, total, harm


def _closeness(graph):
    nodes, _ecc, reach, total, _h = _distance_stats(graph)
    n = len(nodes)
    out = {}
    for i, nd in enumerate(nodes):
        r, tot = int(reach[i]), int(total[i])
        # networkx's closeness_centrality (Wasserman-Faust scaling for disconnected graphs)
        out[nd] = 0.0 if tot == 0 or n < 2 else (r / tot) * (r / (n - 1))
    return out


def _harmonic(graph):
    nodes, _e, _r, _t, harm = _distance_stats(graph)
    return dict(zip(nodes, harm.tolist()))


def _eccentricity(graph):
    nodes, ecc, *_ = _distance_stats(graph)
    return dict(zip(nodes, ecc.tolist())), INT


def _clustering(graph):
    if igr.module():
        return igr.clustering(graph)
    nx = _nx()
    return dict(nx.clustering(to_networkx(graph, directed=False)))


def _triangles(graph):
    if igr.module():
        return igr.triangles(graph), INT
    nx = _nx()
    return dict(nx.triangles(to_networkx(graph, directed=False))), INT


def _coreness(graph):
    if igr.module():
        return igr.coreness(graph), INT
    nx = _nx()
    G = to_networkx(graph, directed=False)
    G.remove_edges_from(list(nx.selfloop_edges(G)))
    return dict(nx.core_number(G)), INT


def _strength(graph):
    out = {n: 0.0 for n in graph._nodes_list()}
    for e in graph._edges_list():
        w = _weight(e)
        out[e._n1] += w
        out[e._n2] += w
    return out


def _components(graph, strong=False):
    if igr.module():
        return igr.components(graph, strong), INT
    nx = _nx()
    if strong:
        comps = nx.strongly_connected_components(to_networkx(graph, directed=True))
    else:
        comps = nx.connected_components(to_networkx(graph, directed=False))
    comps = sorted(comps, key=lambda c: (-len(c), min(n._id for n in c)))
    return {n: i for i, c in enumerate(comps) for n in c}, INT


def _degrank(graph):
    """Degree rank (JUNG DegreeDistributionRanker): each node's share of all
    edge ends, so the values sum to 1."""
    deg = {n: len(n._inc) for n in graph._nodes_list()}
    total = sum(deg.values()) or 1
    return {n: d / total for n, d in deg.items()}


def _rwbetweenness(graph):
    """Random-walk (current-flow) betweenness, Newman 2005: the expected number
    of times a random walk between two nodes passes through each node, averaged
    over pairs, per connected component (direction and weights ignored)."""
    snap = _csr(graph)
    out = {n: 0.0 for n in snap.nodes}
    pairs = snap.pairs
    for comp in snap.components:
        k = len(comp)
        if k < 3:
            continue
        if k > 3000:
            raise GuessError("rwbetweenness inverts an n x n matrix; this component has more than 3000 nodes")
        pos = {v: i for i, v in enumerate(comp)}
        inside = [(pos[a], pos[b]) for a, b in pairs.tolist() if a in pos and b in pos]
        L = np.zeros((k, k))
        for a, b in inside:
            L[a, b] -= 1
            L[b, a] -= 1
            L[a, a] += 1
            L[b, b] += 1
        V = np.zeros((k, k))
        V[:-1, :-1] = np.linalg.inv(L[:-1, :-1])     # potentials; the last node is ground
        contrib = np.zeros(k)
        for a, b in inside:
            d = V[a] - V[b]                           # current on edge (a, b) for pair (s, t) = |d_s - d_t|
            srt = np.sort(d)
            total = float((srt * (2 * np.arange(k) - (k - 1))).sum())   # sum over all pairs s < t
            for i in (a, b):
                # pairs where i is an endpoint count separately (as 1)
                contrib[i] += 0.5 * (total - float(np.abs(d[i] - d).sum()))
        b = (contrib + (k - 1)) / (k * (k - 1) / 2)
        for v, i in pos.items():
            out[snap.nodes[v]] = float(b[i])
    return out


LAZY = {
    "pagerank": _pagerank,
    "hub": lambda g: _hits(g)[0],
    "authority": lambda g: _hits(g)[1],
    "eigenvector": _eigenvector,
    "closeness": _closeness,
    "harmonic": _harmonic,
    "eccentricity": _eccentricity,
    "clustering": _clustering,
    "triangles": _triangles,
    "coreness": _coreness,
    "strength": _strength,
    "component": _components,
    "strongcomponent": lambda g: _components(g, strong=True),
    "betweenness": _betweenness_nodes,
    # the 2006 manual's names
    "degrank": _degrank,
    "hits": lambda g: _hits(g)[1],             # JUNG's HITS ranker: authority scores
    "rwbetweenness": _rwbetweenness,
    "knn": lambda g: igr.knn(g),
}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    g = session.graph
    for name, fn in LAZY.items():
        g.lazy_fields[(NODE, name)] = fn
    g.lazy_fields[(EDGE, "betweenness")] = _betweenness_edges

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def node(x, what="node"):
        if isinstance(x, Node):
            return x
        if isinstance(x, str) and x in g._nodes:
            return g._nodes[x]
        raise GuessError(f"{what} should be a node, got {x!r}")

    def partition(groups, label):
        groups = sorted((list(c) for c in groups), key=lambda c: (-len(c), min(n._id for n in c)))
        return GSet((GSet(sorted(c, key=lambda n: n._id), f"{label} {i}") for i, c in enumerate(groups)),
                    f"{len(groups)} {label}s")

    @cmd
    def recompute(*fields):
        """recompute(pagerank, coreness, ...) recalculates computed fields (betweenness,
        pagerank, closeness, ...) after the graph has changed; recompute() redoes
        every computed field that has been used so far."""
        names = [f.name if isinstance(f, Field) else str(f) for f in fields]
        if not names:
            names = [name for (kind, name) in g.lazy_fields
                     if name in (g.node_schema if kind == NODE else g.edge_schema)]
        for name in names:
            done = False
            for kind, schema in ((NODE, g.node_schema), (EDGE, g.edge_schema)):
                fn = g.lazy_fields.get((kind, name))
                if fn is None:
                    continue
                done = True
                if name in schema:
                    values = fn(g)
                    if isinstance(values, tuple):
                        values = values[0]
                    f = schema[name]
                    for elem in (g._nodes_list() if kind == NODE else g._edges_list()):
                        f.set(elem, values.get(elem, f.default))
                else:
                    g._lazy_field(kind, name)
            if not done:
                raise GuessError(f"'{name}' is not a computed field")

    # ---- communities ------------------------------------------------------
    @cmd
    def louvainClusters(resolution=1.0, seed=0):
        """louvainClusters() finds communities by Louvain modularity optimisation
        (Gephi's Modularity statistic) using edge weights, stores each node's
        community in the modularity_class field (0 = largest) and returns the
        communities. Try colorize(modularity_class). resolution > 1 gives more,
        smaller communities; seed=None varies the result between runs."""
        nx = _nx()
        G = to_networkx(g, directed=False)
        if G.number_of_nodes() == 0:
            return GSet(annotation="no communities")
        _positive_weights(G)
        comms = nx.community.louvain_communities(G, weight="weight", resolution=float(resolution), seed=seed)
        out = partition(comms, "community")
        f = g.addNodeField("modularity_class", INT, -1)
        for i, c in enumerate(out):
            for n in c:
                f.set(n, i)
        q = nx.community.modularity(G, [set(c) for c in out], weight="weight", resolution=float(resolution))
        print(f"modularity {q:.4f}: {len(out)} communities")
        return out

    @cmd
    def modularity(field):
        """modularity(field): the modularity Q of the partition given by a node
        field (e.g. modularity(dept), modularity(modularity_class))."""
        nx = _nx()
        if not isinstance(field, Field) or field.kind != NODE:
            raise GuessError("modularity needs a node field, e.g. modularity(dept)")
        G = to_networkx(g, directed=False)
        _positive_weights(G)
        groups = {}
        for n in g._nodes_list():
            groups.setdefault(field.get(n), set()).add(n)
        if G.number_of_edges() == 0:
            return 0.0
        return nx.community.modularity(G, list(groups.values()), weight="weight")

    # ---- whole-graph statistics -------------------------------------------
    def dist():
        nodes, ecc, reach, total, _h = _distance_stats(g)
        return nodes, ecc, reach, total

    @cmd
    def diameter():
        """The longest shortest path (in hops, ignoring direction) between any two
        connected nodes."""
        _n, ecc, _r, _t = dist()
        return int(ecc.max()) if len(ecc) else 0

    @cmd
    def radius():
        """The smallest eccentricity among nodes with at least one neighbour."""
        _n, ecc, _r, _t = dist()
        ecc = ecc[ecc > 0]
        return int(ecc.min()) if len(ecc) else 0

    @cmd
    def averagePathLength():
        """Mean shortest-path length (hops, ignoring direction) over all connected pairs."""
        _n, _e, reach, total = dist()
        pairs = int(reach.sum())
        return float(total.sum()) / pairs if pairs else 0.0

    @cmd
    def averageClustering():
        """The mean local clustering coefficient."""
        nx = _nx()
        G = to_networkx(g, directed=False)
        return nx.average_clustering(G) if G.number_of_nodes() else 0.0

    @cmd
    def graphStats():
        """Print a summary: size, density, degree, components, diameter, average
        path length, clustering, transitivity, degree assortativity, reciprocity
        (directed edges) and (if computed) modularity."""
        nn, ne = len(g._nodes), len(g._edges)
        directed = sum(e._directed for e in g._edges_list())
        comps = _components(g)[0]
        ncomp = len(set(comps.values()))
        giant = max((list(comps.values()).count(c) for c in set(comps.values())), default=0)
        nodes, ecc, reach, total = dist()
        lines = [
            f"nodes            {nn}",
            f"edges            {ne}" + (f" ({directed} directed)" if directed else ""),
            f"density          {(ne / (nn * (nn - 1) / 2) if nn > 1 else 0):.4f}",
            f"average degree   {(2 * ne / nn if nn else 0):.3f}",
            f"components       {ncomp} (largest {giant} nodes)",
            f"diameter         {int(ecc.max()) if nn else 0}",
            f"avg path length  {(float(total.sum()) / reach.sum() if reach.sum() else 0):.3f}",
            f"avg clustering   {averageClustering():.4f}",
        ]
        if "modularity_class" in g.node_schema:
            lines.append(f"modularity       {modularity(g.node_schema['modularity_class']):.4f}")
        if ne:
            ns = session.ns
            lines.append(f"transitivity     {ns['transitivity']():.4f}")
            try:
                lines.append(f"degree assort.   {ns['assortativity']():+.4f}")
            except (GuessError, ValueError, ZeroDivisionError):
                pass
            if directed:
                lines.append(f"reciprocity      {ns['reciprocity']():.4f}")
        print("\n".join(lines))

    # ---- structural filters ----------------------------------------------
    @cmd
    def kCore(k):
        """kCore(k): the nodes of the k-core — the largest subgraph in which every
        node has at least k neighbours. E.g. showOnly(kCore(3))."""
        core = _coreness(g)[0]
        return GSet((n for n in g._nodes_list() if core.get(n, 0) >= int(k)), f"{int(k)}-core")

    @cmd
    def egoNetwork(center, depth=1):
        """egoNetwork(node, depth=1): the node and everything within `depth` hops of
        it (ignoring direction)."""
        c = node(center, "egoNetwork's centre")
        seen = {c}
        frontier = [c]
        for _ in range(int(depth)):
            nxt = []
            for v in frontier:
                for e in v._inc.values():
                    w = e.opposite(v)
                    if w not in seen:
                        seen.add(w)
                        nxt.append(w)
            frontier = nxt
        return GSet(sorted(seen, key=lambda n: n._id), f"{c._name} ego network")

    @cmd
    def giantComponent():
        """The nodes of the largest connected component (ignoring direction)."""
        comp = _components(g)[0]
        return GSet((n for n in g._nodes_list() if comp.get(n) == 0), "giant component")

    def _edge_split(field, same):
        if not isinstance(field, Field) or field.kind != NODE:
            raise GuessError("needs a node field, e.g. intraEdges(dept)")
        return GSet((e for e in g._edges_list()
                     if (field.get(e._n1) == field.get(e._n2)) == same),
                    f"{'within' if same else 'between'} {field.name}")

    @cmd
    def intraEdges(field):
        """intraEdges(field): edges whose two endpoints share the field's value
        (e.g. edges inside each community)."""
        return _edge_split(field, True)

    @cmd
    def interEdges(field):
        """interEdges(field): edges joining nodes with different values of the field."""
        return _edge_split(field, False)

    @cmd
    def mutualEdges():
        """Directed edges whose reverse edge also exists."""
        pairs = {(e._n1._id, e._n2._id) for e in g._edges_list() if e._directed}
        return GSet((e for e in g._edges_list()
                     if e._directed and (e._n2._id, e._n1._id) in pairs), "mutual edges")

    @cmd
    def groupsOfSize(field, smallest, largest=None):
        """groupsOfSize(field, min[, max]): the nodes (or edges) whose value of
        field is shared by at least min (and at most max) elements — e.g. drop
        tiny communities with showOnly(groupsOfSize(modularity_class, 5))."""
        if not isinstance(field, Field):
            raise GuessError("groupsOfSize needs a field")
        groups = {}
        for x in field.elements():
            groups.setdefault(field.get(x), []).append(x)
        hi = math.inf if largest is None else int(largest)
        return GSet((x for grp in groups.values() if int(smallest) <= len(grp) <= hi for x in grp),
                    f"{field.name} groups of size {smallest}+")

    @cmd
    def showOnly(seq):
        """showOnly(seq) hides every node and edge not in seq (nodes in seq keep the
        edges between them; edges in seq keep their endpoints). Undo with showAll()."""
        keep_n, keep_e = set(), set()
        for x in elements_of(seq):
            if isinstance(x, Node):
                keep_n.add(x)
            elif isinstance(x, Edge):
                keep_e.add(x)
                keep_n.update((x._n1, x._n2))
        only_edges = not any(isinstance(x, Node) for x in elements_of(seq))
        for n in g._nodes_list():
            n.visible = n in keep_n
        for e in g._edges_list():
            e.visible = e in keep_e if only_edges else (e in keep_e or (e._n1 in keep_n and e._n2 in keep_n))

    @cmd
    def showAll():
        """Make every node and edge visible again."""
        for n in g._nodes_list():
            n.visible = True
        for e in g._edges_list():
            e.visible = True

    # ---- paths -------------------------------------------------------------
    @cmd
    def shortestPath(source, target, weighted=False):
        """shortestPath(a, b): the nodes and edges of a shortest path from a to b
        (following edge direction), or an empty set if there is none.
        weighted=true uses edge weights as lengths. E.g. shortestPath(a, b).color = red"""
        nx = _nx()
        a, b = node(source), node(target)
        G = to_networkx(g)
        try:
            path = nx.shortest_path(G, a, b, weight=(lambda u, v, d: abs(d["weight"]) or 1e-9) if weighted else None)
        except nx.NetworkXNoPath:
            print(f"no path from {a._name} to {b._name}")
            return GSet(annotation="no path")
        out = GSet(annotation=f"path {a._name} to {b._name}")
        for i, v in enumerate(path):
            out.append(v)
            if i + 1 < len(path):
                out.append(_best_edge(v, path[i + 1], G.is_directed()))
        return out

    @cmd
    def heatMap(center, near="#d7191c", far="#2c7bb6", unreachable="#bdbdbd", middle="#8e5fbf", spread=True):
        """heatMap(node) colours every node by its distance (hops, ignoring
        direction) from node: red at the node, through violet, to blue for the
        farthest, grey if unreachable; the distance is stored in the hops field
        (-1 if unreachable). spread=True (default) spaces the colours by how
        many nodes are at each distance, so every band is visible;
        spread=False spaces them by distance alone. near, middle, far and
        unreachable change the colours (middle=None: a straight blend). Gephi's
        heat map tool."""
        c = node(center, "heatMap's centre")
        hops = {c: 0}
        frontier = [c]
        d = 0
        while frontier:
            d += 1
            nxt = []
            for v in frontier:
                for e in v._inc.values():
                    w = e.opposite(v)
                    if w not in hops:
                        hops[w] = d
                        nxt.append(w)
            frontier = nxt
        f = g.addNodeField("hops", INT, -1)
        top = max(hops.values()) or 1
        stops = [colors.parse(near, (215, 25, 28, 255))]
        if middle is not None:
            stops.append(colors.parse(middle, (245, 184, 65, 255)))
        stops.append(colors.parse(far, (44, 123, 182, 255)))
        if spread:
            # each distance's position in the cumulative share of reachable nodes
            from collections import Counter
            count = Counter(hops.values())
            total, below, t_of = len(hops), 0, {}
            for h in sorted(count):
                t_of[h] = (below + count[h] / 2) / total
                below += count[h]
            lo, hi = t_of[0], t_of[max(count)]
            t_of = {h: (t - lo) / ((hi - lo) or 1) for h, t in t_of.items()}
        else:
            t_of = {h: h / top for h in set(hops.values())}
        for n in g._nodes_list():
            h = hops.get(n, -1)
            f.set(n, h)
            n.color = colors.mix_stops(stops, t_of[h]) if h >= 0 else colors.normalize(unreachable)

    @cmd
    def paint(center, color, depth=0):
        """paint(node, color, depth=0) colours a node, and with depth=k everything
        within k hops of it (Gephi's brush)."""
        for n in egoNetwork(center, depth):
            n.color = color


def _positive_weights(G):
    """Louvain/modularity need non-negative weights; zero or negative become tiny."""
    for _a, _b, d in G.edges(data=True):
        w = d.get("weight", 1.0)
        d["weight"] = w if isinstance(w, (int, float)) and w > 0 else 1e-9


def _best_edge(u, v, directed):
    best = None
    for e in u._inc.values():
        if e.opposite(u) is not v:
            continue
        if directed and e._directed and e._n1 is not u:
            continue
        if best is None or _weight(e) < _weight(best):
            best = e
    return best
