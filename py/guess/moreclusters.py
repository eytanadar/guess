"""More clustering: the community-detection plugins Gephi users reach for,
plus overlapping communities and a way to see them.

    chineseWhispersClusters()      fast label spreading (Biemann 2006)     -> cw_class
    mclClusters(inflation=2)       Markov clustering (van Dongen 2000)     -> mcl_class
    dbscanClusters((x, y))         density clusters of positions or fields  -> dbscan_class
    mcodeClusters()                dense protein-complex style regions      -> mcode_class
                                   (Bader & Hogue 2003)

Overlapping communities (a node can be in several):

    cliquePercolationClusters(k=3) k-clique percolation (Palla et al. 2005) -> cpm_classes
    linkCommunities()              communities of edges (Ahn et al. 2010)  -> link_classes,
                                                                             edge link_class
    showOverlaps(communities)      a colour per community; nodes in several
                                   drawn as pies with a slice per community

Single-membership commands store the community of each node in an INT field
(0 = largest, -1 = none). Overlapping ones store a text field listing the
communities ("0;3", "" for none) and an INT field counting them
(cpm_count, link_count).
"""
import math
import random
from collections import Counter, defaultdict

import numpy as np

from . import colors
from .algorithms import _nx, to_networkx
from .model import EDGE, INT, NODE, Field, GSet, GuessError, Node, as_field

MCL_MAX = 3000          # nodes in one connected piece (dense matrices)
MAX_LEGEND = 20


def _plural(word):
    return word[:-1] + "ies" if word.endswith("y") and word[-2:-1] not in "aeiou" else word + "s"


def _ranked(groups):
    """Groups (iterables of nodes), largest first, ties by smallest node id."""
    return sorted((sorted(c, key=lambda n: n._id) for c in groups if c),
                  key=lambda c: (-len(c), c[0]._id))


def _result(groups, label, annotation=None):
    return GSet((GSet(c, f"{label} {i}") for i, c in enumerate(groups)),
                annotation or f"{len(groups)} {_plural(label)}")


def _weight(e):
    v = e._vals.get("weight", 1.0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.0
    return v if math.isfinite(v) and v > 0 else 0.0


def _adjacency(g, weighted=True):
    """{node: {neighbour: weight}} ignoring direction and self loops."""
    adj = {n: {} for n in g._nodes_list()}
    for e in g._edges_list():
        a, b = e._n1, e._n2
        if a is b:
            continue
        w = _weight(e) if weighted else 1.0
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w
    return adj


def _pieces(adj):
    """Connected pieces of an adjacency dict."""
    seen, out = set(), []
    for s in adj:
        if s in seen:
            continue
        comp, stack = [], [s]
        seen.add(s)
        while stack:
            v = stack.pop()
            comp.append(v)
            for u in adj[v]:
                if u not in seen:
                    seen.add(u)
                    stack.append(u)
        out.append(comp)
    return out


# --------------------------------------------------------------------------
# algorithms (pure functions on adjacency dicts / arrays)
# --------------------------------------------------------------------------

def chinese_whispers(adj, iterations=20, seed=0):
    rng = random.Random(seed)
    nodes = list(adj)
    label = {n: i for i, n in enumerate(nodes)}
    for _ in range(max(1, int(iterations))):
        rng.shuffle(nodes)
        changed = False
        for v in nodes:
            if not adj[v]:
                continue
            score = defaultdict(float)
            for u, w in adj[v].items():
                score[label[u]] += w
            best = max(score.values())
            choices = sorted(k for k, s in score.items() if s == best)
            new = choices[0] if len(choices) == 1 else rng.choice(choices)
            if new != label[v]:
                label[v] = new
                changed = True
        if not changed:
            break
    groups = defaultdict(list)
    for v, k in label.items():
        groups[k].append(v)
    return list(groups.values())


def mcl(adj, inflation=2.0, expansion=2, loops=True, iterations=100):
    """Markov clustering on each connected piece; returns lists of nodes."""
    out = []
    for comp in _pieces(adj):
        if len(comp) == 1:
            out.append(comp)
            continue
        if len(comp) > MCL_MAX:
            raise GuessError(f"mclClusters works on pieces of up to {MCL_MAX} nodes (this one has {len(comp)}); "
                             "try chineseWhispersClusters() or leidenClusters() on large graphs")
        idx = {v: i for i, v in enumerate(comp)}
        k = len(comp)
        M = np.zeros((k, k))
        for v in comp:
            for u, w in adj[v].items():
                M[idx[u], idx[v]] = w
        if loops:
            # a self loop as heavy as the node's heaviest edge (the usual choice)
            M[np.arange(k), np.arange(k)] = np.maximum(M.max(axis=0), 1e-12)
        M /= np.maximum(M.sum(axis=0), 1e-300)
        for _ in range(max(1, int(iterations))):
            prev = M
            M = np.linalg.matrix_power(M, int(expansion))
            M = np.power(M, float(inflation))
            M[M < 1e-9] = 0.0
            M /= np.maximum(M.sum(axis=0), 1e-300)
            if np.abs(M - prev).max() < 1e-8:
                break
        # attractors are rows with mass; each column (node) joins the first attractor holding it
        assigned = {}
        for r in range(k):
            if M[r].max() <= 1e-6:
                continue
            for c in np.nonzero(M[r] > 1e-6)[0]:
                assigned.setdefault(int(c), r)
        groups = defaultdict(list)
        for c in range(k):
            groups[assigned.get(c, ("alone", c))].append(comp[c])
        out.extend(groups.values())
    return out


def _kdist(X, k, chunk=512):
    """Distance from each point to its k-th nearest other point."""
    n = len(X)
    out = np.empty(n)
    sq = (X * X).sum(axis=1)
    kk = min(k, n - 1)
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        d2 = sq[a:b, None] + sq[None, :] - 2 * X[a:b] @ X.T
        np.maximum(d2, 0, out=d2)
        d2[np.arange(b - a), np.arange(a, b)] = np.inf      # not itself
        out[a:b] = np.sqrt(np.partition(d2, kk - 1, axis=1)[:, kk - 1])
    return out


def knee_eps(X, k):
    """eps from the k-distance curve: the point furthest from the line joining
    its ends (the "knee"), as in Ester et al.'s sorted k-dist graph."""
    d = np.sort(_kdist(X, k))
    n = len(d)
    if n < 3 or d[-1] == d[0]:
        return float(d[-1]) or 1.0
    x = np.arange(n) / (n - 1)
    y = (d - d[0]) / (d[-1] - d[0])
    return float(d[int(np.argmax(x - y))]) or float(d[-1])


def dbscan(X, eps, min_pts, chunk=512):
    """Labels (-1 = noise) for the rows of X."""
    n = len(X)
    sq = (X * X).sum(axis=1)
    eps2 = eps * eps
    nbrs = []
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        d2 = sq[a:b, None] + sq[None, :] - 2 * X[a:b] @ X.T
        for i in range(b - a):
            nbrs.append(np.nonzero(d2[i] <= eps2 + 1e-12)[0])
    core = np.array([len(x) >= min_pts for x in nbrs])     # the point itself counts
    labels = np.full(n, -1)
    c = 0
    for i in range(n):
        if labels[i] != -1 or not core[i]:
            continue
        labels[i] = c
        stack = [i]
        while stack:
            p = stack.pop()
            if not core[p]:
                continue
            for q in nbrs[p]:
                if labels[q] == -1:
                    labels[q] = c
                    if core[q]:
                        stack.append(q)
        c += 1
    return labels


def _core_numbers(nodes, adj):
    """k-core number of each node of the subgraph on `nodes` (Batagelj-Zaversnik)."""
    nodes = set(nodes)
    deg = {v: sum(1 for u in adj[v] if u in nodes) for v in nodes}
    core = {}
    remaining = set(nodes)
    k = 0
    while remaining:
        k = max(k, min(deg[v] for v in remaining))
        layer = [v for v in remaining if deg[v] <= k]
        while layer:
            v = layer.pop()
            if v not in remaining:
                continue
            remaining.discard(v)
            core[v] = k
            for u in adj[v]:
                if u in remaining:
                    deg[u] -= 1
                    if deg[u] <= k:
                        layer.append(u)
    return core


def _density(nodes, adj):
    nodes = set(nodes)
    n = len(nodes)
    if n < 2:
        return 0.0
    m = sum(1 for v in nodes for u in adj[v] if u in nodes) / 2
    return m / (n * (n - 1) / 2)


def mcode(adj, degree_cutoff=2, score_cutoff=0.2, haircut=True, fluff=False, fluff_density=0.1,
          kcore=2, max_depth=100):
    """MCODE complexes as [(score, nodes)], best first, and the vertex weights."""
    weight = {}
    for v, nb in adj.items():
        if len(nb) < degree_cutoff:
            weight[v] = 0.0
            continue
        hood = [v, *nb]
        core = _core_numbers(hood, adj)
        k = max(core.values())
        top = [x for x in hood if core[x] >= k]
        weight[v] = k * _density(top, adj)
    seen = set()
    complexes = []
    for seed in sorted(adj, key=lambda v: (-weight[v], v._id)):
        if seed in seen or weight[seed] <= 0:
            continue
        cut = (1 - score_cutoff) * weight[seed]
        members = {seed}
        frontier = [(seed, 0)]
        while frontier:
            v, depth = frontier.pop()
            if depth >= max_depth:
                continue
            for u in adj[v]:
                if u not in members and u not in seen and weight[u] > cut:
                    members.add(u)
                    frontier.append((u, depth + 1))
        seen |= members
        core = _core_numbers(members, adj)
        if not core or max(core.values()) < kcore:
            continue
        if haircut:
            members = {v for v in members if core[v] >= kcore}
        if fluff:
            extra = set()
            for v in members:
                for u in adj[v]:
                    if u not in members and _density([u, *adj[u]], adj) > fluff_density:
                        extra.add(u)
            members |= extra
        if len(members) < 3:
            continue
        complexes.append((_density(members, adj) * len(members), members))
    complexes.sort(key=lambda c: (-c[0], -len(c[1])))
    return complexes, weight


def link_communities(g, threshold=None):
    """Ahn, Bagrow & Lehmann (2010): edges clustered by the similarity of their
    endpoints' neighbourhoods; returns ({edge: community}, best threshold, D)."""
    edges = [e for e in g._edges_list() if e._n1 is not e._n2]
    # one edge per pair of nodes (parallel edges share their pair's community)
    pair_edges = defaultdict(list)
    for e in edges:
        a, b = sorted((e._n1, e._n2), key=lambda n: n._id)
        pair_edges[(a, b)].append(e)
    pairs = list(pair_edges)
    if not pairs:
        return {}, None, 0.0
    M = len(pairs)
    nbr = defaultdict(set)
    for a, b in pairs:
        nbr[a].add(b)
        nbr[b].add(a)
    incl = {v: s | {v} for v, s in nbr.items()}
    eidx = {p: i for i, p in enumerate(pairs)}
    # similarity of edges (i, k) and (j, k) depends on i and j only
    sims = []                                      # (similarity, edge index, edge index)
    for k, ns in nbr.items():
        ns = sorted(ns, key=lambda n: n._id)
        for x in range(len(ns)):
            i = ns[x]
            ei = eidx[tuple(sorted((i, k), key=lambda n: n._id))]
            for y in range(x + 1, len(ns)):
                j = ns[y]
                a, b = incl[i], incl[j]
                s = len(a & b) / len(a | b)
                ej = eidx[tuple(sorted((j, k), key=lambda n: n._id))]
                sims.append((s, ei, ej))
    sims.sort(key=lambda t: -t[0])
    parent = list(range(M))
    nodes_of = [{pairs[i][0], pairs[i][1]} for i in range(M)]
    m_of = [1] * M

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def term(m, n):
        return 0.0 if n <= 2 else m * (m - (n - 1)) / ((n - 2) * (n - 1))

    total = 0.0                                   # sum of terms; D = 2 / M * total
    best_D, best_cut, best_merges = 0.0, None, 0
    merges = []                                   # (root kept, root absorbed)
    k = 0
    while k < len(sims):
        level = sims[k][0]
        if threshold is not None and level < threshold:
            break
        while k < len(sims) and sims[k][0] == level:
            _, x, y = sims[k]
            k += 1
            rx, ry = find(x), find(y)
            if rx == ry:
                continue
            total -= term(m_of[rx], len(nodes_of[rx])) + term(m_of[ry], len(nodes_of[ry]))
            if len(nodes_of[rx]) < len(nodes_of[ry]):
                rx, ry = ry, rx
            parent[ry] = rx
            nodes_of[rx] |= nodes_of[ry]
            m_of[rx] += m_of[ry]
            nodes_of[ry] = set()
            total += term(m_of[rx], len(nodes_of[rx]))
            merges.append((rx, ry))
        D = 2.0 / M * total
        if threshold is None and D > best_D + 1e-12:
            best_D, best_cut, best_merges = D, level, len(merges)
    if threshold is not None:
        best_cut, best_merges = threshold, len(merges)
        best_D = 2.0 / M * total
    # replay the chosen merges
    parent = list(range(M))
    for rx, ry in merges[:best_merges]:
        parent[ry] = rx
    groups = defaultdict(list)
    for i in range(M):
        groups[find(i)].append(i)
    out = {}
    for c, members in enumerate(groups.values()):
        for i in members:
            for e in pair_edges[pairs[i]]:
                out[e] = c
    return out, best_cut, best_D


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    view = session.view

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def store(field, groups, label):
        """Rank groups, write `field` (0 = largest, -1 = none), return the GSet."""
        g = session.graph
        ranked = _ranked(groups)
        f = g.addNodeField(field, INT, -1)
        which = {}
        for i, c in enumerate(ranked):
            for n in c:
                which[n] = i
        for n in g._nodes_list():
            f.set(n, which.get(n, -1))
        return ranked

    def store_overlapping(prefix, ranked):
        g = session.graph
        lists = defaultdict(list)
        for i, c in enumerate(ranked):
            for n in c:
                lists[n].append(i)
        fl = g.addNodeField(f"{prefix}_classes", "VARCHAR", "")
        fc = g.addNodeField(f"{prefix}_count", INT, 0)
        for n in g._nodes_list():
            ks = lists.get(n, [])
            fl.set(n, ";".join(map(str, ks)))
            fc.set(n, len(ks))
        return sum(1 for ks in lists.values() if len(ks) > 1)

    # ---- single membership ---------------------------------------------------------

    @cmd
    def chineseWhispersClusters(iterations=20, weighted=True, seed=0):
        """chineseWhispersClusters() finds communities by Chinese Whispers
        (Biemann 2006): every node starts in its own class and repeatedly takes
        the class with the most (weighted) ties among its neighbours. Fast and
        parameter-free; the number of communities isn't chosen in advance.
        Stores cw_class (0 = largest) and returns the communities.
        weighted=False ignores edge weights; seed=None varies the result."""
        g = session.graph
        groups = chinese_whispers(_adjacency(g, bool(weighted)), iterations, seed)
        ranked = store("cw_class", groups, "community")
        print(f"Chinese Whispers: {len(ranked)} communities (cw_class)")
        return _result(ranked, "community")

    @cmd
    def mclClusters(inflation=2.0, expansion=2, loops=True, iterations=100):
        """mclClusters() finds clusters by the Markov Cluster algorithm (MCL,
        van Dongen 2000): random walks are expanded and then "inflated" until
        flow stays inside clusters. inflation (1.2-5, default 2) sets the
        granularity: higher gives more, smaller clusters. Uses edge weights;
        loops=True adds self loops (recommended). Stores mcl_class.
        Works on connected pieces of up to 3000 nodes."""
        if float(inflation) <= 1:
            raise GuessError("inflation should be more than 1 (try 1.5 to 4)")
        if int(expansion) < 2:
            raise GuessError("expansion should be 2 or more")
        g = session.graph
        groups = mcl(_adjacency(g), float(inflation), int(expansion), bool(loops), int(iterations))
        ranked = store("mcl_class", groups, "cluster")
        print(f"MCL (inflation {float(inflation):g}): {len(ranked)} clusters (mcl_class)")
        return _result(ranked, "cluster")

    @cmd
    def dbscanClusters(fields=("x", "y"), eps=None, minPts=4):
        """dbscanClusters() groups nodes that lie close together on screen with
        DBSCAN (Ester et al. 1996): a cluster is a dense region (at least
        minPts nodes within eps of each other), and nodes in sparse areas are
        noise (dbscan_class -1). fields: numeric node fields to measure
        distance in, by default the positions (x, y); e.g.
        dbscanClusters((degree, pagerank)). Fields aren't rescaled, so give
        them comparable ranges. eps=None picks it from the knee of the sorted
        k-distance curve and prints it."""
        g = session.graph
        fs = [as_field(g, f, "dbscanClusters", (NODE,)) for f in
              (fields if isinstance(fields, (list, tuple)) else [fields])]
        if not fs:
            raise GuessError("dbscanClusters needs at least one numeric node field")
        minPts = int(minPts)
        if minPts < 1:
            raise GuessError("minPts should be at least 1")
        rows, nodes = [], []
        for n in g._nodes_list():
            vals = []
            for f in fs:
                v = f.get(n)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = float("nan")
                vals.append(v)
            if all(math.isfinite(v) for v in vals):
                rows.append(vals)
                nodes.append(n)
        if not nodes:
            raise GuessError(f"no node has numeric values for {', '.join(f.name for f in fs)}")
        X = np.array(rows, float)
        if eps is None:
            eps = knee_eps(X, minPts) if len(X) > 1 else 1.0
            print(f"dbscanClusters: eps = {eps:.4g} (from the k-distance curve)")
        elif float(eps) <= 0:
            raise GuessError("eps should be a positive distance")
        labels = dbscan(X, float(eps), minPts)
        groups = defaultdict(list)
        for n, lab in zip(nodes, labels):
            if lab >= 0:
                groups[int(lab)].append(n)
        ranked = store("dbscan_class", groups.values(), "cluster")
        noise = len(g._nodes_list()) - sum(map(len, ranked))
        print(f"DBSCAN: {len(ranked)} clusters, {noise} noise nodes (dbscan_class; -1 = noise)")
        return _result(ranked, "cluster", f"{len(ranked)} clusters, {noise} noise")

    @cmd
    def mcodeClusters(degreeCutoff=2, scoreCutoff=0.2, haircut=True, fluff=False, fluffDensity=0.1,
                      kCore=2, maxDepth=100):
        """mcodeClusters() finds densely connected regions with MCODE (Bader &
        Hogue 2003), made for protein complexes in interaction networks. Each
        node is weighted by the density of the highest k-core of its
        neighbourhood; complexes grow from the heaviest seeds through
        neighbours weighing at least (1 - scoreCutoff) of the seed's. Defaults
        are the paper's: degreeCutoff 2, scoreCutoff 0.2, haircut (keep only
        the 2-core) on, fluff (add dense neighbours, fluffDensity) off, kCore 2,
        maxDepth 100. Stores mcode_class (0 = best scoring, -1 = in none) and
        mcode_score (the node weight); returns the complexes, best first, and
        prints their scores (density x size)."""
        g = session.graph
        adj = _adjacency(g, weighted=False)
        complexes, weight = mcode(adj, int(degreeCutoff), float(scoreCutoff), bool(haircut), bool(fluff),
                                  float(fluffDensity), int(kCore), int(maxDepth))
        f = g.addNodeField("mcode_class", INT, -1)
        fw = g.addNodeField("mcode_score", "DOUBLE", 0.0)
        which = {}
        for i, (_, members) in enumerate(complexes):
            for n in members:
                which.setdefault(n, i)
        for n in g._nodes_list():
            f.set(n, which.get(n, -1))
            fw.set(n, round(weight.get(n, 0.0), 6))
        out = GSet((GSet(sorted(m, key=lambda n: n._id), f"complex {i} (score {sc:.2f})")
                    for i, (sc, m) in enumerate(complexes)), f"{len(complexes)} complexes")
        top = ", ".join(f"{sc:.2f}" for sc, _ in complexes[:5])
        print(f"MCODE: {len(complexes)} complexes (mcode_class)" + (f"; best scores {top}" if complexes else ""))
        return out

    # ---- overlapping -----------------------------------------------------------------

    @cmd
    def cliquePercolationClusters(k=3):
        """cliquePercolationClusters(k=3) finds overlapping communities by
        clique percolation (Palla et al. 2005): a community is a chain of
        k-cliques that share k-1 nodes, so a node can be in several (and many
        nodes are in none). Stores cpm_classes (e.g. "0;2"; "" for none) and
        cpm_count; returns the communities, largest first. showOverlaps(...)
        draws them."""
        k = int(k)
        if k < 2:
            raise GuessError("k should be 2 or more (3 is usual)")
        nx = _nx()
        g = session.graph
        G = to_networkx(g, directed=False)
        G.remove_edges_from(list(nx.selfloop_edges(G)))
        ranked = _ranked(nx.community.k_clique_communities(G, k))
        shared = store_overlapping("cpm", ranked)
        print(f"clique percolation (k={k}): {len(ranked)} communities, {shared} nodes in more than one (cpm_classes)")
        return _result(ranked, "community", f"{len(ranked)} overlapping communities")

    @cmd
    def linkCommunities(threshold=None, minEdges=2):
        """linkCommunities() finds overlapping communities by clustering edges
        (Ahn, Bagrow & Lehmann 2010): two edges sharing a node are similar when
        their other ends have similar neighbourhoods; edges are merged by
        single linkage and the dendrogram is cut where partition density is
        highest (or at similarity `threshold`, 0-1). Each edge gets link_class;
        a node belongs to the communities of its edges (link_classes "0;3",
        link_count). Communities of fewer than minEdges edges are dropped
        (link_class -1). Returns node communities, largest first."""
        g = session.graph
        ec, cut, D = link_communities(g, None if threshold is None else float(threshold))
        by = defaultdict(list)
        for e, c in ec.items():
            by[c].append(e)
        kept = sorted((es for es in by.values() if len(es) >= int(minEdges)),
                      key=lambda es: (-len(es), min(e._id for e in es)))
        fe = g.addEdgeField("link_class", INT, -1)
        eclass = {}
        for i, es in enumerate(kept):
            for e in es:
                eclass[e] = i
        for e in g._edges_list():
            fe.set(e, eclass.get(e, -1))
        node_groups = [sorted({n for e in es for n in (e._n1, e._n2)}, key=lambda n: n._id) for es in kept]
        shared = store_overlapping("link", node_groups)
        cut_s = "" if cut is None else f" at similarity {cut:.3g}"
        print(f"link communities: {len(kept)} communities{cut_s} (partition density {D:.3f}); "
              f"{shared} nodes in more than one (link_classes, edge link_class)")
        return _result(node_groups, "community", f"{len(kept)} overlapping communities")

    # ---- display ---------------------------------------------------------------------

    def memberships(communities):
        """[(label, [nodes])] from a GSet of sets or a field like cpm_classes."""
        g = session.graph
        if isinstance(communities, (Field, str)):
            f = as_field(g, communities, "showOverlaps", (NODE,))
            groups = defaultdict(list)
            for n in g._nodes_list():
                v = f.get(n)
                if v is None or v == "":
                    continue
                parts = str(v).split(";") if isinstance(v, str) else [v]
                for p in parts:
                    p = p.strip()
                    if p in ("", "-1"):
                        continue
                    groups[p].append(n)
            keys = sorted(groups, key=lambda p: (int(p) if p.lstrip("-").isdigit() else math.inf, p))
            return [(f"{f.name.removesuffix('_classes').removesuffix('_class')} {p}", groups[p]) for p in keys]
        out = []
        for i, c in enumerate(communities):
            if isinstance(c, Node):
                raise GuessError("showOverlaps needs communities (a set of sets, e.g. the result of "
                                 "cliquePercolationClusters()) or a field such as cpm_classes")
            nodes = [n for n in (c if hasattr(c, "__iter__") else []) if isinstance(n, Node)]
            if nodes:
                out.append((getattr(c, "annotation", None) or f"community {i}", nodes))
        return out

    @cmd
    def showOverlaps(communities, hulls=False, none="lightgray"):
        """showOverlaps(communities) shows overlapping communities: each gets
        its own colour, a node in one takes that colour, a node in several is
        drawn as a pie with a slice per community, and nodes in none are
        lightgray (none=...). communities: the result of
        cliquePercolationClusters()/linkCommunities(), any set of sets, or a
        field listing them (cpm_classes, link_classes, or a class field).
        hulls=True also shades each community. removePies() goes back to
        plain nodes."""
        g = session.graph
        groups = memberships(communities)
        if not groups:
            raise GuessError("no communities to show")
        cols = colors.distinctColors(len(groups))
        member_of = defaultdict(list)
        for k, (_, nodes) in enumerate(groups):
            for n in nodes:
                member_of[n].append(k)
        for n in g._nodes_list():
            ks = member_of.get(n)
            n.color = cols[ks[0]] if ks else none
        view.pie = {"mode": "members", "labels": [lab for lab, _ in groups], "colors": cols,
                    "members": {n._name: ks for n, ks in member_of.items() if len(ks) > 1}}
        if hulls:
            make = session.ns.get("createConvexHull")
            for (_, nodes), c in zip(groups, cols):
                if len(nodes) >= 3 and make is not None:
                    make(GSet(nodes), c + ",70")
        _pie_legend()
        overlap = sum(1 for ks in member_of.values() if len(ks) > 1)
        print(f"{len(groups)} communities; {overlap} nodes in several (pies), "
              f"{len(g._nodes_list()) - len(member_of)} in none")

    def _pie_legend():
        from .visuals import Legend
        g = session.graph
        for n in g._nodes_list():
            g._mark(n)
        old = getattr(view, "pie_legend", None)
        if old is not None:
            view.legends.pop(old, None)
        view.pie_legend = None
        if view.pie:
            lg = Legend(view, view.next_id())
            labels, cols = view.pie["labels"], view.pie["colors"]
            for label, c in list(zip(labels, cols))[:MAX_LEGEND]:
                lg.add(c, label)
            if len(labels) > MAX_LEGEND:
                lg.add("200,200,200", f"… {len(labels) - MAX_LEGEND} more")
            view.legends[lg._id] = lg
            view.pie_legend = lg._id
        view.changed()


__all__ = ["install", "chinese_whispers", "mcl", "dbscan", "knee_eps", "mcode", "link_communities"]
