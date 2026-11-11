"""motifLayout(): a structure-aware layout, ported from LUMINA (the IntAct
team's Cytoscape.js layout, MIT licence, (c) 2026 EMBL-EBI).

It finds the small shapes that make big networks unreadable when drawn by
forces, and gives each its own clean arrangement:

    cycle      nodes on a ring                      -> a circle
    chain      a path ending in a leaf              -> a ring hanging off its anchor
    star       a node and its leaves                -> the node with its leaves in rings
    parallel   nodes with exactly the same neighbours -> a grid between those neighbours

Each structure is collapsed into one virtual node sized to fit its
arrangement; the virtual nodes are laid out by stress majorization (graph
distances become screen distances, with room for each structure), pushed
apart where they overlap, and expanded. Each connected component is then
turned to its smallest bounding box and the components are packed.

Differences from LUMINA: cycles come from a cycle basis rather than an
exhaustive search (fast on big networks); leaves of cycle nodes stay with the
cycle; there is no step-by-step mode and no compound nodes (outline=true
draws a shape around each structure instead).
"""
import heapq
import math

import numpy as np

from .layouts import _binpack_positions, _Layouts, _num
from .model import STRING, GuessError

KINDS = ("cycle", "chain", "star", "parallel", "single")


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

def _cycle_basis(nb, allowed):
    """A cycle basis (Paton's algorithm) of the subgraph on `allowed` nodes."""
    cycles = []
    seen = set()
    for root in sorted(allowed):
        if root in seen:
            continue
        stack = [root]
        pred = {root: root}
        used = {root: set()}
        while stack:
            z = stack.pop()
            seen.add(z)
            zused = used[z]
            for w in nb[z]:
                if w not in allowed:
                    continue
                if w not in used:
                    pred[w] = z
                    stack.append(w)
                    used[w] = {z}
                elif w == z:
                    continue
                elif w not in zused:
                    pw = used[w]
                    cycle = [w, z]
                    p = pred[z]
                    while p not in pw:
                        cycle.append(p)
                        p = pred[p]
                    cycle.append(p)
                    cycles.append(cycle)
                    used[w].add(z)
    # Paton's cycles repeat the closing node; normalise to simple cycles
    out = []
    for c in cycles:
        seen_c, simple = set(), []
        for v in c:
            if v not in seen_c:
                seen_c.add(v)
                simple.append(v)
        if len(simple) >= 3:
            out.append(simple)
    return out


def _order_cycle(nodes, nb):
    """Order a cycle's nodes so neighbours on the ring are linked."""
    s = set(nodes)
    start = nodes[0]
    order, prev, cur = [start], None, start
    while True:
        nxt = [w for w in nb[cur] if w in s and w != prev and w not in order[1:]]
        nxt = [w for w in nxt if w not in order]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    if len(order) != len(nodes):
        return list(nodes)            # not a simple ring: keep the given order
    return order


def detect(nb, opts):
    """Assign every node to a structure. nb: list of neighbour sets (no
    self-loops). Returns a list of groups: dicts with kind, nodes (ordered),
    and kind-specific extras (hub, anchor, sats, shared)."""
    n = len(nb)
    deg = [len(x) for x in nb]
    owner = [-1] * n
    groups = []

    def add(kind, nodes, **extra):
        gi = len(groups)
        groups.append(dict(kind=kind, nodes=list(nodes), **extra))
        for v in nodes:
            owner[v] = gi
        return gi

    # 1. parallel: nodes sharing exactly the same neighbours (first, so the
    # small cycles they form with those neighbours don't count as rings)
    sig = {}
    for v in range(n):
        if deg[v] >= opts["minParallel"]:
            sig.setdefault(frozenset(nb[v]), []).append(v)
    for shared, members in sorted(sig.items(), key=lambda kv: min(kv[1])):
        if len(members) >= 2 and not (set(members) & shared):
            add("parallel", members, shared=sorted(shared))

    # 2. cycles among low-degree nodes (leaves can't be on one)
    if opts["cycles"]:
        allowed = {v for v in range(n) if 2 <= deg[v] < opts["maxCycleDegree"]}
        cand = [c for c in _cycle_basis(nb, allowed) if opts["minCycle"] <= len(c) <= opts["maxCycle"]]
        cand.sort(key=lambda c: (-len(c), min(c)))
        for c in cand:
            if all(owner[v] < 0 for v in c):
                add("cycle", _order_cycle(c, nb), sats={})

    # 3. chains: from a leaf along nodes with two neighbours
    for leaf in range(n):
        if deg[leaf] != 1 or owner[leaf] >= 0:
            continue
        path, prev, cur = [leaf], None, leaf
        while True:
            nxt = [w for w in nb[cur] if w != prev]
            if len(nxt) != 1:
                break
            w = nxt[0]
            if owner[w] >= 0 or deg[w] != 2 or w in path:
                break
            path.append(w)
            prev, cur = cur, w
        anchor = next((w for w in nb[path[-1]] if w not in path), None)
        if len(path) >= opts["minChain"] and len(path) >= 2:
            add("chain", list(reversed(path)), anchor=anchor)    # first node next to the anchor

    # 4. leaves around their node: a star, or satellites of the cycle it's on
    leaves_of = {}
    for v in range(n):
        if deg[v] == 1 and owner[v] < 0:
            p = next(iter(nb[v]))
            leaves_of.setdefault(p, []).append(v)
    for p, leaves in sorted(leaves_of.items()):
        if owner[p] >= 0 and groups[owner[p]]["kind"] == "cycle":
            g = groups[owner[p]]
            g["sats"][p] = leaves
            for v in leaves:
                owner[v] = owner[p]
            g["nodes"].extend(leaves)
        elif owner[p] < 0 and (len(leaves) >= opts["minStar"] or opts["leavesAround"]):
            add("star", [p] + leaves, hub=p)

    # 5. the rest, one by one
    for v in range(n):
        if owner[v] < 0:
            add("single", [v])
    return groups, owner


# --------------------------------------------------------------------------
# geometry of each structure
# --------------------------------------------------------------------------

def _star_rings(k, base, sp):
    """[(count, radius)] of a star's rings: up to 2*base leaves on one ring
    (widened to fit them), more in concentric rings holding base, 2*base, …"""
    if k <= 2 * base:
        return [(k, max(sp, k * sp / (2 * math.pi)))]
    rings, left, j = [], k, 1
    while left > 0:
        c = min(left, base * j)
        rings.append((c, j * sp))
        left -= c
        j += 1
    return rings


def radius(g, size, sp, opts):
    """The radius of the circle a structure needs."""
    nodes = g["nodes"]
    big = max(size[v] for v in nodes) / 2
    kind = g["kind"]
    if kind == "single":
        return big
    if kind == "cycle":
        L = len(nodes) - sum(len(x) for x in g["sats"].values())
        R = max(L * sp / (2 * math.pi), sp / 2)
        return R + big + (sp if g["sats"] else 0)
    if kind == "chain":
        R = max(len(nodes) * sp / (2 * math.pi), sp * 0.75)
        return R + big
    if kind == "star":
        rings = _star_rings(len(nodes) - 1, opts["starBase"], sp * opts["ringSpacing"])
        return rings[-1][1] + big
    if kind == "parallel":
        m = len(nodes)
        cols = math.ceil(math.sqrt(m))
        rows = math.ceil(m / cols)
        return math.hypot(cols - 1, rows - 1) * sp / 2 + big
    return big


def _rot(P, a):
    c, s = math.cos(a), math.sin(a)
    return P @ np.array([[c, s], [-s, c]])


def expand(g, centre, size, sp, opts, target_of):
    """Positions (centres) of a structure's nodes around `centre`.
    target_of(v): where node v's outside links pull it (a point), or None."""
    nodes = g["nodes"]
    kind = g["kind"]
    out = {}
    cx, cy = centre
    if kind == "single":
        out[nodes[0]] = (cx, cy)
        return out
    if kind == "star":
        hub = g["hub"]
        out[hub] = (cx, cy)
        leaves = nodes[1:]
        # leaves leave a gap facing where the hub's other links go
        t = target_of(hub)
        start = math.atan2(t[1] - cy, t[0] - cx) if t is not None else -math.pi / 2
        i = 0
        for cnt, r in _star_rings(len(leaves), opts["starBase"], sp * opts["ringSpacing"]):
            for k in range(cnt):
                a = start + 2 * math.pi * (k + 0.5) / cnt
                out[leaves[i]] = (cx + r * math.cos(a), cy + r * math.sin(a))
                i += 1
        return out
    if kind == "cycle":
        sats = g["sats"]
        ring = [v for v in nodes if not any(v in ls for ls in sats.values())]
        L = len(ring)
        R = max(L * sp / (2 * math.pi), sp / 2)
        targets = [target_of(v) for v in ring]
        best, best_cost = None, math.inf
        for direction in (1, -1):
            for off in range(L):
                cost = 0.0
                for i, t in enumerate(targets):
                    if t is None:
                        continue
                    a = direction * 2 * math.pi * (i + off) / L
                    px, py = cx + R * math.cos(a), cy + R * math.sin(a)
                    cost += math.hypot(px - t[0], py - t[1])
                if cost < best_cost - 1e-9:
                    best, best_cost = (direction, off), cost
        direction, off = best
        for i, v in enumerate(ring):
            a = direction * 2 * math.pi * (i + off) / L
            out[v] = (cx + R * math.cos(a), cy + R * math.sin(a))
            leaves = sats.get(v, [])
            for k, leaf in enumerate(leaves):
                spread = 0 if len(leaves) == 1 else (k / (len(leaves) - 1) - 0.5) * min(1.6, 0.35 * len(leaves))
                b = a + spread
                rr = R + sp
                out[leaf] = (cx + rr * math.cos(b), cy + rr * math.sin(b))
        return out
    if kind == "chain":
        L = len(nodes)
        R = max(L * sp / (2 * math.pi), sp * 0.75)
        t = target_of(nodes[0])
        a0 = math.atan2(t[1] - cy, t[0] - cx) if t is not None else 0.0
        step = 2 * math.pi / max(L, 1) if L * sp >= 2 * math.pi * R - 1e-9 else sp / R
        for i, v in enumerate(nodes):
            a = a0 + i * step
            out[v] = (cx + R * math.cos(a), cy + R * math.sin(a))
        return out
    if kind == "parallel":
        m = len(nodes)
        cols = math.ceil(math.sqrt(m))
        rows = math.ceil(m / cols)
        # the grid's rows run across the line between the shared neighbours
        shared = g.get("shared_pos") or []
        if len(shared) >= 2:
            (ax, ay), (bx, by) = shared[0], shared[1]
            ang = math.atan2(by - ay, bx - ax) + math.pi / 2
        else:
            ang = 0.0
        P = np.array([((k % cols) - (cols - 1) / 2, (k // cols) - (rows - 1) / 2) for k in range(m)], float) * sp
        P = _rot(P, -ang)
        for v, (x, y) in zip(nodes, P):
            out[v] = (cx + x, cy + y)
        return out
    raise AssertionError(kind)


# --------------------------------------------------------------------------
# the virtual graph: distances, stress, overlap removal
# --------------------------------------------------------------------------

def _distances(k, adj, lengths):
    """All-pairs shortest path lengths on the virtual graph (Dijkstra)."""
    D = np.full((k, k), np.inf)
    for s in range(k):
        dist = D[s]
        dist[s] = 0.0
        heap = [(0.0, s)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for v in adj[u]:
                nd = d + lengths[(u, v) if u < v else (v, u)]
                if nd < dist[v]:
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))
    return D


def _stress(D, X0, iters):
    """Stress majorization (SMACOF, weights 1/d^2) from X0."""
    k = len(D)
    if k == 1:
        return np.zeros((1, 2))
    X = X0.copy()
    with np.errstate(divide="ignore"):
        W = np.where(D > 0, 1.0 / (D * D), 0.0)
    np.fill_diagonal(W, 0.0)
    wsum = W.sum(1)
    wsum[wsum == 0] = 1.0
    prev = math.inf
    for _ in range(iters):
        diff = X[:, None, :] - X[None, :, :]
        dist = np.hypot(diff[..., 0], diff[..., 1])
        dist[dist < 1e-9] = 1e-9
        B = W * D / dist
        np.fill_diagonal(B, 0.0)
        # Jacobi step: each node moves to the weighted mean of where every
        # other node says it should be (at distance D from it)
        X = (W @ X + B.sum(1)[:, None] * X - B @ X) / wsum[:, None]
        s = float((W * (dist - D) ** 2).sum())
        if abs(prev - s) < 1e-6 * max(s, 1.0):
            break
        prev = s
    return X


def _classical(D):
    """Classical MDS start (2 dimensions)."""
    k = len(D)
    D2 = D * D
    J = np.eye(k) - 1.0 / k
    B = -0.5 * J @ D2 @ J
    w, V = np.linalg.eigh(B)
    idx = np.argsort(w)[::-1][:2]
    return V[:, idx] * np.sqrt(np.maximum(w[idx], 1e-9))


def _separate(X, r, pad, iters=120):
    """Push overlapping circles apart. Only circles that overlapped in the
    previous round are compared again (plus a full check every 10 rounds),
    so it stays fast when most of the drawing is already clear."""
    k = len(X)
    if k < 2:
        return X
    X = X.copy()
    rng = np.random.default_rng(0)
    I = J = None
    for it in range(iters):
        if I is None or it % 10 == 0:
            diff = X[:, None, :] - X[None, :, :]
            dist = np.hypot(diff[..., 0], diff[..., 1])
            need = r[:, None] + r[None, :] + pad
            I, J = np.nonzero(np.triu(dist < need, 1))
            if not len(I):
                break
        d = X[I] - X[J]
        dist = np.hypot(d[:, 0], d[:, 1])
        over = r[I] + r[J] + pad - dist
        hit = over > 1e-6
        if not hit.any():
            I = None
            continue
        I, J, d, dist, over = I[hit], J[hit], d[hit], dist[hit], over[hit]
        tie = dist < 1e-9
        if tie.any():
            d[tie] = rng.normal(0, 1, (int(tie.sum()), 2))
            dist[tie] = np.hypot(d[tie, 0], d[tie, 1])
        # each pair moves apart by its whole overlap, split by size (the
        # smaller circle moves more), a little more than needed to settle fast
        share = r[J] / np.maximum(r[I] + r[J], 1e-9)
        step = (over * 0.55 / dist)[:, None] * d
        np.add.at(X, I, step * (2 * share)[:, None])
        np.add.at(X, J, -step * (2 * (1 - share))[:, None])
    return X


def _min_area_rotation(P):
    """The rotation (radians) that gives points the smallest bounding box."""
    if len(P) < 3:
        return 0.0
    pts = sorted(set(map(tuple, np.round(P, 6))))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = np.array(lower[:-1] + upper[:-1])
    best, best_a = math.inf, 0.0
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        a = -math.atan2(e[1], e[0])
        R = _rot(hull, a)
        w, h = R.max(0) - R.min(0)
        area = w * h
        if area < best - 1e-9:
            best, best_a = area, a
    # prefer landscape
    R = _rot(np.asarray(P, float), best_a)
    w, h = R.max(0) - R.min(0)
    if h > w:
        best_a += math.pi / 2
    return best_a


# --------------------------------------------------------------------------
# the layout
# --------------------------------------------------------------------------

def compute(snap, opts):
    """Centres of every node, plus the groups found."""
    n = snap.n
    indptr, ind = snap.csr
    nb = [set(ind[indptr[i]:indptr[i + 1]].tolist()) for i in range(n)]
    size = snap.size.max(1)
    sp = opts["spacing"] or max(24.0, 2.4 * float(np.median(size)) if n else 24.0)
    groups, owner = detect(nb, opts)
    k = len(groups)
    radii = np.array([radius(g, size, sp, opts) for g in groups])
    gap = sp * opts["gap"]
    # virtual edges
    vadj = [set() for _ in range(k)]
    for i in range(n):
        for j in nb[i]:
            a, b = owner[i], owner[j]
            if a != b:
                vadj[a].add(b)
                vadj[b].add(a)
    lengths = {}
    for a in range(k):
        for b in vadj[a]:
            if a < b:
                lengths[(a, b)] = radii[a] + radii[b] + gap
    # virtual components
    vcomp = [-1] * k
    comps = []
    for s in range(k):
        if vcomp[s] >= 0:
            continue
        stack, members = [s], []
        vcomp[s] = len(comps)
        while stack:
            u = stack.pop()
            members.append(u)
            for v in vadj[u]:
                if vcomp[v] < 0:
                    vcomp[v] = len(comps)
                    stack.append(v)
        comps.append(sorted(members))
    rng = np.random.default_rng(opts["seed"])
    centres = np.zeros((k, 2))
    cur = snap.pos + snap.size / 2
    for members in comps:
        m = len(members)
        if m == 1:
            continue
        loc = {g: i for i, g in enumerate(members)}
        sub_adj = [[loc[v] for v in vadj[g]] for g in members]
        sub_len = {(loc[a], loc[b]) if loc[a] < loc[b] else (loc[b], loc[a]): L
                   for (a, b), L in lengths.items() if a in loc and b in loc}
        D = _distances(m, sub_adj, sub_len)
        if m <= opts["exactLimit"]:
            X0 = _classical(D) + rng.normal(0, 1e-3, (m, 2))
            X = _stress(D, X0, min(opts["iterations"], 150))
        else:
            from .layouts import _stress_fast_gen
            ei = np.array([i for i in range(m) for j in sub_adj[i]], np.intp)
            ej = np.array([j for i in range(m) for j in sub_adj[i]], np.intp)
            # a classical-MDS start from a few pivots, then sampled stress
            piv = rng.choice(m, size=min(m, 60), replace=False)
            Dp = D[:, piv]
            Dp = np.where(np.isfinite(Dp), Dp, np.nanmax(np.where(np.isfinite(Dp), Dp, np.nan)) * 1.2)
            C = Dp * Dp
            C = C - C.mean(0) - C.mean(1)[:, None] + C.mean()
            U, S, _ = np.linalg.svd(-0.5 * C, full_matrices=False)
            X = U[:, :2] * np.sqrt(np.maximum(S[:2], 1e-9)) + rng.normal(0, 1e-3, (m, 2))
            for X in _stress_fast_gen(X, D, ei, ej, np.zeros(m, bool), rng, iters=60):
                pass
        X = _separate(X, radii[members], gap * 0.25)
        centres[members] = X
    # expand
    C = np.zeros((n, 2))
    gpos = centres

    def target_for(gi):
        def target_of(v):
            pts = [gpos[owner[w]] for w in nb[v] if owner[w] != gi]
            if not pts:
                return None
            return tuple(np.mean(pts, 0))
        return target_of

    for gi, g in enumerate(groups):
        if g["kind"] == "parallel":
            g["shared_pos"] = [tuple(gpos[owner[w]]) for w in g["shared"]]
        for v, p in expand(g, gpos[gi], size, sp, opts, target_for(gi)).items():
            C[v] = p
    # each component: smallest bounding box, landscape; then pack
    for members in comps:
        nodes = [v for gi in members for v in groups[gi]["nodes"]]
        if len(nodes) < 3:
            continue
        a = _min_area_rotation(C[nodes])
        mid = C[nodes].mean(0)
        C[nodes] = _rot(C[nodes] - mid, a) + mid
    return C, groups, owner, sp


def install(session):
    lay = getattr(session, "_layouts", None) or _Layouts(session)

    def motifLayout(spacing=None, minStar=3, minCycle=3, maxCycle=40, minChain=2, minParallel=2,
                    leavesAround=True, gap=2.0, iterations=300, outline=False, seed=0):
        """motifLayout() is a structure-aware layout (a port of LUMINA, the
        IntAct team's layout for protein networks). It finds four shapes and
        gives each its own arrangement: cycles become circles, chains (paths
        ending in a leaf) hang off their anchor as small rings, a node with
        leaves becomes a star with the leaves in rings around it, and nodes
        sharing exactly the same neighbours (parallel) line up in a grid
        between them. Each shape is treated as one big node while the whole
        is laid out by stress majorization, so the drawing keeps graph
        distances; components are turned to fit and packed. Each node's shape
        is stored in the field `motif` ("star 3", "cycle 1", …), so
        colorize(motif) or groupBy(motif) work.

        spacing= the distance between neighbouring nodes in a shape (default:
        from node sizes); gap= the room between shapes, in spacings;
        minStar= the leaves a node needs to be a star (leavesAround=false
        leaves smaller groups of leaves to the layout); minCycle/maxCycle and
        minChain set the sizes of rings and chains; outline=true draws an
        ellipse or box around each shape (removeConvexHulls() clears them).
        Fixed nodes keep their positions."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        opts = dict(spacing=None if spacing is None else float(spacing), minStar=int(minStar),
                    minCycle=max(3, int(minCycle)), maxCycle=int(maxCycle), minChain=max(2, int(minChain)),
                    minParallel=max(1, int(minParallel)), leavesAround=bool(leavesAround), gap=float(gap),
                    iterations=max(10, int(iterations)), cycles=True, maxCycleDegree=8, starBase=6,
                    ringSpacing=1.0, exactLimit=600, seed=seed)
        if opts["spacing"] is not None and opts["spacing"] <= 0:
            raise GuessError("motifLayout spacing must be positive")
        C, groups, owner, sp = compute(s, opts)
        P = C - s.size / 2
        P[s.fixed] = s.pos[s.fixed]
        # pack components side by side (positions only; no rescaling)
        s2 = lay.snap()
        s2.pos = P
        P = _binpack_positions(s2, False)
        P[s.fixed] = s.pos[s.fixed]
        # label each node's shape
        g = session.graph
        if "motif" not in g.node_schema:
            g.addNodeField("motif", STRING, "")
        f = g.node_schema["motif"]
        counts = {}
        names = []
        for grp in groups:
            kind = grp["kind"]
            if kind == "single":
                names.append("")
                continue
            counts[kind] = counts.get(kind, 0) + 1
            names.append(f"{kind} {counts[kind]}")
        for gi, grp in enumerate(groups):
            for v in grp["nodes"]:
                f.set(s.nodes[v], names[gi])
        lay.apply(s, P)
        if outline:
            view = session.view
            from . import colors
            palette = colors.distinctColors(12)
            shapes = {"cycle": "ellipse", "chain": "ellipse", "star": "ellipse", "parallel": "box"}
            k = 0
            for gi, grp in enumerate(groups):
                if grp["kind"] == "single" or len(grp["nodes"]) < 2:
                    continue
                rgb = palette[k % len(palette)]
                k += 1
                session.ns["createConvexHull"]([s.nodes[v] for v in grp["nodes"]], f"{rgb},55",
                                               shape=shapes[grp["kind"]], rotate=True, padding=8)
            view.changed()
        summary = ", ".join(f"{v} {k}{'s' if v != 1 else ''}" for k, v in counts.items()) or "no shapes"
        print(f"motifLayout: {summary} (field motif)")

    session.register_command("motifLayout", motifLayout)


__all__ = ["install", "detect", "compute", "KINDS"]
