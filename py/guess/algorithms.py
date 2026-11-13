"""Graph algorithms backed by networkx (available in Pyodide via loadPackage)."""
import random

from .model import INT, GSet, GuessError


def _nx():
    try:
        import networkx
    except ImportError:  # pragma: no cover - depends on environment
        raise GuessError("networkx is not available") from None
    return networkx


def to_networkx(graph, directed=None):
    nx = _nx()
    edges = graph._edges_list()
    if directed is None:
        directed = any(e._directed for e in edges)
    G = nx.DiGraph() if directed else nx.Graph()
    for n in graph._nodes_list():
        G.add_node(n)
    for e in edges:
        w = e._vals.get("weight", 1.0)
        G.add_edge(e._n1, e._n2, weight=w, edge=e)
        if directed and not e._directed:
            G.add_edge(e._n2, e._n1, weight=w, edge=e)
    return G


def _edge_values(graph, G, values):
    out = {}
    for (a, b), v in values.items():
        e = G.edges[a, b]["edge"]
        out[e] = max(v, out.get(e, 0.0))
    return out


def _betweenness_nodes(graph):
    from . import igr
    if igr.module():
        return igr.betweenness_nodes(graph)
    nx = _nx()
    return nx.betweenness_centrality(to_networkx(graph), normalized=False)


def _betweenness_edges(graph):
    from . import igr
    if igr.module():
        return igr.betweenness_edges(graph)
    nx = _nx()
    G = to_networkx(graph)
    return _edge_values(graph, G, nx.edge_betweenness_centrality(G, normalized=False))


def install(session):
    g = session.graph   # computed fields (betweenness, pagerank, ...) live in analysis.py

    def edgeBetweennessClusters(count):
        """Split the graph into `count` communities with Girvan-Newman."""
        nx = _nx()
        G = to_networkx(g, directed=False)
        comps = None
        for level in nx.community.girvan_newman(G):
            comps = level
            if len(level) >= count:
                break
        comps = comps or [set(G.nodes)]
        return GSet((GSet(sorted(c, key=lambda n: n._id), f"cluster {i}") for i, c in enumerate(comps)),
                    f"{len(comps)} edge betweenness clusters")

    def weakComponentClusters():
        """Connected components (ignoring edge direction)."""
        nx = _nx()
        comps = nx.connected_components(to_networkx(g, directed=False))
        return GSet((GSet(sorted(c, key=lambda n: n._id), f"component {i}")
                     for i, c in enumerate(sorted(comps, key=len, reverse=True))),
                    "weak components")

    def biComponentClusters():
        """Biconnected components (ignoring edge direction)."""
        nx = _nx()
        comps = nx.biconnected_components(to_networkx(g, directed=False))
        return GSet((GSet(sorted(c, key=lambda n: n._id), f"bicomponent {i}")
                     for i, c in enumerate(sorted(comps, key=len, reverse=True))),
                    "bicomponents")

    session.register_command("biComponentClusters", biComponentClusters)

    # ---- generators (replace the current graph; nodes are named nd0, nd1, ...) ----
    def make_from(G, label):
        directed = G.is_directed()
        g.clear()
        add_born(G)
        index = {}
        for i, v in enumerate(G.nodes):
            n = g.addNode(f"nd{i}")
            n.label = f"nd{i}"
            if "born" in G.nodes[v]:
                n.born = G.nodes[v]["born"]
            pos = G.nodes[v].get("pos")
            if pos is not None:
                n.x, n.y = 50 + 900 * pos[0], 50 + 900 * pos[1]
            else:
                n.x, n.y = random.random() * 500, random.random() * 500
            index[v] = n
        for a, b in G.edges():
            e = g.addEdge(index[a], index[b], directed)
            if "born" in G.edges[a, b]:
                e.born = G.edges[a, b]["born"]
        session.scene()
        print(f"generated {label}: {len(g._nodes)} nodes, {len(g._edges)} edges")

    def add_born(G):
        """Growth models record when each node (and edge) arrived: a `born` field, for revealUpTo."""
        if any("born" in d for _v, d in G.nodes(data=True)):
            g.addNodeField("born", INT, 0)
            g.addEdgeField("born", INT, 0)

    def gen(name, doc, build):
        def fn(*args):
            nx = _nx()
            G = build(nx, *args)
            make_from(G, name)
        fn.__name__ = name
        fn.__doc__ = doc
        session.register_command(name, fn)

    gen("makeSimpleRandom", "makeSimpleRandom(nodes, edges): uniform random undirected graph.",
        lambda nx, n, m: nx.gnm_random_graph(int(n), int(m)))
    gen("makeSimpleDirectedRandom", "makeSimpleDirectedRandom(nodes, edges): uniform random directed graph.",
        lambda nx, n, m: nx.gnm_random_graph(int(n), int(m), directed=True))
    gen("makeErdosRenyiRandom", "makeErdosRenyiRandom(nodes, p): each edge present with probability p.",
        lambda nx, n, p: nx.gnp_random_graph(int(n), float(p)))
    gen("makeBarabasiAlbertRandom",
        "makeBarabasiAlbertRandom(vert, edges, evolve): preferential attachment; starts from "
        "`vert` nodes and adds `evolve` nodes with `edges` edges each. The field `born` records the "
        "step each node and edge arrived (0 for the seeds), so revealUpTo(step) can replay the growth.",
        lambda nx, v, m, ev: _barabasi(nx, int(v), int(m), int(ev)))
    gen("makeKleinbergRandom",
        "makeKleinbergRandom(size, clust): Kleinberg small world on a size x size torus with "
        "one long-range edge per node, distance exponent clust.",
        lambda nx, n, r: _kleinberg(nx, int(n), float(r)))
    gen("makeLattice1DRandom", "makeLattice1DRandom(nodes, toroidal): a path (or ring if toroidal).",
        lambda nx, n, tor: _with_ring_pos(nx.cycle_graph(int(n)) if tor else nx.path_graph(int(n))))
    gen("makeLattice2DRandom", "makeLattice2DRandom(size, toroidal): a size x size grid (torus if toroidal).",
        lambda nx, n, tor: _grid(nx, int(n), bool(tor)))
    gen("makeEppsteinRandom",
        "makeEppsteinRandom(nodes, edges, r): power-law graph by r rounds of degree-biased "
        "rewiring of a uniform random graph (Eppstein & Wang).",
        lambda nx, n, m, r: _eppstein(nx, int(n), int(m), int(r)))

    session.register_command("edgeBetweennessClusters", edgeBetweennessClusters)
    session.register_command("weakComponentClusters", weakComponentClusters)


def _barabasi(nx, v, m, evolve):
    """Preferential attachment: each new node links to m existing nodes chosen
    with probability proportional to (degree + 1), so isolated seeds can be hit.
    `pool` holds every node once plus once per incident edge end (linear time)."""
    G = nx.empty_graph(max(v, 1))
    nx.set_node_attributes(G, 0, "born")        # the seed nodes arrive at step 0
    pool = list(G.nodes)
    for step in range(1, evolve + 1):
        new = G.number_of_nodes()
        k = min(m, new)
        chosen = set()
        while len(chosen) < k:
            chosen.add(random.choice(pool))
        G.add_node(new, born=step)
        pool.append(new)
        for t in chosen:
            G.add_edge(new, t, born=step)
            pool += [new, t]
    return G


def _kleinberg(nx, size, r):
    G = nx.navigable_small_world_graph(size, p=1, q=1, r=r, dim=2)
    H = nx.Graph()
    for (i, j) in G.nodes:
        H.add_node((i, j), pos=(i / max(size - 1, 1), j / max(size - 1, 1)))
    for a, b in G.edges:
        if a != b:
            H.add_edge(a, b)
    return H


def _grid(nx, size, tor):
    G = nx.grid_2d_graph(size, size, periodic=tor)
    for (i, j) in G.nodes:
        G.nodes[(i, j)]["pos"] = (i / max(size - 1, 1), j / max(size - 1, 1))
    return G


def _with_ring_pos(G):
    import math
    k = G.number_of_nodes()
    for i, v in enumerate(G.nodes):
        a = 2 * math.pi * i / max(k, 1)
        G.nodes[v]["pos"] = (0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a))
    return G


def _eppstein(nx, n, m, r):
    G = nx.gnm_random_graph(n, m)
    nodes = list(G.nodes)
    for _ in range(r):
        edges = list(G.edges)
        if not edges:
            break
        a, b = random.choice(edges)
        # pick an endpoint pair biased toward high degree
        x = random.choice(nodes)
        degs = [G.degree(v) + 1 for v in nodes]
        y = random.choices(nodes, weights=degs)[0]
        if x != y and not G.has_edge(x, y):
            G.remove_edge(a, b)
            G.add_edge(x, y)
    return G
