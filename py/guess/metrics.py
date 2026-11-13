"""Measures from Newman, Networks, ch. 7 that GUESS's other modules lack:
Katz centrality with a chosen alpha and beta, structural balance of signed
networks, k-components, and regular-equivalence similarity."""
from .model import scatter_position, INT as INTEGER, GSet, GuessError


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

    def bowTie(name="bowtie"):
        """bowTie() splits a directed network the way the Web was described in
        2000: the largest strongly connected component ("core"), the nodes that
        can reach it but not be reached from it ("in"), those reached from it
        that can't reach back ("out"), "tube" nodes on paths from in to out that
        bypass the core, "tendril" nodes hanging off in or out, and "other"
        for nodes outside the core's weakly connected component. Sets the node
        field `bowtie` and returns the sizes, e.g. {"core": 224, "in": 89, ...}.
        Undirected edges count both ways."""
        import networkx as nx
        G = session.ns["toNetworkX"](directed=True)
        if len(G) == 0:
            raise GuessError("the graph has no nodes")
        core = max(nx.strongly_connected_components(G), key=len)
        seed = next(iter(core))
        out_ = nx.descendants(G, seed) - core
        in_ = nx.ancestors(G, seed) - core
        weak = next(c for c in nx.weakly_connected_components(G) if seed in c)
        rest = weak - core - out_ - in_
        from_in = set().union(*(nx.descendants(G, v) for v in in_)) if in_ else set()
        to_out = set().union(*(nx.ancestors(G, v) for v in out_)) if out_ else set()
        part = {}
        for v in G:
            if v in core:
                part[v] = "core"
            elif v in in_:
                part[v] = "in"
            elif v in out_:
                part[v] = "out"
            elif v in rest:
                part[v] = "tube" if (v in from_in and v in to_out) else "tendril"
            else:
                part[v] = "other"
        session.ns["setField"](part, str(name))
        sizes = {k: 0 for k in ("core", "in", "out", "tube", "tendril", "other")}
        for k in part.values():
            sizes[k] += 1
        return sizes

    def _tail_fit(vals, kmin):
        import math
        tail = [v for v in vals if v >= kmin]
        n = len(tail)
        sl = sum(math.log(v / (kmin - 0.5)) for v in tail)
        if n < 2 or sl <= 0:
            return None
        alpha = 1 + n / sl
        return alpha, (alpha - 1) / math.sqrt(n), n

    def fitPowerLaw(field="degree", kmin=None, shift=0):
        """fitPowerLaw(degree) fits a power law p(k) ~ k^-alpha to the values
        of a numeric node field (or a list of numbers) from kmin up, by maximum likelihood (Newman,
        Networks, eq. 10.9, with the -1/2 correction for whole numbers), not
        by drawing a line through a log-log plot. With kmin left out it is
        chosen as the value that makes the fitted distribution closest to the
        data (the smallest Kolmogorov-Smirnov distance; Clauset, Shalizi and
        Newman 2009). Returns {"alpha", "sigma" (its standard error), "kmin",
        "n" (values in the tail), "ks"}. shift=a fits a power law in k + a
        rather than k, as Price's model gives (p_k ~ (k + a)^-alpha); kmin and
        the returned kmin stay in units of k. plotFrequency(degree, cumulative=true,
        log=true, fit=true) draws the fit."""
        from .model import as_field
        if isinstance(field, (list, tuple)):                 # plain numbers (a degree sequence)
            fname = "values"
            raw = list(field)
        else:
            f = as_field(session.graph, field)
            fname = f.name
            raw = [f.get(e) for e in f.elements()]
        shift = float(shift)
        vals = sorted(float(v) + shift for v in raw
                      if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) + shift > 0)
        if len(vals) < 5:
            raise GuessError(f"{fname}: too few values above 0 to fit")

        def ks(kmin, alpha):
            tail = [v for v in vals if v >= kmin]
            n = len(tail)
            worst = 0.0
            for i, v in enumerate(tail):            # empirical P(K >= v) against the fit's, at each distinct value
                if i and tail[i - 1] == v:
                    continue
                emp = (n - i) / n
                fit = ((v - 0.5) / (kmin - 0.5)) ** (1 - alpha)
                worst = max(worst, abs(emp - fit))
            return worst

        if kmin is None:
            best = None
            for k in sorted(set(vals)):
                if sum(1 for v in vals if v >= k) < 10:
                    break
                r = _tail_fit(vals, k)
                if r is None:
                    continue
                d = ks(k, r[0])
                if best is None or d < best[0]:
                    best = (d, k, r)
            if best is None:
                raise GuessError(f"{fname}: not enough values to choose kmin")
            d, k, (alpha, sigma, n) = best
        else:
            k = float(kmin) + shift
            if k <= 0.5:
                raise GuessError("kmin must be at least 1")
            r = _tail_fit(vals, k)
            if r is None:
                raise GuessError(f"{fname}: too few values at or above kmin = {k:g}")
            alpha, sigma, n = r
            d = ks(k, alpha)
        k = int(k) if float(k).is_integer() else k
        if shift:
            k = k - shift
            k = int(k) if float(k).is_integer() else round(k, 6)
        return {"alpha": round(alpha, 4), "sigma": round(sigma, 4), "kmin": k, "n": n, "ks": round(d, 4)}

    def _degrees_arg(degrees, what):
        """A list of numbers, or a node field of the current graph (copied before it is replaced)."""
        if isinstance(degrees, (list, tuple)):
            vals = list(degrees)
        else:
            from .model import as_field
            f = as_field(session.graph, degrees)
            vals = [f.get(n) for n in session.graph._nodes_list()]
        out = []
        for v in vals:
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                raise GuessError(f"{what}: values must be numbers of at least 0, got {v!r}")
            out.append(v)
        if not out:
            raise GuessError(f"{what}: no values")
        return out

    def _replace_graph(n, edges, field, values, label, layout=True):
        import random as _r
        gr = session.graph
        gr.clear()
        nodes = []
        for i in range(n):
            v = gr.addNode(f"nd{i}")
            v.label = f"nd{i}"
            v.x, v.y = scatter_position(v._name)
            nodes.append(v)
        for a, b in edges:
            gr.addEdge(nodes[a], nodes[b], False)
        floats = any(not float(x).is_integer() for x in values)
        f = gr.addNodeField(field, "DOUBLE" if floats else INTEGER, 0.0 if floats else 0)
        for v, x in zip(nodes, values):
            f.set(v, float(x) if floats else int(x))
        session.scene()
        if layout and 0 < n <= 3000:
            session.ns["frLayout"]()
        loops = sum(1 for a, b in edges if a == b)
        pairs = {}
        for a, b in edges:
            if a != b:
                key = (min(a, b), max(a, b))
                pairs[key] = pairs.get(key, 0) + 1
        multi = sum(c - 1 for c in pairs.values())
        print(f"generated {label}: {n} nodes, {len(edges)} edges ({loops} self-loops, {multi} repeated edges)")
        return {"selfloops": loops, "multiedges": multi}

    def makeConfigurationModel(degrees, simple=False, seed=0, layout=True):
        """makeConfigurationModel([3, 2, 2, 1, ...]) replaces the graph with a
        random network with exactly those degrees: each node gets that many
        "stubs" (half-edges) and the stubs are paired up uniformly at random
        (Newman, Networks, section 12.1). Some pairs make self-loops or join
        nodes already joined; simple=true deletes those afterwards (so some
        degrees come out lower). degrees can be a node field of the current
        graph, e.g. makeConfigurationModel(degree), which randomises a network
        keeping its degrees. The node field `stubs` keeps each node's intended
        degree. The degrees must add up to an even number. Returns the counts of
        self-loops and repeated edges. layout=false skips the force-directed
        layout (for when you lay it out yourself). (GUESS's degree field counts a self-loop
        once; in the book's convention it adds 2 to the degree, which is what
        `stubs` holds.)"""
        import random as _r
        ks = [int(round(k)) for k in _degrees_arg(degrees, "makeConfigurationModel")]
        if sum(ks) % 2:
            raise GuessError(f"makeConfigurationModel: the degrees add up to {sum(ks)}, an odd number; "
                             "every edge has two ends, so the total must be even")
        stubs = [i for i, k in enumerate(ks) for _ in range(k)]
        _r.Random(seed).shuffle(stubs)
        edges = [(stubs[i], stubs[i + 1]) for i in range(0, len(stubs), 2)]
        counts = None
        if simple:
            seen, kept = set(), []
            for a, b in edges:
                key = (min(a, b), max(a, b))
                if a != b and key not in seen:
                    seen.add(key)
                    kept.append((a, b))
            counts = {"selfloops": sum(1 for a, b in edges if a == b),
                      "multiedges": len(edges) - len(kept) - sum(1 for a, b in edges if a == b)}
            edges = kept
        made = _replace_graph(len(ks), edges, "stubs", ks, "makeConfigurationModel", layout)
        if counts is not None:
            print(f"  simple=true removed {counts['selfloops']} self-loops and {counts['multiedges']} repeated edges")
            return {**counts, "removed": True}
        return made

    def makeExpectedDegree(weights, seed=0, layout=True):
        """makeExpectedDegree([5.5, 3, 1.2, ...]) replaces the graph with a random
        network in which each pair i, j is joined independently with
        probability w_i w_j / sum(w) (at most 1), so node i's expected degree is
        about w_i: the Chung-Lu model, the configuration model's cousin with
        independent edges (Newman, Networks, section 12.1.2). weights can be a
        node field of the current graph. No self-loops or repeated edges. The
        node field `expected` keeps w. layout=false skips the layout."""
        import random as _r
        w = [float(x) for x in _degrees_arg(weights, "makeExpectedDegree")]
        total = sum(w)
        if total <= 0:
            raise GuessError("makeExpectedDegree: the weights add up to 0")
        rnd = _r.Random(seed)
        edges = []
        for i in range(len(w)):
            for j in range(i + 1, len(w)):
                if rnd.random() < min(1.0, w[i] * w[j] / total):
                    edges.append((i, j))
        return _replace_graph(len(w), edges, "expected", w, "makeExpectedDegree", layout)

    def _build(n, edges, directed, node_fields, edge_fields, label, layout):
        """Replace the graph: n nodes nd0.., edges (a, b), and fields {name: (type, values)}."""
        import random as _r
        gr = session.graph
        gr.clear()
        nfs = {name: gr.addNodeField(name, t, 0) for name, (t, _v) in node_fields.items()}
        efs = {name: gr.addEdgeField(name, t, 0) for name, (t, _v) in edge_fields.items()}
        nodes = []
        for i in range(n):
            v = gr.addNode(f"nd{i}")
            v.label = f"nd{i}"
            v.x, v.y = scatter_position(v._name)
            for name, (_t, vals) in node_fields.items():
                nfs[name].set(v, vals[i])
            nodes.append(v)
        for k, (a, b) in enumerate(edges):
            e = gr.addEdge(nodes[a], nodes[b], directed)
            for name, (_t, vals) in edge_fields.items():
                efs[name].set(e, vals[k])
        session.scene()
        if layout and 0 < n <= 3000:
            session.ns["frLayout"]()
        print(f"generated {label}: {n} nodes, {len(edges)} edges")

    def makePriceModel(n, c=3, a=1.0, seed=0, layout=True):
        """makePriceModel(n, c, a) grows a citation network by Price's model
        (Newman, Networks, section 13.1): papers arrive one at a time, and each
        cites c earlier papers (on average, when c isn't a whole number),
        chosen with probability proportional to in-degree + a, so the
        much-cited get cited more (cumulative advantage). The in-degrees end up
        with a power-law tail of exponent 2 + a/c. Uses Newman's fast method:
        with probability c/(c + a) copy a citation made by a random earlier
        paper, otherwise pick a paper uniformly. Edges point from citing to
        cited. The field `born` gives each node's and edge's arrival step (paper
        k arrives at step k), so revealUpTo(step) replays the growth."""
        import random as _r
        n, c, a = int(n), float(c), float(a)
        if n < 2:
            raise GuessError("makePriceModel: n should be at least 2")
        if c <= 0 or a <= 0:
            raise GuessError("makePriceModel: c and a should be greater than 0")
        rnd = _r.Random(seed)
        edges, targets = [], []                      # targets: the cited end of every edge so far
        for new in range(1, n):
            want = int(c) + (1 if rnd.random() < c - int(c) else 0)
            want = min(want, new)
            cited = set()
            while len(cited) < want:
                if targets and rnd.random() < c / (c + a):
                    cited.add(rnd.choice(targets))   # in proportion to in-degree
                else:
                    cited.add(rnd.randrange(new))    # uniformly: the "+ a"
            for t in sorted(cited):
                edges.append((new, t))
                targets.append(t)
        _build(n, edges, True, {"born": (INTEGER, list(range(n)))},
               {"born": (INTEGER, [s_ for s_, _t in edges])}, "makePriceModel", layout)

    def makeBlockModel(sizes, p_in, p_out=None, seed=0, layout=True):
        """makeBlockModel([30, 30, 40], 0.3, 0.02) makes a stochastic block model:
        nodes in groups of the given sizes, each pair inside a group joined with
        probability p_in and each pair in different groups with p_out, so the
        network has community structure (Newman, Networks, section 12.11.6).
        p_in can instead be a matrix of probabilities between groups. The node
        field `block` gives each node's group (0, 1, ...)."""
        import random as _r
        sizes = [int(x) for x in sizes]
        if not sizes or min(sizes) < 1:
            raise GuessError("makeBlockModel: sizes are group sizes, each at least 1")
        k = len(sizes)
        if isinstance(p_in, (list, tuple)):
            P = [[float(x) for x in row] for row in p_in]
            if len(P) != k or any(len(r) != k for r in P):
                raise GuessError(f"makeBlockModel: the matrix should be {k} x {k}")
        else:
            if p_out is None:
                raise GuessError("makeBlockModel(sizes, p_in, p_out): give p_out, or a matrix as p_in")
            P = [[float(p_in) if i == j else float(p_out) for j in range(k)] for i in range(k)]
        if any(not 0 <= x <= 1 for r in P for x in r):
            raise GuessError("makeBlockModel: probabilities are between 0 and 1")
        block = [b for b, sz in enumerate(sizes) for _ in range(sz)]
        n = len(block)
        rnd = _r.Random(seed)
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rnd.random() < P[block[i]][block[j]]]
        _build(n, edges, False, {"block": (INTEGER, block)}, {}, "makeBlockModel", layout)

    def makeGrowingNetwork(n, m=2, gamma=1.0, a=1.0, extra=0.0, remove=0.0, seed=0, layout=True):
        """makeGrowingNetwork(n, m, gamma, a) grows an undirected network one node
        at a time (Newman, Networks, sections 13.2 and 13.4). Each new node links
        to m existing nodes chosen with probability proportional to
        (degree + a)^gamma: gamma = 1 is linear preferential attachment (a
        power law), gamma < 1 gives a stretched exponential, gamma > 1
        "condensation" where one node gets a finite share of all edges, and
        gamma = 0 is uniform attachment. extra= adds that many edges per step
        (on average) between existing nodes, both ends chosen the same way;
        remove= deletes that many random edges per step. Every node and edge
        has a `born` step; removed edges stay in the graph, hidden, with the
        step they were removed in `died` (-1 for edges still there), so
        revealUpTo(step) replays additions and removals."""
        import numpy as np
        n, m = int(n), int(m)
        gamma, a, extra, remove = float(gamma), float(a), float(extra), float(remove)
        if m < 1 or n <= m:
            raise GuessError("makeGrowingNetwork: need m >= 1 and n > m")
        if a <= 0 and gamma != 0:
            raise GuessError("makeGrowingNetwork: a should be greater than 0, since new nodes have degree 0 "
                             "(for the book's pure k^gamma kernel use a tiny a, e.g. 0.01)")
        rng = np.random.default_rng(seed)
        deg = np.zeros(n)
        edges, born, died, alive, have = [], [], [], [], set()

        def add_edge(u, v, step):
            key = (min(u, v), max(u, v))
            if u == v or key in have:
                return False
            have.add(key)
            edges.append((u, v)); born.append(step); died.append(-1); alive.append(len(edges) - 1)
            deg[u] += 1; deg[v] += 1
            return True

        def weights(k):
            w = (deg[:k] + a) ** gamma if gamma != 0 else np.ones(k)
            return w / w.sum()

        for u in range(m + 1):                         # a small starting clique: step 0
            for v in range(u + 1, m + 1):
                add_edge(u, v, 0)
        node_born = [0] * (m + 1)
        for new in range(m + 1, n):
            step = new - m
            node_born.append(step)
            for t in rng.choice(new, size=m, replace=False, p=weights(new)):
                add_edge(new, int(t), step)
            for _ in range(rng.poisson(extra) if extra > 0 else 0):
                u, v = rng.choice(new, size=2, p=weights(new))     # between nodes already there, not the newcomer
                add_edge(int(u), int(v), step)
            for _ in range(rng.poisson(remove) if remove > 0 else 0):
                if not alive:
                    break
                j = alive.pop(int(rng.integers(len(alive))))
                died[j] = step
                u, v = edges[j]
                deg[u] -= 1; deg[v] -= 1
                have.discard((min(u, v), max(u, v)))
        _build(n, edges, False, {"born": (INTEGER, node_born)},
               {"born": (INTEGER, born), "died": (INTEGER, died)}, "makeGrowingNetwork", layout)
        for e in session.graph._edges_list():
            if e.died >= 0:
                e.visible = False
        if remove > 0:
            print(f"  {sum(1 for d in died if d >= 0)} edges were removed along the way (hidden; field died)")

    def makeCopyingModel(n, c=3, copy=0.5, seed=0, layout=True):
        """makeCopyingModel(n, c, copy) grows a directed network by node copying
        (Newman, Networks, section 13.5, after Kleinberg et al.): each new node
        picks an existing node at random and goes through its c out-links; each
        one is copied with probability `copy`, otherwise replaced by a link to
        a node chosen uniformly at random. Without any preference this gives a
        power-law in-degree distribution with exponent 1 + 1/copy (it is Price's
        model with a = c(1 - copy)/copy). Starts from c + 1 nodes each linking
        to all the others. Fields: `born` (arrival step, on nodes and edges)
        and `copied` (the index of the node copied, -1 for the first nodes)."""
        import random as _r
        n, c, copy = int(n), int(c), float(copy)
        if c < 1 or n <= c + 1:
            raise GuessError("makeCopyingModel: need c >= 1 and n > c + 1")
        if not 0 <= copy <= 1:
            raise GuessError("makeCopyingModel: copy is a probability between 0 and 1")
        rnd = _r.Random(seed)
        outs = [[v for v in range(c + 1) if v != u] for u in range(c + 1)]
        node_born, copied = [0] * (c + 1), [-1] * (c + 1)
        edges, born = [(u, v) for u in range(c + 1) for v in outs[u]], [0] * ((c + 1) * c)
        for new in range(c + 1, n):
            src = rnd.randrange(new)
            mine = []
            for target in outs[src]:
                t = target if rnd.random() < copy else rnd.randrange(new)
                tries = 0
                while t in mine and tries < 20:          # keep the bibliography free of repeats
                    t, tries = rnd.randrange(new), tries + 1
                if t not in mine:
                    mine.append(t)
            outs.append(mine)
            step = new - c
            node_born.append(step)
            copied.append(src)
            for t in mine:
                edges.append((new, t))
                born.append(step)
        _build(n, edges, True, {"born": (INTEGER, node_born), "copied": (INTEGER, copied)},
               {"born": (INTEGER, born)}, "makeCopyingModel", layout)

    def _adjacency_lists():
        gr = g()
        nodes = gr._nodes_list()
        idx = {v: i for i, v in enumerate(nodes)}
        nbrs = [[] for _ in nodes]
        for e in gr._edges_list():
            a, b = idx[e._n1], idx[e._n2]
            nbrs[a].append(b)
            if a != b:
                nbrs[b].append(a)
        return nodes, nbrs

    def _sbm_loglik(M, nr, kr, dc):
        """Karrer and Newman's profile log-likelihoods: sum over group pairs r, s of
        m_rs log(m_rs / (n_r n_s)), or with degree correction m_rs log(m_rs / (k_r k_s));
        m_rr counts each inside edge twice."""
        import numpy as np
        size = kr if dc else nr
        den = np.outer(size, size)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where((M > 0) & (den > 0), M * np.log(M / np.where(den > 0, den, 1)), 0.0)
        return float(t.sum())

    def fitBlockModel(k=2, degreeCorrected=True, restarts=5, seed=0, name="sbm_class"):
        """fitBlockModel(k) divides the nodes into k groups by fitting a
        stochastic block model by maximum likelihood (Newman, Networks,
        section 14.4; Karrer and Newman 2011): the groups that make the
        observed edges most probable. degreeCorrected=True (the default)
        allows hubs and small nodes in the same group; the plain model
        (False) tends to put hubs in one group and everyone else in another,
        as on the karate club. Uses Kernighan-Lin passes of single-node moves
        from `restarts` random starts and keeps the best. Stores the groups in
        the field `name` (0 = largest) and returns {"loglik": ..., "k": k}.
        Edge direction and self-loops are ignored. Meant for networks of up to
        a few hundred nodes."""
        import numpy as np
        nodes, nbrs = _adjacency_lists()
        nbrs = [[j for j in ns if j != i] for i, ns in enumerate(nbrs)]
        n, k = len(nodes), int(k)
        if not 1 <= k <= n:
            raise GuessError("fitBlockModel: k should be between 1 and the number of nodes")
        deg = np.array([len(x) for x in nbrs], float)
        dc = bool(degreeCorrected)
        rng = np.random.default_rng(seed)

        def kl_pass(grp):
            M, nr, kr = _counts(grp, nbrs, deg, k)
            L = _sbm_loglik(M, nr, kr, dc)
            moved = np.zeros(n, bool)
            best_state, best_L = grp.copy(), L
            for _step in range(n):
                choice = None
                for i in np.flatnonzero(~moved):
                    r = grp[i]
                    cnt = np.bincount(grp[nbrs[i]], minlength=k).astype(float) if nbrs[i] else np.zeros(k)
                    for t in range(k):
                        if t == r:
                            continue
                        M2 = M.copy()
                        _move(M2, cnt, r, t)
                        nr2, kr2 = nr.copy(), kr.copy()
                        nr2[r] -= 1; nr2[t] += 1
                        kr2[r] -= deg[i]; kr2[t] += deg[i]
                        L2 = _sbm_loglik(M2, nr2, kr2, dc)
                        if choice is None or L2 > choice[0]:
                            choice = (L2, i, t, M2, nr2, kr2)
                if choice is None:
                    break
                L, i, t, M, nr, kr = choice
                grp[i] = t
                moved[i] = True
                if L > best_L + 1e-9:
                    best_state, best_L = grp.copy(), L
            return best_state, best_L

        best = None
        for _ in range(max(1, int(restarts))):
            grp = rng.integers(k, size=n)
            L = _sbm_loglik(*_counts(grp, nbrs, deg, k), dc)
            while True:                                   # passes until one no longer helps
                new_grp, new_L = kl_pass(grp.copy())
                if new_L <= L + 1e-9:
                    break
                grp, L = new_grp, new_L
            if best is None or L > best[0]:
                best = (L, grp.copy())
        L, grp = best
        order = sorted(range(k), key=lambda r: -int((grp == r).sum()))
        relabel = {r: i for i, r in enumerate(order)}
        session.ns["setField"]({nodes[i]: relabel[int(grp[i])] for i in range(n)}, str(name))
        return {"loglik": round(L, 4), "k": k}

    def _move(M, cnt, r, t):
        """Update the group-pair counts m (each edge counted from both ends) when a node with
        cnt[u] neighbours in each group u moves from group r to group t."""
        for u in range(len(cnt)):
            c = cnt[u]
            if c:
                M[r, u] -= c; M[u, r] -= c
                M[t, u] += c; M[u, t] += c

    def _counts(grp, nbrs, deg, k):
        import numpy as np
        M = np.zeros((k, k))
        for i, ns in enumerate(nbrs):
            for j in ns:
                M[grp[i], grp[j]] += 1
        return M, np.bincount(grp, minlength=k).astype(float), np.bincount(grp, weights=deg, minlength=k)

    def makeLFR(n=250, tau1=2.5, tau2=1.5, mu=0.1, degree=10, maxDegree=None, minCommunity=20, seed=0, layout=True):
        """makeLFR(n, tau1, tau2, mu) makes a Lancichinetti-Fortunato-Radicchi
        benchmark network: power-law degrees (exponent tau1) and community sizes
        (exponent tau2), with a share mu of each node's edges leaving its
        community (Newman, Networks, section 14.6.2). mu near 0 gives obvious
        communities; past about 0.5 they stop being communities at all. The
        node field `community` holds the planted groups (0 = largest), to
        compare with what an algorithm finds: compareClusters(louvain_class,
        community). degree= is the mean degree. The construction fails for some
        seeds, so up to ten seeds from seed= are tried (the one used is
        printed); if all fail, try larger communities or a lower mu."""
        nx = __import__("networkx")
        G, last = None, None
        for tries in range(10):                       # networkx gives up on some seeds: try the next few
            try:
                G = nx.LFR_benchmark_graph(int(n), float(tau1), float(tau2), float(mu), average_degree=float(degree),
                                           max_degree=int(maxDegree) if maxDegree else None,
                                           min_community=int(minCommunity), seed=int(seed) + tries, max_iters=500)
                break
            except Exception as ex:  # noqa: BLE001
                last = ex
        if G is None:
            raise GuessError(f"makeLFR couldn't build that network ({type(last).__name__}: {last}); "
                             "try a larger minCommunity, a larger n or a lower mu") from None
        if tries:
            print(f"  (seed {int(seed)} didn't work out; used seed {int(seed) + tries})")
        comms = []
        for v in G:
            c = frozenset(G.nodes[v]["community"])
            if c not in comms:
                comms.append(c)
        comms.sort(key=lambda c: (-len(c), min(c)))
        cid = {v: i for i, c in enumerate(comms) for v in c}
        G.remove_edges_from(list(nx.selfloop_edges(G)))
        order = sorted(G)
        index = {v: i for i, v in enumerate(order)}
        _build(len(order), [(index[a], index[b]) for a, b in G.edges()], False,
               {"community": (INTEGER, [cid[v] for v in order])}, {}, "makeLFR", layout)
        print(f"  {len(comms)} planted communities (field community), mixing mu = {float(mu):g}")

    def corePeriphery(name="core"):
        """corePeriphery() splits the nodes into a densely connected core and a
        periphery that links to the core but hardly to itself (Newman, Networks,
        section 14.7.3; Borgatti and Everett's discrete model): the split that
        best matches the ideal pattern where every pair involving a core node
        is linked and no pair of peripheral nodes is. Sets the node field
        `core` (1 in the core, 0 outside) and returns {"core": size, "fit": the
        correlation with the ideal pattern}. Direction is ignored."""
        import numpy as np
        nodes, nbrs = _adjacency_lists()
        n = len(nodes)
        if n < 3:
            raise GuessError("corePeriphery needs at least 3 nodes")
        A = np.zeros((n, n))
        for i, ns in enumerate(nbrs):
            for j in ns:
                if i != j:
                    A[i, j] = A[j, i] = 1.0
        iu = np.triu_indices(n, 1)
        a = A[iu]

        def fit(core):
            ideal = (core[:, None] | core[None, :]).astype(float)[iu]
            if ideal.std() == 0 or a.std() == 0:
                return -1.0
            return float(np.corrcoef(a, ideal)[0, 1])
        deg = A.sum(1)
        best_core, best = None, -2.0
        for size in range(1, n):                       # start from the top nodes by degree, then refine
            core = np.zeros(n, bool)
            core[np.argsort(-deg)[:size]] = True
            f = fit(core)
            if f > best:
                best, best_core = f, core
        core = best_core.copy()
        improved = True
        while improved:                                # single-node flips while they help
            improved = False
            for i in np.argsort(-deg):
                core[i] = not core[i]
                f = fit(core)
                if f > best + 1e-12:
                    best, improved = f, True
                else:
                    core[i] = not core[i]
        session.ns["setField"]({nodes[i]: int(core[i]) for i in range(n)}, str(name))
        return {"core": int(core.sum()), "fit": round(best, 4)}

    def rankNodes(name="rank", alpha=0.0):
        """rankNodes() places the nodes of a directed network on a ladder so that
        edges mostly point the same way (Newman, Networks, section 14.7.4): the
        SpringRank method (De Bacco, Larremore and Moore 2018), where each edge
        i -> j is a spring pulling i one unit above j. Use it for dominance,
        endorsement or who-hires-whose-graduates networks. Sets the node field
        `rank` (higher = above) and returns the share of edges that point
        downwards, from higher to lower rank. alpha > 0 pulls ranks toward 0
        (useful when the network is in pieces)."""
        import numpy as np
        gr = g()
        nodes = gr._nodes_list()
        idx = {v: i for i, v in enumerate(nodes)}
        n = len(nodes)
        A = np.zeros((n, n))
        for e in gr._edges_list():
            if e._n1 is not e._n2:
                A[idx[e._n1], idx[e._n2]] += 1.0
                if not e._directed:
                    A[idx[e._n2], idx[e._n1]] += 1.0
        dout, din = A.sum(1), A.sum(0)
        L = np.diag(dout + din) - (A + A.T) + float(alpha) * np.eye(n)
        b = dout - din
        rank = np.linalg.lstsq(L, b, rcond=None)[0]
        rank -= rank.min()
        session.ns["setField"]({nodes[i]: float(rank[i]) for i in range(n)}, str(name))
        down = sum(A[i, j] for i in range(n) for j in range(n) if A[i, j] and rank[i] > rank[j])
        total = A.sum()
        return round(float(down / total), 4) if total else 1.0

    for fn in (katzCentrality, structuralBalance, kComponents, bowTie, fitPowerLaw, makeConfigurationModel,
               makeExpectedDegree, makePriceModel, makeBlockModel, makeGrowingNetwork, makeCopyingModel,
               fitBlockModel, makeLFR, corePeriphery, rankNodes):
        reg(fn.__name__, fn)
