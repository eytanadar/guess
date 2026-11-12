"""Measures from Newman, Networks, ch. 7 that GUESS's other modules lack:
Katz centrality with a chosen alpha and beta, structural balance of signed
networks, k-components, and regular-equivalence similarity."""
from .model import INT as INTEGER, GSet, GuessError


def regular_similarity(graph, alpha=0.9):
    """sigma = sum_m (a A)^m = (I - a A)^-1 with a = alpha / lambda_1 (Leicht, Holme
    and Newman): two nodes are similar if their neighbours are similar, counting
    paths of every length. Scaled so each node is 1 with itself. Returns
    (nodes, matrix)."""
    import numpy as np
    nodes = graph._nodes_list()
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    A = np.zeros((n, n))
    for e in graph._edges_list():
        if e._n1 is not e._n2:
            A[idx[e._n1], idx[e._n2]] = A[idx[e._n2], idx[e._n1]] = 1.0
    if n == 0:
        return nodes, A
    lam = float(max(abs(np.linalg.eigvals(A)))) or 1.0
    S = np.linalg.inv(np.eye(n) - (float(alpha) / lam) * A)
    d = np.sqrt(np.clip(np.diag(S), 1e-12, None))
    return nodes, S / np.outer(d, d)


def install(session):
    reg = session.register_command

    def g():
        return session.graph

    def katzCentrality(alpha=None, beta=1.0, name="katz"):
        """katzCentrality(alpha, beta) gives each node x = alpha A x + beta: the
        importance its in-neighbours pass on (scaled by alpha) plus a free amount
        beta, so even nodes no one points to count. alpha must be below 1/kappa1
        (the largest eigenvalue of A; returned along with the field) for the
        sum to converge; small alpha ranks nodes almost by degree, alpha near
        1/kappa1 almost like eigenvector centrality. With alpha left out it is
        0.85/kappa1. Edges follow their direction (undirected ones both ways).
        Stores the values in the field `name` (default "katz") and returns
        (field, 1/kappa1)."""
        import numpy as np
        gr = g()
        nodes = gr._nodes_list()
        idx = {v: i for i, v in enumerate(nodes)}
        n = len(nodes)
        if n == 0:
            raise GuessError("the graph has no nodes")
        A = np.zeros((n, n))
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            A[idx[e._n2], idx[e._n1]] += 1.0            # A_ij = 1 for an edge from j to i
            if not e._directed:
                A[idx[e._n1], idx[e._n2]] += 1.0
        kappa = float(max(abs(np.linalg.eigvals(A))))
        limit = 1.0 / kappa if kappa > 1e-12 else float("inf")
        a = 0.85 * limit if alpha is None else float(alpha)
        if a < 0 or a >= limit:
            raise GuessError(f"alpha must be at least 0 and below 1/kappa1 = {limit:.4g}")
        x = np.linalg.solve(np.eye(n) - a * A, np.full(n, float(beta)))
        f = session.ns["setField"]({v: float(x[i]) for i, v in enumerate(nodes)}, str(name))
        return f, limit

    def _sign(e, field):
        v = getattr(e, field, None)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("+", "positive", "pos", "friend", "1", "+1"):
                return 1
            if s in ("-", "negative", "neg", "enemy", "-1", "−"):
                return -1
            raise GuessError(f"edge {e!r}: don't know the sign {v!r}")
        if v is None or v == 0:
            raise GuessError(f"edge {e!r} has no sign (field {field!r})")
        return 1 if v > 0 else -1

    def structuralBalance(sign="sign", name="camp"):
        """structuralBalance(sign) tests a signed network (an edge field of +1/-1,
        or "+"/"-") for structural balance: every cycle has an even number of
        negative edges, so no triangle has exactly one or three. Harary's
        theorem says a balanced network splits into (at most) two camps with
        positive edges inside and negative edges between; the node field `camp`
        (0 or 1) gets that split, or for an unbalanced network one that follows
        a spanning tree. Returns {"balanced": ..., "unbalanced": [(a, b, c), ...]
        (triangles with an odd number of negative edges), "frustrated": [edges
        that disagree with the camps]}. Direction is ignored."""
        gr = g()
        field = getattr(sign, "name", sign)
        nbr = {v: [] for v in gr._nodes_list()}
        sg = {}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            s = _sign(e, field)
            nbr[e._n1].append((e._n2, s))
            nbr[e._n2].append((e._n1, s))
            key = frozenset((e._n1, e._n2))
            sg[key] = s if key not in sg else min(sg[key], s)   # a negative tie wins over a positive one
        camp = {}
        for start in gr._nodes_list():
            if start in camp:
                continue
            camp[start] = 0
            todo = [start]
            while todo:
                u = todo.pop()
                for v, s in nbr[u]:
                    if v not in camp:
                        camp[v] = camp[u] if s > 0 else 1 - camp[u]
                        todo.append(v)
        f = gr.addNodeField(str(name), INTEGER, 0)
        for v, c in camp.items():
            f.set(v, c)
        frustrated = [e for e in gr._edges_list() if e._n1 is not e._n2
                      and (camp[e._n1] == camp[e._n2]) != (_sign(e, field) > 0)]
        nodes = gr._nodes_list()
        order = {v: i for i, v in enumerate(nodes)}
        adj = {v: {w for w, _ in nbr[v]} for v in nodes}
        bad = []
        for u in nodes:
            for v in adj[u]:
                if order[v] <= order[u]:
                    continue
                for w in adj[u] & adj[v]:
                    if order[w] <= order[v]:
                        continue
                    if sg[frozenset((u, v))] * sg[frozenset((v, w))] * sg[frozenset((u, w))] < 0:
                        bad.append((u, v, w))
        return {"balanced": not frustrated, "unbalanced": bad, "frustrated": GSet(frustrated, "frustrated edges")}

    def kComponents(k=2, name="kcomponent"):
        """kComponents(k) finds the k-components: the largest groups of nodes in
        which every pair is joined by at least k node-independent paths (k = 1:
        components; 2: bicomponents; 3: tricomponents). Unlike k-cores they need
        the paths, not just the degrees. Returns them as sets, largest first, and
        stores each node's (first) one in the field `name` (-1 for none); a node
        can belong to more than one, e.g. a cut node shared by two bicomponents.
        Direction is ignored. Exact for k <= 2; for k >= 3 uses networkx's
        k_components (Moody and White), which can be slow on big graphs."""
        import networkx as nx
        k = int(k)
        if k < 1:
            raise GuessError("k is at least 1")
        G = session.ns["toNetworkX"](directed=False)
        G.remove_edges_from(list(nx.selfloop_edges(G)))
        if k == 1:
            comps = [set(c) for c in nx.connected_components(G) if len(c) > 1]
        elif k == 2:
            comps = [set(c) for c in nx.biconnected_components(G) if len(c) > 2]
        else:
            comps = [set(c) for c in nx.k_components(G).get(k, [])]
        comps.sort(key=lambda c: (-len(c), min(map(str, c))))
        gr = g()
        f = gr.addNodeField(str(name), INTEGER, -1)
        for nd in gr._nodes_list():
            f.set(nd, -1)
        out = []
        for i in reversed(range(len(comps))):
            members = [gr._nodes[str(v)] for v in comps[i] if str(v) in gr._nodes]
            for nd in members:
                f.set(nd, i)
        for i, c in enumerate(comps):
            members = sorted((gr._nodes[str(v)] for v in c if str(v) in gr._nodes), key=lambda nd: nd._id)
            out.append(GSet(members, f"{k}-component {i}"))
        return out

    for fn in (katzCentrality, structuralBalance, kComponents):
        reg(fn.__name__, fn)
