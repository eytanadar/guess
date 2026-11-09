"""Structure: weak points, backbones, directed hierarchies, mixing, and how
two partitions agree.

    bridges(); cutNodes()                    edges / nodes whose removal disconnects the graph
    spanningTree(maximum=False)              the backbone (minimum or maximum spanning forest)
    ancestors(n); descendants(n)             upstream / downstream along directed edges
    transitiveReduction(); feedbackEdges()   implied edges of a DAG; edges that make cycles
    assortativity(dept); mixingMatrix(dept)  do similar nodes link?
    triadCensus(); reciprocity(); transitivity()
    compareClusters(modularity_class, dept)  how well two partitions agree (NMI, ARI, ...)

Node fields computed on first use: constraint and effsize (Burt's structural
holes: low constraint = a broker), generation (step in a directed hierarchy).
"""
import math
from collections import Counter, defaultdict

import numpy as np

from .algorithms import _nx
from .model import BOOL, INT, NODE, Field, GSet, GuessError, Node


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
    def ancestors(n):
        """ancestors(n): every node with a directed path to n (upstream: what n
        depends on or cites, transitively). Undirected edges count both ways."""
        nx = _nx()
        n = node(n)
        return GSet(sorted(nx.ancestors(_directed(g()), n), key=lambda m: m._id), f"ancestors of {n._name}")

    @cmd
    def descendants(n):
        """descendants(n): every node reachable from n along directed edges
        (downstream: what depends on n, or what n leads to)."""
        nx = _nx()
        n = node(n)
        return GSet(sorted(nx.descendants(_directed(g()), n), key=lambda m: m._id), f"descendants of {n._name}")

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
    def compareClusters(field1, field2, method="nmi"):
        """compareClusters(modularity_class, dept) says how well two partitions of
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

