"""igraph as GUESS's engine for heavy computations, plus what only igraph has.

igraph (C core) ships with Pyodide; the page loads it in the background after
start-up. When it is there, these existing statistics use it (same results,
much faster on graphs of 10k+ nodes): betweenness (nodes and edges),
closeness, harmonic, eccentricity, diameter, radius, averagePathLength,
clustering, triangles, coreness, component, strongcomponent. Until then, or
after useIgraph(false), the networkx / numpy versions run.

New commands (igraph only):
    leidenClusters, infomapClusters, walktrapClusters, fastGreedyClusters,
    labelPropagationClusters, eigenvectorClusters, fluidClusters,
    voronoiClusters, spinglassClusters, optimalClusters, cutDendrogram,
    cohesiveBlocks
    drlLayout, lglLayout, umapLayout, dhLayout, bipartiteLayout
    similarTo, predictLinks, findPattern, minCut, maxFlow,
    personalizedPagerank, dominatorTree, largestCliques, maxMatching
and the node field knn (average degree of the neighbours).
Pure-Python helpers here too: simplify, rewire.
"""
import math
import random

import numpy as np

from .model import DOUBLE, EDGE, INT, STRING, Field, GSet, GuessError, Node, elements_of

ENABLED = [True]



def _plural(word):
    """community -> communities, cluster -> clusters."""
    return word[:-1] + "ies" if word.endswith("y") and word[-2:-1] not in "aeiou" else word + "s"

def module():
    """The igraph module if it is loaded and enabled, else None."""
    if not ENABLED[0]:
        return None
    try:
        import igraph
    except ImportError:
        import importlib
        importlib.invalidate_caches()        # the page may have just installed it
        try:
            import igraph
        except ImportError:
            return None
    return igraph


def need(what):
    ig = module()
    if ig is None:
        if not ENABLED[0]:
            raise GuessError(f"{what} needs igraph; useIgraph(true) turns it back on")
        raise GuessError(f"{what} needs igraph, which loads in the background a few seconds "
                         "after GUESS starts; try again in a moment")
    return ig


def _weight(e):
    v = e._vals.get("weight", 1.0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.0
    return v if math.isfinite(v) else 1.0


class IG:
    """The GUESS graph as an igraph Graph on the same nodes (vertex i =
    nodes[i]). Parallel edges merge into one (weights summed) and self-loops
    are dropped, as networkx's simple graphs do; `pairs[k]` lists the GUESS
    edges behind igraph edge k. directed=None follows the graph (directed if
    any edge is); undirected edges then go both ways."""

    def __init__(self, graph, directed=False, nodes=None):
        ig = need("this command")
        self.graph = graph
        self.nodes = list(nodes) if nodes is not None else graph._nodes_list()
        self.index = {n._id: i for i, n in enumerate(self.nodes)}
        edges = [e for e in graph._edges_list()
                 if e._n1._id in self.index and e._n2._id in self.index and e._n1 is not e._n2]
        if directed is None:
            directed = any(e._directed for e in edges)
        self.directed = directed
        merged = {}
        for e in edges:
            a, b = self.index[e._n1._id], self.index[e._n2._id]
            arcs = [(a, b)] if (not directed or e._directed) else [(a, b), (b, a)]
            for x, y in arcs:
                key = (x, y) if directed else (min(x, y), max(x, y))
                slot = merged.setdefault(key, [0.0, []])
                slot[0] += _weight(e)
                slot[1].append(e)
        keys = list(merged)
        self.pairs = [merged[k][1] for k in keys]
        self.G = ig.Graph(n=len(self.nodes), edges=keys, directed=directed)
        self.G.es["weight"] = [merged[k][0] for k in keys]

    def node_values(self, values):
        return {n: v for n, v in zip(self.nodes, values)}

    def edge_values(self, values):
        out = {}
        for es, v in zip(self.pairs, values):
            for e in es:
                out[e] = max(v, out.get(e, v))
        return out

    def vid(self, n):
        return self.index[n._id]

    def positive_weights(self):
        """Weights for algorithms that need them positive (communities)."""
        w = self.G.es["weight"]
        return [x if x > 0 else 1e-9 for x in w] if w else None


# ---- faster versions of existing statistics ---------------------------------

def betweenness_nodes(graph):
    I = IG(graph, directed=None)
    return I.node_values(I.G.betweenness(directed=I.directed))


def betweenness_edges(graph):
    I = IG(graph, directed=None)
    return I.edge_values(I.G.edge_betweenness(directed=I.directed))


def distance_stats(graph):
    """(nodes, eccentricity, reachable count, sum of distances, harmonic sum),
    in hops ignoring direction, as analysis._distance_stats returns."""
    I = IG(graph, directed=False)
    G, n = I.G, len(I.nodes)
    ecc = np.array(G.eccentricity(), np.int64) if n else np.zeros(0, np.int64)
    comp = G.connected_components()
    sizes = np.array(comp.sizes())
    reach = (sizes[np.array(comp.membership, np.int64)] - 1) if n else np.zeros(0, np.int64)
    clo = np.array(G.closeness(normalized=True), float) if n else np.zeros(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        total = np.where((reach > 0) & np.isfinite(clo) & (clo > 0), np.rint(reach / clo), 0).astype(np.int64)
    harm = np.array(G.harmonic_centrality(normalized=False), float) if n else np.zeros(0)
    return I.nodes, ecc, reach.astype(np.int64), total, harm


def clustering(graph):
    I = IG(graph, directed=False)
    return I.node_values(I.G.transitivity_local_undirected(mode="zero"))


def triangles(graph):
    I = IG(graph, directed=False)
    counts = [0] * len(I.nodes)
    for tri in I.G.list_triangles():
        for v in tri:
            counts[v] += 1
    return I.node_values(counts)


def coreness(graph):
    I = IG(graph, directed=False)
    return I.node_values(I.G.coreness())


def components(graph, strong=False):
    I = IG(graph, directed=True if strong else False)
    cl = I.G.connected_components(mode="strong" if strong else "weak")
    groups = [[I.nodes[v] for v in c] for c in cl]
    groups.sort(key=lambda c: (-len(c), min(n._id for n in c)))
    return {n: i for i, c in enumerate(groups) for n in c}


def knn(graph):
    """Average degree of each node's neighbours (0 for isolated nodes)."""
    ig = module()
    if ig is None:
        from .algorithms import _nx, to_networkx
        nx = _nx()
        return {n: float(v) for n, v in nx.average_neighbor_degree(to_networkx(graph, directed=False)).items()}
    I = IG(graph, directed=False)
    vals, _ = I.G.knn()
    return I.node_values([0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v) for v in vals])


# ---- helpers for commands -------------------------------------------------

class _Seeded:
    """igraph's random number generator seeded for one call (seed=None: free)."""

    def __init__(self, seed):
        self.seed = seed

    def __enter__(self):
        if self.seed is not None:
            module().set_random_number_generator(random.Random(self.seed))

    def __exit__(self, *exc):
        if self.seed is not None:
            module().set_random_number_generator(random)


def install(session):
    from .layouts import BOX, _Layouts
    lay = _Layouts(session)
    state = {"dendrogram": None}

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def node(x):
        return _node_of(x)

    def _node_of(x):
        if isinstance(x, Node):
            return x
        if isinstance(x, str) and x in g()._nodes:
            return g()._nodes[x]
        raise GuessError(f"expected a node, got {x!r}")

    def field_arg(f, what):
        from .model import NODE, as_field
        return as_field(g(), f, what, (NODE,))

    @cmd
    def useIgraph(on=True):
        """useIgraph(false) makes the statistics use networkx / numpy instead of
        igraph (to compare results or work around a problem); useIgraph() turns
        igraph back on. Prints which engine is active."""
        ENABLED[0] = bool(on)
        try:
            import igraph
            loaded = f"igraph {igraph.__version__} loaded"
        except ImportError:
            loaded = "igraph not loaded yet"
        print(f"engine: {'igraph' if module() else 'networkx/numpy'} ({loaded})")

    # ---- communities ----------------------------------------------------------
    def store(I, membership, fieldname, label, show=True):
        """Write a membership list as an INT field (0 = largest community) and
        return the communities as sets; print modularity and count."""
        groups = {}
        for v, c in enumerate(membership):
            groups.setdefault(c, []).append(I.nodes[v])
        ordered = sorted(groups.values(), key=lambda c: (-len(c), min(n._id for n in c)))
        f = g().addNodeField(fieldname, INT, -1)
        renum = [0] * len(I.nodes)
        for i, c in enumerate(ordered):
            for n in c:
                f.set(n, i)
                renum[I.vid(n)] = i
        q = I.G.modularity(renum, weights=I.positive_weights()) if I.G.ecount() else 0.0
        if show:
            print(f"modularity {q:.4f}: {len(ordered)} communities in {fieldname}")
        return GSet((GSet(sorted(c, key=lambda n: n._id), f"{label} {i}") for i, c in enumerate(ordered)),
                    f"{len(ordered)} {_plural(label)}")

    def undirected():
        I = IG(g(), directed=False)
        if not I.nodes:
            raise GuessError("the graph is empty")
        return I

    @cmd
    def leidenClusters(resolution=1.0, objective="modularity", iterations=-1, seed=0):
        """leidenClusters() finds communities with the Leiden algorithm (better
        than Louvain: every community is internally connected) and stores them
        in leiden_class (0 = largest). resolution > 1 gives more, smaller
        communities. objective="CPM" (constant Potts model) avoids modularity's
        resolution limit; its resolution is a density, typically 0.001-0.1.
        iterations=-1 runs until stable; seed=None varies the result."""
        need("leidenClusters")
        I = undirected()
        obj = "modularity" if str(objective).lower() == "modularity" else "CPM"
        with _Seeded(seed):
            cl = I.G.community_leiden(objective_function=obj, weights=I.positive_weights(),
                                      resolution=float(resolution), n_iterations=int(iterations))
        return store(I, cl.membership, "leiden_class", "community")

    @cmd
    def infomapClusters(trials=10, seed=0):
        """infomapClusters() finds communities by Infomap (how a random walker's
        flow stays inside groups), following edge direction and weights; a good
        choice for directed networks such as citations or web links. Stored in
        infomap_class."""
        need("infomapClusters")
        I = IG(g(), directed=None)
        with _Seeded(seed):
            cl = I.G.community_infomap(edge_weights=I.positive_weights(), trials=int(trials))
        return store(I, cl.membership, "infomap_class", "community")

    def cut(dendrogram, I, count):
        """A clustering with `count` groups; a graph in pieces can't have fewer
        groups than components, so the count is raised to that."""
        if count is None:
            return dendrogram.as_clustering()
        least = len(I.nodes) - len(dendrogram.merges)
        count = max(1, min(int(count), len(I.nodes)))
        if count < least:
            print(f"the graph has {least} separate parts, so {least} is the fewest communities")
            count = least
        return dendrogram.as_clustering(count)

    def dendro(dendrogram, I, count, fieldname, label):
        state["dendrogram"] = (dendrogram, I, fieldname, label)
        session.last_dendrogram = {"nodes": list(I.nodes), "merges": [tuple(m) for m in dendrogram.merges],
                                   "title": f"{fieldname.split('_')[0]} hierarchy"}
        return store(I, cut(dendrogram, I, count).membership, fieldname, label)

    @cmd
    def walktrapClusters(count=None, steps=4):
        """walktrapClusters() groups nodes that short random walks (steps long)
        tend to stay among, building a hierarchy; count=None cuts it where
        modularity is highest, walktrapClusters(8) gives 8 communities.
        Stored in walktrap_class; cutDendrogram(n) re-cuts it."""
        need("walktrapClusters")
        I = undirected()
        return dendro(I.G.community_walktrap(weights=I.positive_weights(), steps=int(steps)),
                      I, count, "walktrap_class", "community")

    @cmd
    def fastGreedyClusters(count=None):
        """fastGreedyClusters() merges communities greedily by modularity
        (Clauset-Newman-Moore), building a hierarchy; count as in
        walktrapClusters. Stored in fastgreedy_class; cutDendrogram(n) re-cuts."""
        need("fastGreedyClusters")
        I = undirected()
        return dendro(I.G.community_fastgreedy(weights=I.positive_weights()),
                      I, count, "fastgreedy_class", "community")

    @cmd
    def cutDendrogram(count):
        """cutDendrogram(n) re-cuts the hierarchy of the last walktrapClusters or
        fastGreedyClusters into n communities (same field), e.g. driven by a
        Slider to explore coarser and finer groupings."""
        if state["dendrogram"] is None:
            raise GuessError("run walktrapClusters() or fastGreedyClusters() first")
        dendrogram, I, fieldname, label = state["dendrogram"]
        if [n._id for n in I.nodes] != [n._id for n in g()._nodes_list()]:
            raise GuessError("the graph changed since the clustering; run it again")
        return store(I, cut(dendrogram, I, count).membership, fieldname, label)

    @cmd
    def labelPropagationClusters(field=None, seed=0):
        """labelPropagationClusters() finds communities very fast (linear time) by
        letting each node adopt its neighbours' most common label; good for very
        large graphs, rougher than Leiden. labelPropagationClusters(field)
        starts from the values of a field and keeps those nodes fixed, filling in
        the rest (semi-supervised). Stored in lpa_class."""
        need("labelPropagationClusters")
        I = undirected()
        initial = fixed = None
        if field is not None:
            f = field_arg(field, "labelPropagationClusters")
            codes = {}
            initial = []
            for n in I.nodes:
                v = f.get(n)
                initial.append(-1 if v is None or v == "" else codes.setdefault(v, len(codes)))
            fixed = [x >= 0 for x in initial]
            if not codes:
                raise GuessError(f"no node has a value of {f.name}")
        with _Seeded(seed):
            cl = I.G.community_label_propagation(weights=I.positive_weights(), initial=initial, fixed=fixed)
        return store(I, cl.membership, "lpa_class", "community")

    @cmd
    def eigenvectorClusters(count=None):
        """eigenvectorClusters() splits the graph by the leading eigenvector of
        the modularity matrix (Newman), repeatedly; count limits the number of
        communities. Stored in eigen_class."""
        need("eigenvectorClusters")
        I = undirected()
        last = None
        for attempt in range(5):        # ARPACK starts from a random vector: seed it, and retry if it doesn't converge
            try:
                with _Seeded(attempt):
                    cl = I.G.community_leading_eigenvector(clusters=None if count is None else int(count),
                                                           weights=I.positive_weights())
                break
            except Exception as ex:  # noqa: BLE001 - igraph's InternalError
                last = ex
        else:
            raise GuessError(f"eigenvectorClusters: the eigenvector calculation didn't converge ({last})")
        return store(I, cl.membership, "eigen_class", "community")

    @cmd
    def fluidClusters(count, seed=0):
        """fluidClusters(count) splits a connected graph into exactly count communities
        (fluid communities). On a graph in pieces run it on one part, e.g. in
        subgraph(giantComponent()). Stored in fluid_class."""
        need("fluidClusters")
        I = undirected()
        if not I.G.is_connected():
            raise GuessError("fluidClusters needs a connected graph: try subgraph(giantComponent()) first")
        G = I.G.copy()
        del G.es["weight"]                   # the algorithm takes no weights
        with _Seeded(seed):
            cl = G.community_fluid_communities(no_of_communities=int(count))
        return store(I, cl.membership, "fluid_class", "community")

    @cmd
    def voronoiClusters():
        """voronoiClusters() picks central "generator" nodes automatically and
        gives every other node to its nearest one (by weighted distance); the
        communities are stored in voronoi_class and the generators returned."""
        need("voronoiClusters")
        I = undirected()
        w = I.positive_weights()
        lengths = [1.0 / x for x in w] if w else None
        cl = I.G.community_voronoi(lengths=lengths, weights=w)
        store(I, cl.membership, "voronoi_class", "community")
        gens = getattr(cl, "generators", None) or []
        return GSet(sorted((I.nodes[v] for v in gens), key=lambda n: n._id), "generator nodes")

    @cmd
    def spinglassClusters(spins=25, gamma=1.0, seed=0):
        """spinglassClusters() finds communities by simulated annealing of a spin
        model (Reichardt-Bornholdt); handles negative edge weights (signed
        networks). Slow: for graphs up to about 2,000 nodes. spins is the most
        communities allowed, gamma > 1 favours smaller ones. Stored in
        spinglass_class. Needs a connected graph."""
        need("spinglassClusters")
        I = undirected()
        if len(I.nodes) > 5000:
            raise GuessError("spinglassClusters is too slow for more than 5,000 nodes; try leidenClusters()")
        if not I.G.is_connected():
            raise GuessError("spinglassClusters needs a connected graph: try subgraph(giantComponent()) first")
        neg = any(x < 0 for x in I.G.es["weight"])
        with _Seeded(seed):
            cl = I.G.community_spinglass(weights=I.G.es["weight"], spins=int(spins), gamma=float(gamma),
                                         implementation="negative" if neg else "original")
        return store(I, cl.membership, "spinglass_class", "community")

    @cmd
    def optimalClusters():
        """optimalClusters() finds the partition with the highest possible
        modularity (exact, by integer programming): only for small graphs (up
        to about 100 nodes), as a baseline for the other methods. Stored in
        optimal_class."""
        need("optimalClusters")
        I = undirected()
        if len(I.nodes) > 150:
            raise GuessError("optimalClusters is exact and exponential: only for graphs up to about 150 nodes")
        try:
            cl = I.G.community_optimal_modularity(weights=I.positive_weights())
        except Exception as e:  # noqa: BLE001 - igraph built without GLPK
            raise GuessError(f"optimalClusters isn't available here: {e}") from None
        return store(I, cl.membership, "optimal_class", "community")

    @cmd
    def cohesiveBlocks():
        """cohesiveBlocks() finds nested groups that stay connected after removing
        any k-1 nodes (Moody and White's cohesive blocking): a structural view
        that k-cores miss. Each node's highest cohesion is stored in `cohesion`;
        the blocks are returned, most cohesive last. Slow beyond a few thousand
        nodes."""
        need("cohesiveBlocks")
        I = undirected()
        if len(I.nodes) > 5000:
            raise GuessError("cohesiveBlocks is too slow for more than 5,000 nodes")
        cb = I.G.cohesive_blocks()
        f = g().addNodeField("cohesion", INT, 0)
        best = [0] * len(I.nodes)
        blocks = []
        for i, members in enumerate(cb):
            k = cb.cohesion(i)
            for v in members:
                best[v] = max(best[v], k)
            blocks.append((k, GSet(sorted((I.nodes[v] for v in members), key=lambda n: n._id), f"block {i} (cohesion {k})")))
        for v, k in enumerate(best):
            f.set(I.nodes[v], k)
        blocks.sort(key=lambda kb: (kb[0], len(kb[1])))
        print(f"{len(blocks)} blocks, highest cohesion {max(best) if best else 0}")
        return GSet((b for _k, b in blocks), f"{len(blocks)} cohesive blocks")

    # ---- layouts ----------------------------------------------------------
    def place(I, layout, s):
        P = np.array(layout.coords, float)[:, :2] if len(I.nodes) else np.zeros((0, 2))
        if len(P):
            lo, hi = P.min(0), P.max(0)
            span = float(max(hi - lo)) or 1.0
            P = (P - lo) / span * (BOX - 100) + 50
        lay.apply(s, P)

    def layout_graph():
        s = lay.snap()
        return s, IG(g(), directed=False, nodes=s.nodes)

    @cmd
    def drlLayout(preset="default", seed=0):
        """drlLayout() is a force-directed layout for large graphs (DrL /
        OpenOrd): tens of thousands of nodes in seconds, with clusters pulled
        well apart. preset: "default", "coarsen" (more separated clusters),
        "coarsest", "refine" (polish an existing layout) or "final"."""
        need("drlLayout")
        s, I = layout_graph()
        options = {"default": "default", "coarsen": "coarsen", "coarsest": "coarsest",
                   "refine": "refine", "final": "final"}.get(str(preset).lower())
        if options is None:
            raise GuessError('preset should be "default", "coarsen", "coarsest", "refine" or "final"')
        seed_pos = s.pos.tolist() if options in ("refine", "final") else None
        with _Seeded(seed):
            layout = I.G.layout_drl(weights=I.positive_weights(), seed=seed_pos, options=options)
        place(I, layout, s)

    @cmd
    def lglLayout(root=None, seed=0):
        """lglLayout() is the Large Graph Layout: grows the drawing outward from
        a root node (default: a random one, or lglLayout(v1)), suited to big,
        tree-like networks."""
        need("lglLayout")
        s, I = layout_graph()
        r = I.vid(node(root)) if root is not None else None
        import warnings
        if not I.G.is_connected():
            print("lglLayout: the graph is in pieces, which LGL lays out on top of each other; "
                  "binPackLayout() afterwards separates them")
        with _Seeded(seed), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            layout = I.G.layout_lgl(root=r)
        place(I, layout, s)

    @cmd
    def umapLayout(minDist=0.01, epochs=500, seed=0):
        """umapLayout() places nodes by UMAP on the graph's connections: tight,
        well-separated islands for clusters. Edge weights count as similarity.
        minDist (0..1) is how tightly points may pack; more epochs, more
        polish."""
        need("umapLayout")
        s, I = layout_graph()
        w = I.G.es["weight"]
        top = max(w) if w else 1.0
        dist = [max(0.0, 1.0 - x / top) for x in w] if w and top > 0 else None
        with _Seeded(seed):
            layout = I.G.layout_umap(dist=dist, min_dist=float(minDist), epochs=int(epochs))
        place(I, layout, s)

    @cmd
    def dhLayout(seed=0):
        """dhLayout() is the Davidson-Harel layout: simulated annealing that
        spreads nodes evenly and avoids edge crossings and nodes on edges. Slow
        but tidy: for figures of up to a few hundred nodes."""
        need("dhLayout")
        s, I = layout_graph()
        if len(I.nodes) > 2000:
            raise GuessError("dhLayout is meant for small graphs (up to about 2,000 nodes); try drlLayout()")
        with _Seeded(seed):
            layout = I.G.layout_davidson_harel()
        place(I, layout, s)

    @cmd
    def bipartiteLayout(field, hgap=1, vgap=1):
        """bipartiteLayout(field) draws a two-mode network in two rows (by a field
        with two values, e.g. bipartite in makeSample("davis")), ordering each
        row to reduce edge crossings. Without igraph (still loading, or
        turned off) the rows are ordered by the barycenter heuristic instead."""
        f = field_arg(field, "bipartiteLayout")
        if module() is None:
            return _bipartite_barycenter(f)
        s, I = layout_graph()
        vals = [f.get(n) for n in I.nodes]
        kinds = sorted({v for v in vals if v is not None}, key=str)
        if len(kinds) != 2:
            raise GuessError(f"bipartiteLayout needs a field with exactly two values; {f.name} has {len(kinds)}")
        types = [v == kinds[1] for v in vals]
        layout = I.G.layout_bipartite(types=types, hgap=float(hgap), vgap=float(vgap))
        P = np.array(layout.coords, float)
        if len(P):
            P[:, 0] = (P[:, 0] - P[:, 0].min()) / (np.ptp(P[:, 0]) or 1) * (BOX - 100) + 50
            P[:, 1] = np.where(P[:, 1] > P[:, 1].min(), BOX * 0.7, BOX * 0.3)
        lay.apply(s, P)

    def _bipartite_barycenter(f):
        """Two rows; each node placed at the mean position of its neighbours in the
        other row, alternating rows for a few sweeps (Sugiyama's barycenter rule)."""
        s = lay.snap()
        nodes = list(s.nodes)
        vals = [f.get(n) for n in nodes]
        kinds = sorted({v for v in vals if v is not None}, key=str)
        if len(kinds) != 2:
            raise GuessError(f"bipartiteLayout needs a field with exactly two values; {f.name} has {len(kinds)}")
        idx = {id(n): i for i, n in enumerate(nodes)}
        nbrs = [[] for _ in nodes]
        for e in g()._edges_list():
            a, b = idx.get(id(e._n1)), idx.get(id(e._n2))
            if a is not None and b is not None and a != b:
                nbrs[a].append(b)
                nbrs[b].append(a)
        rows = [[i for i, v in enumerate(vals) if v == k] for k in kinds]
        rows = [sorted(r, key=lambda i: (-len(nbrs[i]), str(nodes[i].name))) for r in rows]
        pos = {}
        for r in rows:
            for k, i in enumerate(r):
                pos[i] = k / max(len(r) - 1, 1)
        for sweep in range(12):
            r = rows[sweep % 2]
            bary = {i: (sum(pos[j] for j in nbrs[i]) / len(nbrs[i]) if nbrs[i] else pos[i]) for i in r}
            r.sort(key=lambda i: (bary[i], pos[i]))
            for k, i in enumerate(r):
                pos[i] = k / max(len(r) - 1, 1)
        P = np.zeros((len(nodes), 2))
        for i, v in enumerate(vals):
            P[i, 0] = pos.get(i, 0.5) * (BOX - 100) + 50
            P[i, 1] = BOX * (0.3 if v == kinds[0] else 0.7 if v == kinds[1] else 0.5)
        lay.apply(s, P)

    # ---- similarity and link prediction --------------------------------------
    @cmd
    def similarTo(node, method="jaccard", top=10, alpha=0.9):
        """similarTo(v1) scores every node by how much its neighbourhood overlaps
        v1's, stores the score in the field `similarity` and returns the `top`
        most similar nodes. method: "jaccard" (shared neighbours / all
        neighbours of either), "dice" (2 x shared / sum of degrees), or
        "adamic_adar" (shared neighbours, rare ones counting more), or
        "regular": regular equivalence (Leicht, Holme and Newman), where nodes
        are similar if their neighbours are similar, so nodes with the same
        role score high even with no neighbours in common; alpha (below 1)
        weighs longer paths. Direction is ignored."""
        gr = g()
        me = _node_of(node)
        if str(method).lower() == "regular":
            from .metrics import regular_similarity
            nodes, S = regular_similarity(gr, alpha)
            i = nodes.index(me)
            f = gr.addNodeField("similarity", DOUBLE, 0.0)
            for j, x in enumerate(nodes):
                f.set(x, 0.0 if x is me else float(S[i, j]))
            ranked = sorted((x for x in nodes if x is not me), key=lambda x: (-float(S[i, nodes.index(x)]), x._id))
            return GSet(ranked[:int(top)], f"most similar to {me._name}")
        nbrs = {}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            nbrs.setdefault(e._n1, set()).add(e._n2)
            nbrs.setdefault(e._n2, set()).add(e._n1)
        mine = nbrs.get(me, set())
        m = str(method).lower()
        if m not in ("jaccard", "dice", "adamic_adar", "adamicadar", "aa"):
            raise GuessError('method should be "jaccard", "dice", "adamic_adar" or "regular"')
        scores = {}
        for z in mine:                                   # only nodes sharing a neighbour score > 0
            for other in nbrs.get(z, ()):
                if other is not me:
                    scores.setdefault(other, 0.0)
        for other in scores:
            theirs = nbrs.get(other, set())
            common = mine & theirs
            if m == "jaccard":
                scores[other] = len(common) / len(mine | theirs)
            elif m == "dice":
                scores[other] = 2 * len(common) / (len(mine) + len(theirs))
            else:
                scores[other] = sum(1 / math.log(len(nbrs[z])) for z in common if len(nbrs[z]) > 1)
        f = gr.addNodeField("similarity", DOUBLE, 0.0)
        for x in gr._nodes_list():
            f.set(x, float(scores.get(x, 0.0)))
        ranked = sorted((x for x, v in scores.items() if v > 0), key=lambda x: (-scores[x], x._id))
        return GSet(ranked[:int(top)], f"most similar to {me._name}")

    @cmd
    def predictLinks(top=20, method="adamic_adar", show=True, add=False):
        """predictLinks() lists likely missing edges: pairs of nodes that aren't
        linked but share neighbours, scored by "adamic_adar" (shared neighbours,
        rare ones counting more), "jaccard", "common" (count of shared
        neighbours) or "resource" (resource allocation). Returns the `top`
        pairs as (node, node, score), best first. add=true also adds them as
        edges, marked with the method's name in the edge field `predicted`
        (showOnly(predicted != None) shows them; undo() takes them away).
        evaluateLinks() tests how well a method would have predicted."""
        need("predictLinks")
        I = undirected()
        G = I.G
        nbrs = [set(G.neighbors(v)) for v in range(len(I.nodes))]
        deg = [len(s) for s in nbrs]
        m = str(method).lower()
        if m not in ("adamic_adar", "jaccard", "common", "resource"):
            raise GuessError('method should be "adamic_adar", "jaccard", "common" or "resource"')
        scores = {}
        for z in range(len(I.nodes)):
            if deg[z] < 2:
                continue
            inc = {"adamic_adar": 1 / math.log(deg[z]), "resource": 1 / deg[z]}.get(m, 1.0)
            ns = sorted(nbrs[z])
            for i, a in enumerate(ns):
                for b in ns[i + 1:]:
                    if b not in nbrs[a]:
                        scores[(a, b)] = scores.get((a, b), 0.0) + inc
        if m == "jaccard":
            scores = {(a, b): c / len(nbrs[a] | nbrs[b]) for (a, b), c in scores.items()}
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:int(top)]
        out = [(I.nodes[a], I.nodes[b], round(s, 4)) for (a, b), s in best]
        if show:
            for a, b, s in out:
                session.say((a, ">14"), " - ", (b, "<14"), f" {s}")
        if add and out:
            gr = g()
            f = gr.addEdgeField("predicted", "VARCHAR", None)
            made = []
            for a, b, _s in out:
                e = gr.addEdge(a, b, False)
                f.set(e, m)
                made.append(e)
            session.say("added ", (f"{len(made)} predicted edges", made), f" (predicted = {m!r})")
        return out

    # ---- patterns, cuts, flows -------------------------------------------------
    def pattern_graph(pattern):
        ig = module()
        if hasattr(pattern, "nodes") and hasattr(pattern, "is_directed"):       # networkx
            keys = list(pattern.nodes)
            idx = {k: i for i, k in enumerate(keys)}
            return ig.Graph(n=len(keys), edges=[(idx[a], idx[b]) for a, b in pattern.edges()],
                            directed=pattern.is_directed())
        pairs = list(pattern)
        if not pairs or not all(isinstance(p, (tuple, list)) and len(p) == 2 for p in pairs):
            raise GuessError('findPattern needs a pattern: a list of pairs like [("a","b"), ("b","c")] '
                             "or a networkx graph such as nx.cycle_graph(4)")
        keys = []
        for a, b in pairs:
            for k in (a, b):
                if k not in keys:
                    keys.append(k)
        idx = {k: i for i, k in enumerate(keys)}
        return ig.Graph(n=len(keys), edges=[(idx[a], idx[b]) for a, b in pairs])

    @cmd
    def findPattern(pattern, induced=False, limit=100):
        """findPattern(pattern) finds every place where a small pattern occurs in
        the graph (subgraph isomorphism, LAD algorithm). The pattern is a list of
        pairs, e.g. findPattern([("a","b"), ("b","c"), ("c","a")]) for
        triangles, or a networkx graph (nx.cycle_graph(4), nx.star_graph(3)).
        induced=True requires no extra edges among the matched nodes. Returns
        up to `limit` matches, each a set of nodes; the same nodes matched in
        another order count once."""
        need("findPattern")
        P = pattern_graph(pattern)
        I = IG(g(), directed=bool(P.is_directed()))
        if P.vcount() > I.G.vcount():
            return GSet(annotation="no matches")
        maps = I.G.get_subisomorphisms_lad(P, induced=bool(induced))
        seen, out = set(), []
        for mp in maps:
            key = frozenset(mp)
            if key in seen:
                continue
            seen.add(key)
            out.append(GSet(sorted((I.nodes[v] for v in mp), key=lambda n: n._id), f"match {len(out)}"))
            if len(out) >= int(limit):
                break
        session.say((f"{len(out)} match{'es' if len(out) != 1 else ''}", out),
                    " (limit reached)" if len(out) >= int(limit) else "")
        return GSet(out, f"{len(out)} matches")

    @cmd
    def minCut(a, b, capacity=None):
        """minCut(a, b) returns the fewest edges whose removal separates a from b
        (direction ignored); minCut(a, b, weight) the cut of least total
        weight. Prints the cut's size."""
        need("minCut")
        I = undirected()
        va, vb = I.vid(node(a)), I.vid(node(b))
        if va == vb:
            raise GuessError("minCut needs two different nodes")
        cap = None
        if capacity is not None:
            f = capacity if isinstance(capacity, Field) else g().edge_schema.get(str(capacity))
            if f is None or f.kind != EDGE:
                raise GuessError("capacity should be an edge field, e.g. minCut(a, b, weight)")
            cap = [sum(float(f.get(e) or 0) for e in es) for es in I.pairs]
        cut = I.G.mincut(source=va, target=vb, capacity=cap)
        edges = [e for k in cut.cut for e in I.pairs[k]]
        session.say(f"cut value {cut.value:g}: ", (f"{len(edges)} edges", edges))
        return GSet(sorted(edges, key=lambda e: e._id), f"cut between {I.nodes[va]._name} and {I.nodes[vb]._name}")

    @cmd
    def maxFlow(a, b, capacity="weight"):
        """maxFlow(a, b) computes the maximum flow from a to b with edge weights
        as capacities (capacity=None: 1 per edge), following edge direction when
        the graph has directed edges. Each edge's flow is stored in the edge
        field `flow`; returns the total."""
        need("maxFlow")
        I = IG(g(), directed=None)
        va, vb = I.vid(node(a)), I.vid(node(b))
        if capacity is None:
            cap = None
        else:
            f = capacity if isinstance(capacity, Field) else g().edge_schema.get(str(capacity))
            if f is None:
                raise GuessError(f"no edge field {capacity!r}")
            cap = [max(0.0, sum(float(f.get(e) or 0) for e in es)) for es in I.pairs]
        flow = I.G.maxflow(va, vb, capacity=cap)
        ff = g().addEdgeField("flow", DOUBLE, 0.0)
        for e in g()._edges_list():
            ff.set(e, 0.0)
        for es, x in zip(I.pairs, flow.flow):
            for e in es:
                ff.set(e, abs(float(x)) / len(es))
        print(f"maximum flow {flow.value:g}")
        return float(flow.value)

    @cmd
    def personalizedPagerank(seq, damping=0.85):
        """personalizedPagerank(seq) ranks every node by how easily a random walk
        restarting at the given nodes reaches it: relevance to a chosen set
        (e.g. personalizedPagerank(sel) or personalizedPagerank(v1)). Stored in
        the field `ppr`."""
        need("personalizedPagerank")
        I = IG(g(), directed=None)
        seeds = [I.vid(x) for x in elements_of(seq) if isinstance(x, Node)]
        if not seeds:
            raise GuessError("personalizedPagerank needs some nodes")
        vals = I.G.personalized_pagerank(damping=float(damping), reset_vertices=seeds,
                                         weights=I.positive_weights(), directed=I.directed)
        f = g().addNodeField("ppr", DOUBLE, 0.0)
        for n, v in zip(I.nodes, vals):
            f.set(n, float(v))
        return f

    @cmd
    def dominatorTree(root):
        """dominatorTree(root) follows directed edges from root and finds, for
        every node it reaches, its immediate dominator: the last node every path
        from root must pass through (who controls access to whom). Stored in
        `idom` (a node name); returns the nodes root reaches."""
        need("dominatorTree")
        I = IG(g(), directed=True)
        r = I.vid(node(root))
        dom = I.G.dominator(r, mode="out")
        f = g().addNodeField("idom", STRING, None)
        reached = []
        for v, d in enumerate(dom):
            n = I.nodes[v]
            if v == r:
                f.set(n, None)
            elif d is None or (isinstance(d, (int, float)) and d < 0) or (isinstance(d, float) and math.isnan(d)):
                f.set(n, None)
            else:
                f.set(n, I.nodes[int(d)]._name)
                reached.append(n)
        return GSet(sorted(reached, key=lambda n: n._id), f"reached from {I.nodes[r]._name}")

    @cmd
    def largestCliques():
        """largestCliques() returns the largest cliques (groups where everyone is
        linked to everyone), each a set of nodes. Exponential in the worst
        case, fast on sparse graphs."""
        need("largestCliques")
        I = undirected()
        cl = I.G.largest_cliques()
        out = [GSet(sorted((I.nodes[v] for v in c), key=lambda n: n._id), f"clique {i}") for i, c in enumerate(cl)]
        session.say((f"{len(out)} cliques", out), f" of size {len(cl[0]) if cl else 0}")
        return GSet(out, f"{len(out)} largest cliques")

    @cmd
    def maxMatching(field=None):
        """maxMatching() returns a largest set of edges with no node in two of
        them (pairs everyone it can); maxMatching(field) matches across the two
        values of a field in a two-mode network, using weights."""
        need("maxMatching")
        I = undirected()
        if field is None:
            # general graphs: networkx's blossom algorithm (O(n^3), fine to a few thousand nodes)
            from .algorithms import _nx
            nx = _nx()
            if len(I.nodes) > 5000:
                raise GuessError("maxMatching() on a general graph is slow beyond 5,000 nodes")
            H = nx.Graph(I.G.get_edgelist())
            out = []
            for v, w in nx.max_weight_matching(H, maxcardinality=True, weight=None):
                out.append(I.pairs[I.G.get_eid(v, w)][0])
            return GSet(sorted(out, key=lambda e: e._id), f"{len(out)} matched pairs")
        else:
            f = field_arg(field, "maxMatching")
            vals = [f.get(n) for n in I.nodes]
            kinds = sorted({v for v in vals if v is not None}, key=str)
            if len(kinds) != 2:
                raise GuessError(f"{f.name} should have exactly two values")
            m = I.G.maximum_bipartite_matching([v == kinds[1] for v in vals], weights=I.G.es["weight"])
        out = []
        for v, w in enumerate(m.matching):
            if w is not None and w > v:
                k = I.G.get_eid(v, w)
                out.append(I.pairs[k][0])
        return GSet(sorted(out, key=lambda e: e._id), f"{len(out)} matched pairs")

    # ---- graph surgery (no igraph needed) -----------------------------------------
    @cmd
    def simplify(combine="sum", loops=True):
        """simplify() merges parallel edges between the same two nodes (and the
        same direction) into one, whose weight combines theirs: combine="sum"
        (default), "max", "min", "mean" or "first"; loops=True also removes
        self-loops. One undo step."""
        how = {"sum": sum, "max": max, "min": min, "mean": lambda xs: sum(xs) / len(xs),
               "first": lambda xs: xs[0]}.get(str(combine).lower())
        if how is None:
            raise GuessError('combine should be "sum", "max", "min", "mean" or "first"')
        gr = g()
        groups = {}
        loops_out = []
        for e in gr._edges_list():
            if e._n1 is e._n2:
                if loops:
                    loops_out.append(e)
                continue
            key = (e._n1._id, e._n2._id, True) if e._directed else (min(e._n1._id, e._n2._id), max(e._n1._id, e._n2._id), False)
            groups.setdefault(key, []).append(e)
        removed = list(loops_out)
        for es in groups.values():
            if len(es) > 1:
                es[0].weight = how([_weight(e) for e in es])
                removed += es[1:]
        if removed:
            gr.remove(removed)
        print(f"removed {len(removed)} edges ({len(loops_out)} self-loops)")

    @cmd
    def rewire(times=None, name=None, seed=0, keep=None):
        """rewire() makes a randomised copy of the graph in a new tab keeping
        every node's degree (repeated swaps of edge ends, 10 x edges by
        default): the null model for "is this structure more than chance?".
        Compare e.g. transitivity() or modularity here and there. Edge weights
        travel with the swapped ends. keep=field only swaps ends that share
        that field's value, so the edges between each pair of values stay
        the same in number: rewire(keep=kind) keeps a two-mode network
        two-mode (plants still only link to pollinators)."""
        gr = g()
        keep_name = None if keep is None else (keep.name if hasattr(keep, "name") else str(keep))
        if keep_name is not None and keep_name not in gr.node_schema:
            raise GuessError(f"keep= needs a node field (no node field {keep_name!r})")
        session.ns["subgraph"](list(gr._nodes_list()), name or "rewired")
        gr = g()
        keep_f = None if keep_name is None else gr.node_schema[keep_name]
        rnd = random.Random(seed)
        edges = [e for e in gr._edges_list() if e._n1 is not e._n2]
        if len(edges) < 2:
            return
        present = {frozenset((e._n1._id, e._n2._id)) for e in edges}
        where = {e._id: i for i, e in enumerate(edges)}
        n_swaps = int(times) if times is not None else 10 * len(edges)
        done = 0
        for _ in range(n_swaps * 3):
            if done >= n_swaps:
                break
            e1, e2 = rnd.sample(edges, 2)
            a, b, c, d = e1._n1, e1._n2, e2._n1, e2._n2
            if rnd.random() < 0.5:
                c, d = d, c
            if len({a._id, b._id, c._id, d._id}) < 4:
                continue
            if keep_f is not None and keep_f.get(b) != keep_f.get(d):
                continue       # the two ends swapped must be of the same kind
            k1, k2 = frozenset((a._id, d._id)), frozenset((c._id, b._id))
            if k1 in present or k2 in present:
                continue
            w1, w2 = _weight(e1), _weight(e2)
            gr.remove([e1, e2])
            present -= {frozenset((a._id, b._id)), frozenset((c._id, d._id))}
            n1 = gr.addEdge(a, d, e1._directed)
            n2 = gr.addEdge(c, b, e2._directed)
            n1.weight, n2.weight = w1, w2
            present |= {k1, k2}
            i1, i2 = where.pop(e1._id), where.pop(e2._id)
            edges[i1], edges[i2] = n1, n2
            where[n1._id], where[n2._id] = i1, i2
            done += 1
        session.scene()
        print(f"{done} swaps; degrees unchanged")

