"""Structure: weak points, backbones, directed hierarchies, mixing, and how
two partitions agree.

    bridges(); cutNodes()                    edges / nodes whose removal disconnects the graph
    spanningTree(maximum=False)              the backbone (minimum or maximum spanning forest)
    ancestors(node); descendants(node)       upstream / downstream along directed edges
    transitiveReduction(); feedbackEdges()   implied edges of a DAG; edges that make cycles
    assortativity(dept); mixingMatrix(dept)  do similar nodes link?
    triadCensus(); reciprocity(); transitivity()
    compareClusters(louvain_class, dept)  how well two partitions agree (NMI, ARI, ...)

Node fields computed on first use: constraint and effsize (Burt's structural
holes: low constraint = a broker), generation (step in a directed hierarchy).
"""
import math
from collections import Counter, defaultdict

import numpy as np

from .algorithms import _nx
from .model import BOOL, DOUBLE, INT, NODE, Field, GSet, GuessError, Node


# ---- graphs for the algorithms (node keys are GUESS nodes) -----------------

def _undirected(graph, prefer=None):
    """A simple undirected networkx graph; parallel edges merge, keeping (as
    `edge`) the lightest (prefer="min") or heaviest ("max") or last one, and
    `count` records how many GUESS edges join the pair. Self-loops are dropped."""
    nx = _nx()
    G = nx.Graph()
    G.add_nodes_from(graph._nodes_list())
    for e in graph._edges_list():
        a, b = e._n1, e._n2
        if a is b:
            continue
        w = e._vals.get("weight", 1.0)
        w = 1.0 if w is None else float(w)
        if G.has_edge(a, b):
            d = G.edges[a, b]
            d["count"] += 1
            if (prefer == "min" and w < d["weight"]) or (prefer == "max" and w > d["weight"]):
                d["weight"], d["edge"] = w, e
        else:
            G.add_edge(a, b, weight=w, edge=e, count=1)
    return G


def _directed(graph, only_directed=False):
    """A simple DiGraph: directed edges one way, undirected edges both ways
    (unless only_directed). `edges` on each arc lists the GUESS edges."""
    nx = _nx()
    G = nx.DiGraph()
    G.add_nodes_from(graph._nodes_list())
    for e in graph._edges_list():
        if only_directed and not e._directed:
            continue
        arcs = [(e._n1, e._n2)] if e._directed else [(e._n1, e._n2), (e._n2, e._n1)]
        for a, b in arcs:
            if G.has_edge(a, b):
                G.edges[a, b]["edges"].append(e)
            else:
                G.add_edge(a, b, edges=[e])
    return G


# ---- computed node fields ----------------------------------------------------

def _clean(values):
    return {k: (None if isinstance(v, float) and math.isnan(v) else float(v)) for k, v in values.items()}


def _constraint(graph):
    nx = _nx()
    G = _undirected(graph)
    G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
    vals = _clean(nx.constraint(G, weight="weight")) if len(G) else {}
    return {n: vals.get(n) for n in graph._nodes_list()}


def _effsize(graph):
    nx = _nx()
    G = _undirected(graph)
    vals = _clean(nx.effective_size(G, weight="weight")) if len(G) else {}
    return {n: (vals.get(n) if vals.get(n) is not None else 0.0) for n in graph._nodes_list()}


def _generation(graph):
    """0 for nodes nothing points to, then 1, 2, ... along directed edges; a
    strongly connected group (a cycle) shares one generation."""
    nx = _nx()
    G = _directed(graph, only_directed=True)
    C = nx.condensation(G)
    gen = {}
    for i, layer in enumerate(nx.topological_generations(C)):
        for c in layer:
            for n in C.nodes[c]["members"]:
                gen[n] = i
    return gen, INT


LAZY = {"constraint": _constraint, "effsize": _effsize, "generation": _generation}


# ---- partition comparison ----------------------------------------------------

def _contingency(a, b):
    la, ia = np.unique(np.asarray(a, dtype=object).astype(str), return_inverse=True)
    lb, ib = np.unique(np.asarray(b, dtype=object).astype(str), return_inverse=True)
    m = np.zeros((len(la), len(lb)))
    np.add.at(m, (ia, ib), 1)
    return m


def _entropy(p):
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def compare_partitions(a, b, method="nmi"):
    m = _contingency(a, b)
    n = m.sum()
    if n == 0:
        raise GuessError("no elements have both values")
    pa, pb, pab = m.sum(1) / n, m.sum(0) / n, m / n
    ha, hb = _entropy(pa), _entropy(pb)
    nz = pab > 0
    mi = float((pab[nz] * np.log(pab[nz] / np.outer(pa, pb)[nz])).sum())
    method = str(method).lower()
    if method == "nmi":
        return 1.0 if ha + hb == 0 else 2 * mi / (ha + hb)
    if method == "vi":
        return ha + hb - 2 * mi
    comb = lambda x: x * (x - 1) / 2  # noqa: E731
    sum_ij = comb(m).sum()
    sum_a, sum_b = comb(m.sum(1)).sum(), comb(m.sum(0)).sum()
    total = comb(n)
    if method == "rand":
        return 1.0 if total == 0 else float((total + 2 * sum_ij - sum_a - sum_b) / total)
    if method in ("ari", "adjusted_rand"):
        expected = sum_a * sum_b / total if total else 0
        top = (sum_a + sum_b) / 2 - expected
        return 1.0 if top == 0 else float((sum_ij - expected) / top)
    raise GuessError("method should be 'nmi', 'ari', 'rand' or 'vi'")


# ---- commands ----------------------------------------------------------------

def install(session):
    for name, fn in LAZY.items():
        session.graph.lazy_fields[(NODE, name)] = fn

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

    def field(f, what):
        if isinstance(f, Field):
            return f
        if isinstance(f, str):
            for schema in (g().node_schema, g().edge_schema):
                if f in schema:
                    return schema[f]
        raise GuessError(f"{what} needs a field, e.g. {what}(dept)")

    # ---- weak points and backbones -------------------------------------------
    @cmd
    def bridges():
        """bridges(): the edges whose removal would split a connected part of the
        graph in two (direction ignored; a pair joined by parallel edges is never
        a bridge). bridges().color = red shows the weak ties."""
        nx = _nx()
        G = _undirected(g())
        out = [G.edges[a, b]["edge"] for a, b in nx.bridges(G) if G.edges[a, b]["count"] == 1]
        return GSet(sorted(out, key=lambda e: e._id), "bridges")

    @cmd
    def cutNodes():
        """cutNodes(): the nodes whose removal would split a connected part of the
        graph (articulation points; direction ignored)."""
        nx = _nx()
        G = _undirected(g())
        return GSet(sorted(nx.articulation_points(G), key=lambda n: n._id), "cut nodes")

    @cmd
    def spanningTree(maximum=False, weighted=True):
        """spanningTree() returns the edges of a minimum spanning tree (a forest if
        the graph is in pieces) by edge weight: the cheapest backbone that keeps
        everything connected. spanningTree(maximum=True) keeps the strongest ties
        instead, a good backbone when weight means strength:
        showOnly(spanningTree(maximum=True)). weighted=False ignores weights."""
        nx = _nx()
        G = _undirected(g(), prefer="max" if maximum else "min")
        if not weighted:
            for _a, _b, d in G.edges(data=True):
                d["weight"] = 1.0
        fn = nx.maximum_spanning_edges if maximum else nx.minimum_spanning_edges
        out = [d["edge"] for _a, _b, d in fn(G, weight="weight", data=True)]
        return GSet(sorted(out, key=lambda e: e._id), "maximum spanning tree" if maximum else "spanning tree")

    # ---- directed structure --------------------------------------------------
    @cmd
    def ancestors(node):
        """ancestors(node): every node with a directed path to node (upstream: what it
        depends on or cites, transitively). Undirected edges count both ways."""
        nx = _nx()
        node = _node_of(node)
        return GSet(sorted(nx.ancestors(_directed(g()), node), key=lambda m: m._id), f"ancestors of {node._name}")

    @cmd
    def descendants(node):
        """descendants(node): every node reachable from node along directed edges
        (downstream: what depends on it, or what it leads to)."""
        nx = _nx()
        node = _node_of(node)
        return GSet(sorted(nx.descendants(_directed(g()), node), key=lambda m: m._id), f"descendants of {node._name}")

    @cmd
    def feedbackEdges():
        """feedbackEdges(): directed edges that close cycles (back edges of a
        depth-first search, plus self-loops); removing or reversing them leaves
        the directed part acyclic. A small set, not necessarily the smallest."""
        G = _directed(g(), only_directed=True)
        state, back = {}, []
        for root in sorted(G, key=lambda n: n._id):
            if root in state:
                continue
            stack = [(root, iter(sorted(G.successors(root), key=lambda n: n._id)))]
            state[root] = 1
            while stack:
                v, it = stack[-1]
                for w in it:
                    if state.get(w) == 1:
                        back += G.edges[v, w]["edges"]
                    elif w not in state:
                        state[w] = 1
                        stack.append((w, iter(sorted(G.successors(w), key=lambda n: n._id))))
                        break
                else:
                    state[v] = 2
                    stack.pop()
        uniq = {e._id: e for e in back}
        return GSet(sorted(uniq.values(), key=lambda e: e._id), "feedback edges")

    @cmd
    def mainPath():
        """mainPath() finds the main path of a citation (or other flow)
        network: the chain of directed edges that the most source-to-sink
        paths run through (Hummon and Doreian's main path analysis, key-route
        variant). Each directed edge gets `spc`, its search path count as a
        share of all source-to-sink paths (0..1). The path starts at the edge
        with the highest spc and extends both ways, always along the
        highest-spc edge, to a source and a sink. Edges closing cycles
        (feedbackEdges()) are ignored. Returns the path's nodes and edges.
        In a citation network with edges citing -> cited, it runs from recent
        work back to the field's foundations."""
        gr = g()
        back = {e._id for e in feedbackEdges()}
        edges = [e for e in gr._edges_list() if e._directed and e._id not in back and e._n1 is not e._n2]
        if not edges:
            raise GuessError("mainPath needs directed edges (e.g. citing -> cited)")
        out, inc = defaultdict(list), defaultdict(list)
        nodes = set()
        for e in edges:
            out[e._n1].append(e)
            inc[e._n2].append(e)
            nodes.update((e._n1, e._n2))
        # topological order (Kahn) of the acyclic part
        indeg = {n: len(inc[n]) for n in nodes}
        order = []
        ready = sorted((n for n in nodes if indeg[n] == 0), key=lambda n: n._id)
        while ready:
            n = ready.pop()
            order.append(n)
            for e in out[n]:
                indeg[e._n2] -= 1
                if indeg[e._n2] == 0:
                    ready.append(e._n2)
        before = {}          # paths from any source to n
        for n in order:
            before[n] = 1 if not inc[n] else sum(before[e._n1] for e in inc[n])
        after = {}           # paths from n to any sink
        for n in reversed(order):
            after[n] = 1 if not out[n] else sum(after[e._n2] for e in out[n])
        total = sum(before[n] for n in nodes if not out[n]) or 1
        f = gr.addEdgeField("spc", DOUBLE, 0.0)
        spc = {}
        for e in edges:
            s = before[e._n1] * after[e._n2]
            spc[e._id] = s
            f.set(e, s / total)
        best = max(edges, key=lambda e: (spc[e._id], -e._id))
        path = [best]
        n = best._n2
        while out[n]:
            e = max(out[n], key=lambda x: (spc[x._id], -x._id))
            path.append(e)
            n = e._n2
        n = best._n1
        while inc[n]:
            e = max(inc[n], key=lambda x: (spc[x._id], -x._id))
            path.insert(0, e)
            n = e._n1
        members = [path[0]._n1] + [e._n2 for e in path]
        print(f"main path: {len(members)} nodes; its strongest link carries "
              f"{spc[best._id] / total:.0%} of all source-to-sink paths")
        return GSet(members + path, "main path")

    @cmd
    def transitiveReduction():
        """transitiveReduction(): in a directed acyclic graph, the edges implied
        by longer paths (a -> c when a -> b -> c exists, and repeated edges). They
        are marked in the edge field `redundant` and returned, so
        transitiveReduction().visible = false shows the backbone of a citation or
        dependency graph. Only directed edges count; cycles are an error (see
        feedbackEdges)."""
        nx = _nx()
        G = _directed(g(), only_directed=True)
        if not nx.is_directed_acyclic_graph(G):
            raise GuessError("the directed edges form cycles: feedbackEdges() lists edges to break them")
        keep = set(nx.transitive_reduction(G).edges())
        redundant = []
        for a, b, d in G.edges(data=True):
            es = sorted(d["edges"], key=lambda e: e._id)
            redundant += es if (a, b) not in keep else es[1:]
        gr = g()
        f = gr.edge_schema.get("redundant") or gr.addEdgeField("redundant", BOOL, False)
        ids = {e._id for e in redundant}
        for e in gr._edges_list():
            f.set(e, e._id in ids if e._directed else False)
        return GSet(sorted(redundant, key=lambda e: e._id), "redundant edges")

    # ---- mixing --------------------------------------------------------------
    @cmd
    def assortativity(field=None):
        """assortativity() is the degree assortativity of the graph: positive when
        hubs link to hubs, negative when hubs link to small nodes.
        assortativity(dept) measures homophily by a field: near 1 = ties stay
        within the same value, 0 = random mixing, negative = ties cross values.
        Numeric fields use the correlation of values across edges."""
        nx = _nx()
        G = _undirected(g())
        if field is None:
            if G.number_of_edges() == 0:
                raise GuessError("no edges")
            return float(nx.degree_assortativity_coefficient(G))
        f = _node_field(field)
        vals = {n: f.get(n) for n in G}
        G.remove_nodes_from([n for n, v in vals.items() if v is None])
        if G.number_of_edges() == 0:
            raise GuessError(f"no edges between nodes with a value of {f.name}")
        nx.set_node_attributes(G, {n: vals[n] for n in G}, "v")
        if f.type in ("INTEGER", "DOUBLE"):
            return float(nx.numeric_assortativity_coefficient(G, "v"))
        return float(nx.attribute_assortativity_coefficient(G, "v"))

    def _node_field(f):
        f = field(f, "assortativity")
        if f.kind != NODE:
            raise GuessError("needs a node field")
        return f

    @cmd
    def mixingMatrix(field, show=True):
        """mixingMatrix(dept) counts the edges between each pair of values of a
        node field (dept1-dept1, dept1-dept2, ...), printed as a table and
        returned as {value: {value: count}}. Direction is ignored. With many
        values only the 20 most common are printed."""
        f = _node_field(field)
        counts = defaultdict(Counter)
        for e in g()._edges_list():
            a, b = f.get(e._n1), f.get(e._n2)
            if a is None or b is None:
                continue
            counts[a][b] += 1
            if a != b:
                counts[b][a] += 1
        out = {a: dict(row) for a, row in counts.items()}
        if show and out:
            size = Counter({a: sum(row.values()) for a, row in out.items()})
            keys = [k for k, _c in size.most_common(20)]
            keys.sort(key=lambda k: (str(type(k)), k))
            w = max(6, *(len(str(k)) for k in keys))
            print(" " * w + " " + " ".join(f"{str(k)[:w]:>{w}}" for k in keys))
            for a in keys:
                print(f"{str(a)[:w]:>{w}} " + " ".join(f"{out.get(a, {}).get(b, 0):>{w}}" for b in keys))
            if len(size) > len(keys):
                print(f"({len(size) - len(keys)} more values not shown)")
        return out

    # ---- directed / social summaries ---------------------------------------
    TRIADS = {
        "003": "empty", "012": "one edge", "102": "one mutual pair", "021D": "out-star",
        "021U": "in-star", "021C": "path", "111D": "mutual + in", "111U": "mutual + out",
        "030T": "transitive", "030C": "cycle", "201": "two mutual pairs", "120D": "mutual + out-star",
        "120U": "mutual + in-star", "120C": "mutual + path", "210": "almost complete", "300": "complete",
    }

    @cmd
    def triadCensus(show=True):
        """triadCensus() counts the 16 kinds of directed triads (Holland and
        Leinhardt): how often three nodes form a cycle, a transitive triple, a
        star and so on. Undirected edges count as mutual. Prints the types that
        occur and returns {type: count}."""
        nx = _nx()
        G = _directed(g())
        census = nx.triadic_census(G)
        if show:
            for k, v in census.items():
                if v and k != "003":
                    print(f"{k:5} {v:>9}  {TRIADS[k]}")
            print(f"003   {census['003']:>9}  {TRIADS['003']}")
        return dict(census)

    @cmd
    def robustness(orders=("random", "degree"), trials=5, seed=0, show=True):
        """robustness() asks how the network falls apart as nodes fail: for
        each way of removing nodes it gives the share of nodes still in the
        largest connected piece after removing each share of them, and plots
        the curves. orders: "random" (failures; averaged over `trials`
        random orders), "degree" or "betweenness" (attacks on the biggest
        hubs or bridges first, ranked once at the start), "adaptive" (the
        current highest-degree node each time), or a node field (highest
        first). The graph isn't changed. Returns {order: [(removed share,
        largest-piece share), ...]} and prints the share removed at which the
        largest piece drops below half. Many real networks shrug off random
        failures but break quickly under attack."""
        import random as _random
        gr = g()
        nodes = gr._nodes_list()
        n = len(nodes)
        if n < 2:
            raise GuessError("robustness needs at least two nodes")
        idx = {x._id: i for i, x in enumerate(nodes)}
        adj = [[] for _ in range(n)]
        for e in gr._edges_list():
            a, b = idx[e._n1._id], idx[e._n2._id]
            if a != b:
                adj[a].append(b)
                adj[b].append(a)

        def curve(order):
            # add nodes back in reverse removal order, tracking the largest piece
            parent, size = list(range(n)), [1] * n
            alive = [False] * n

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            largest, sizes = 0, [0] * (n + 1)      # sizes[k]: largest piece with k nodes present
            for k, v in enumerate(reversed(order), start=1):
                alive[v] = True
                for w in adj[v]:
                    if alive[w]:
                        a, b = find(v), find(w)
                        if a != b:
                            if size[a] < size[b]:
                                a, b = b, a
                            parent[b] = a
                            size[a] += size[b]
                largest = max(largest, size[find(v)])
                sizes[k] = largest
            return [(i / n, sizes[n - i] / n) for i in range(n + 1)]

        def adaptive_order():
            deg = [len(a) for a in adj]
            gone = [False] * n
            out = []
            for _ in range(n):
                v = max((i for i in range(n) if not gone[i]), key=lambda i: (deg[i], -i))
                gone[v] = True
                out.append(v)
                for w in adj[v]:
                    if not gone[w]:
                        deg[w] -= 1
            return out

        if isinstance(orders, (str, Field)):
            orders = [orders]
        results = {}
        for o in orders:
            name = o.name if isinstance(o, Field) else str(o)
            if name == "random":
                rng = _random.Random(seed)
                runs = []
                for _ in range(max(1, int(trials))):
                    order = list(range(n))
                    rng.shuffle(order)
                    runs.append(curve(order))
                pts = [(runs[0][i][0], sum(r[i][1] for r in runs) / len(runs)) for i in range(n + 1)]
            elif name == "adaptive":
                pts = curve(adaptive_order())
            else:
                f = o if isinstance(o, Field) else gr.node_schema.get(name)
                if f is None and (NODE, name) in gr.lazy_fields:
                    f = gr._lazy_field(NODE, name)       # betweenness etc.: computed on first use
                if f is None:
                    raise GuessError(f"unknown order {name!r}: use random, degree, betweenness, adaptive or a node field")
                vals = [f.get(x) for x in nodes]
                pts = curve(sorted(range(n), key=lambda i: (-(vals[i] if isinstance(vals[i], (int, float)) else 0), i)))
            results[name] = pts
        palette = [0x2c7bb6, 0xd7191c, 0x1a9641, 0x8e5fbf, 0xfdae61]
        step = max(1, n // 200)
        series = [{"name": k, "color": palette[i % len(palette)],
                   "points": [[round(x, 4), round(y, 4)] for x, y in v[::step] + [v[-1]]]}
                  for i, (k, v) in enumerate(results.items())]
        if show:
            for k, v in results.items():
                half = next((x for x, y in v if y < 0.5), 1.0)
                print(f"{k:>12}: largest piece below half after removing {half:.0%} of nodes")
            session.chart_out({"type": "chart", "id": "chart:line:robustness", "kind": "line",
                          "title": "Robustness", "xlabel": "share of nodes removed",
                          "ylabel": "share in the largest piece", "items": [], "series": series})
        return results

    @cmd
    def reciprocity():
        """reciprocity(): the share of directed edges whose reverse edge also
        exists (1 = every tie returned). Undirected edges are left out."""
        nx = _nx()
        G = _directed(g(), only_directed=True)
        if G.number_of_edges() == 0:
            raise GuessError("no directed edges")
        return float(nx.reciprocity(G))

    @cmd
    def transitivity():
        """transitivity(): the share of connected triples that close into
        triangles (global clustering coefficient; direction ignored)."""
        nx = _nx()
        return float(nx.transitivity(_undirected(g())))

    @cmd
    def blockmodel(count=4, show=True):
        """blockmodel(count) groups the nodes into count positions of structurally
        equivalent nodes: nodes tied to the same others (in the same
        directions), whether or not they're tied to each other, which is a
        role (teacher, broker, follower), not a community. Profiles are
        compared by correlation and merged by average-linkage clustering.
        Stores each node's position in `position` (0 = largest), prints the
        image matrix (the density of ties from each position to each other;
        a dense diagonal means cohesive positions, dense off-diagonals mean
        roles that serve each other) and returns the positions. Try
        colorize(position), then collapseBy(position) for the reduced graph.
        Fine up to a couple of thousand nodes."""
        gr = g()
        nodes = gr._nodes_list()
        n = len(nodes)
        count = int(count)
        if n < 2 or not 1 <= count <= n:
            raise GuessError(f"blockmodel needs 1 <= k <= the number of nodes ({n})")
        idx = {x._id: i for i, x in enumerate(nodes)}
        A = np.zeros((n, n))
        for e in gr._edges_list():
            a, b = idx[e._n1._id], idx[e._n2._id]
            if a == b:
                continue
            A[a, b] = 1
            if not e._directed:
                A[b, a] = 1
        # each node's profile: its row and its column (out- and in-ties). For
        # a pair i, j the entries about i and j themselves are left out (they
        # can't match: i isn't tied to itself); exact up to 400 nodes, then the
        # whole-profile correlation, which is close on larger graphs
        P = np.hstack([A, A.T])
        if n <= 400:
            C = np.empty((n, n))
            for i in range(n):
                for j in range(i, n):
                    m = np.ones(2 * n, bool)
                    m[[i, j, n + i, n + j]] = False
                    x, y = P[i, m], P[j, m]
                    sx, sy = x.std(), y.std()
                    if sx == 0 or sy == 0:
                        c = 1.0 if np.array_equal(x, y) else 0.0
                    else:
                        c = float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))
                    C[i, j] = C[j, i] = c
        else:
            with np.errstate(invalid="ignore", divide="ignore"):
                C = np.nan_to_num(np.corrcoef(P))
        # average-linkage agglomeration down to k clusters
        D = 1 - C
        np.fill_diagonal(D, np.inf)
        size = np.ones(n)
        members = {i: [i] for i in range(n)}
        for _ in range(n - count):
            a, b = np.unravel_index(np.argmin(D), D.shape)
            a, b = min(a, b), max(a, b)
            merged = (size[a] * D[a] + size[b] * D[b]) / (size[a] + size[b])
            D[a, :] = merged
            D[:, a] = merged
            D[a, a] = np.inf
            D[b, :] = np.inf
            D[:, b] = np.inf
            size[a] += size[b]
            members[a] += members.pop(b)
        clusters = members
        groups = sorted(clusters.values(), key=lambda c: (-len(c), min(c)))
        f = gr.addNodeField("position", INT, -1)
        pos = np.empty(n, int)
        for p, members in enumerate(groups):
            for i in members:
                f.set(nodes[i], p)
                pos[i] = p
        image = np.zeros((count, count))
        for p in range(count):
            for q in range(count):
                rows, cols = pos == p, pos == q
                block = A[np.ix_(rows, cols)]
                cells = rows.sum() * cols.sum() - (rows.sum() if p == q else 0)
                image[p, q] = block.sum() / cells if cells else 0.0
        if show:
            head = "position  size  " + "  ".join(f"{q:>5}" for q in range(count))
            print("tie density from each position (row) to each other (column)")
            print(head)
            for p in range(count):
                print(f"{p:>8}  {len(groups[p]):>4}  " + "  ".join(f"{image[p, q]:5.2f}" for q in range(count)))
        return GSet([GSet([nodes[i] for i in grp], annotation=f"position {p}")
                     for p, grp in enumerate(groups)], annotation=f"{count} positions")

    @cmd
    def compareClusters(field1, field2, method="nmi"):
        """compareClusters(louvain_class, dept) says how well two partitions of
        the nodes agree, over the nodes that have both values: method "nmi"
        (normalized mutual information, 0..1), "ari" (adjusted Rand: 0 = chance,
        1 = identical), "rand" or "vi" (variation of information: 0 = identical).
        Works for edge fields too."""
        f1, f2 = field(field1, "compareClusters"), field(field2, "compareClusters")
        if f1.kind != f2.kind:
            raise GuessError("both fields should be node fields (or both edge fields)")
        elems = g()._nodes_list() if f1.kind == NODE else g()._edges_list()
        pairs = [(f1.get(x), f2.get(x)) for x in elems]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if not pairs:
            raise GuessError("no element has both values")
        a, b = zip(*pairs)
        return float(compare_partitions(a, b, method))

