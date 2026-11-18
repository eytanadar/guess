"""ciseLayout: CiSE, a circular spring embedder for clustered graphs.

A numpy port of CiSE (Dogrusoz, Belviranli & Dilek, "CiSE: A Circular Spring
Embedder Layout Algorithm", IEEE TVCG 19(6), 2013) after the i-Vis Research
Group's (Bilkent University) cytoscape.js-cise (src/CiSE/*.js, src/layout/CiSE.js),
its AVSDF circular ordering (avsdf-base: He & Sykora's AVSDF) and the CoSE spring
embedder it extends (cose-base 2.2 / layout-base 2.0.1, fd/FDLayout.js).

Everything is in node-centre coordinates. A cluster is a rigid circle: a centre,
a radius and one angle per on-circle node; the spring embedder moves the
"bodies" (circles and unclustered nodes) and turns the circles.
"""
import math

import numpy as np

from .layouts import _accumulate, _fcose_gen, _rect_clip, _separation, _Snapshot
from .model import NODE, GSet, GuessError, Node, as_field

# CiSEConstants / FDLayoutConstants
_EDGE = 50.0                    # DEFAULT_EDGE_LENGTH
_INNER_EDGE = _EDGE / 3         # DEFAULT_INNER_EDGE_LENGTH
_MAX_ROT = math.pi / 36         # MAX_ROTATION_ANGLE
_SWAP_IDLE, _SWAP_PERIOD = 45, 50
_SWAP_CLEAR = 6 * _SWAP_PERIOD  # SWAP_HISTORY_CLEARANCE_PERIOD
_MIN_SWAP = 6.0                 # MIN_DISPLACEMENT_FOR_SWAP
_REVERSE_PERIOD = 25
_ENLARGE_PERIOD = 50            # CLUSTER_ENLARGEMENT_CHECK_PERIOD
_MAX_DISP = 300.0               # MAX_NODE_DISPLACEMENT
_MIN_REP = _EDGE / 10           # MIN_REPULSION_DIST
_CIRCLE_REP = 4500.0            # cluster nodes keep FDLayoutNode's default repulsion
_MARGIN = 15.0 + 15             # graph margin + the extra 15 convertToClusteredGraph adds
_TWO_PI = 2 * math.pi


# --------------------------------------------------------------------------
# Crossings and alignment
# --------------------------------------------------------------------------

def _chord_crossings(ps, pt, qs, qt, m):
    """Crossings of chords (ps, pt) x (qs, qt) by circle position (CiSEEdge /
    AVSDFEdge.crossesWithEdge: the circular distances from the first source)."""
    if not len(ps) or not len(qs):
        return 0
    dt = ((pt - ps) % m)[:, None]
    du = (qs[None, :] - ps[:, None]) % m
    dv = (qt[None, :] - ps[:, None]) % m
    lo, hi = np.minimum(du, dv), np.maximum(du, dv)
    return int(((dt > lo) & (dt < hi) & (du != 0) & (dv != 0)).sum())


def _node_crossings(v, ea, eb, pos, m):
    """calculateTotalCrossing: v's edges against the circle's edges not at v."""
    own = (ea == v) | (eb == v)
    if not own.any():
        return 0
    return _chord_crossings(pos[ea[own]], pos[eb[own]], pos[ea[~own]], pos[eb[~own]], m)


def _nw_score(a, b, match=20, mismatch=-1, gap=-2):
    """NeedlemanWunsch(a, b, 20, -1, -2).getScore(), a row at a time; the
    left (gap) recurrence is a running max."""
    b = np.asarray(b)
    ks = np.arange(len(b) + 1) * gap
    row = ks.astype(float)
    for i, x in enumerate(a, 1):
        new = np.empty_like(row)
        new[0] = i * gap
        new[1:] = np.maximum(row[:-1] + np.where(b == x, match, mismatch), row[1:] + gap)
        row = np.maximum.accumulate(new - ks) + ks
    return row[-1]


def _avsdf(m, ea, eb, diag, sep):
    """AVSDF on one cluster (local ids 0..m-1, intra edges ea-eb): AVSDFLayout.layout
    (DFS from the smallest-degree node, neighbours by degree), the He & Sykora
    post-processing (move a node next to a neighbour when that cuts its
    crossings), then correctAngles. Returns order, angle per node, radius."""
    deg = np.bincount(ea, minlength=m) + np.bincount(eb, minlength=m)
    nbrs = [[] for _ in range(m)]          # getNeighborsList, in edge order
    for a, b in zip(ea.tolist(), eb.tolist()):
        if b not in nbrs[a]:
            nbrs[a].append(b)
        if a not in nbrs[b]:
            nbrs[b].append(a)
    idx = np.full(m, -1, np.intp)
    order, stack = [], []
    while len(order) < m:
        s = None
        while stack:
            c = stack.pop()
            if idx[c] < 0:
                s = c
                break
        if s is None:                      # findUnorderedSmallestDegreeNode
            free = np.flatnonzero(idx < 0)
            s = int(free[np.argmin(deg[free])])
        cand = sorted((v for v in nbrs[s] if idx[v] < 0), key=lambda v: deg[v])
        stack.extend(reversed(cand))
        idx[s] = len(order)
        order.append(s)
    # post-processing (initPostProcess / oneStepPostProcess)
    crossing = [_node_crossings(v, ea, eb, idx, m) for v in range(m)]
    for v in sorted(range(m), key=lambda v: -crossing[v]):
        cur = _node_crossings(v, ea, eb, idx, m)
        for nb in nbrs[v]:
            old, new = int(idx[v]), (int(idx[nb]) + 1) % m
            if old == new:
                continue
            idx[v] = new
            if old < new:
                old += m
            for k in range(new, old):
                t = order[k % m]
                idx[t] = (idx[t] + 1) % m
            c = _node_crossings(v, ea, eb, idx, m)
            if c >= cur:
                idx[order] = np.arange(m)          # loadOldIndicesOfNodes
            else:
                order = list(np.argsort(idx))      # reOrderVertices
                cur = c
    perimeter = diag.sum() + m * sep
    ang = np.zeros(m)
    for k in range(1, m):                          # putInOrder via correctAngles
        a, b = order[k - 1], order[k]
        ang[b] = ang[a] + _TWO_PI * (diag[b] / 2 + sep + diag[a] / 2) / perimeter
    return [int(v) for v in order], ang, perimeter / _TWO_PI


def _segments_cross(p1, p2, p3, p4):
    """IGeometry.doIntersect for arrays of segments p1-p2 and p3-p4."""
    a, b = p1[:, 0], p1[:, 1]
    c, d = p2[:, 0], p2[:, 1]
    p, q = p3[:, 0], p3[:, 1]
    r, s = p4[:, 0], p4[:, 1]
    det = (c - a) * (s - q) - (r - p) * (d - b)
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = ((s - q) * (r - a) + (p - r) * (s - b)) / det
        gam = ((b - d) * (r - a) + (c - a) * (s - b)) / det
    return (det != 0) & (lam > 0) & (lam < 1) & (gam > 0) & (gam < 1)


def _repulse(C, H, rep, nch, pa, pb):
    """FDLayout.calcRepulsionForce for pairs pa-pb of rectangles (centres C,
    half sizes H): overlap separation (x childrenConstant) or inverse-square
    repulsion on the clipped distance, scaled by noOfChildren."""
    F = np.zeros_like(C)
    if not len(pa):
        return F
    d = C[pb] - C[pa]
    over = ((H[pa] + H[pb] - np.abs(d)) > 0).all(1)
    f = np.zeros_like(d)
    if over.any():
        a, b = pa[over], pb[over]
        cc = nch[a] * nch[b] / (nch[a] + nch[b])
        f[over] = (2 * cc)[:, None] * _separation(C[a], C[b], H[a], H[b], _EDGE / 2)
    ap = ~over
    if ap.any():
        a, b = pa[ap], pb[ap]
        dd = d[ap]
        ln = np.maximum(np.hypot(dd[:, 0], dd[:, 1]), 1e-9)
        u = dd / ln[:, None]
        cl = ln - _rect_clip(H[a], u) - _rect_clip(H[b], u)
        v = u * cl[:, None]
        v = np.where(np.abs(v) < _MIN_REP, np.where(v >= 0, 1.0, -1.0) * _MIN_REP, v)
        d2 = (v * v).sum(1)
        mag = (rep[a] / 2 + rep[b] / 2) * nch[a] * nch[b] / d2
        f[ap] = (mag / np.sqrt(d2))[:, None] * v
    return _accumulate(len(C), pb, pa, f)


# --------------------------------------------------------------------------
# The layout
# --------------------------------------------------------------------------

def _cise_gen(snap, cl, rng, o):
    n = snap.n
    H = snap.size / 2
    diag = np.hypot(snap.size[:, 0], snap.size[:, 1])
    hd = diag / 2
    K = int(cl.max()) + 1 if n else 0
    sep0 = o["sep"]
    src, dst = snap.src, snap.dst
    keep = src != dst
    src, dst = src[keep], dst[keep]
    intra = (cl[src] == cl[dst]) & (cl[src] >= 0)

    # ---- step 1: AVSDF per cluster -------------------------------------
    ring = []                       # circle -> on-circle nodes by position
    pos = np.full(n, -1, np.intp)   # position on the circle
    ang = np.zeros(n)
    R = np.zeros(K)
    addsep = np.zeros(K)            # additionalNodeSeparation
    cedges = []                     # intra edges per circle (global ids)
    for k in range(K):
        mem = np.flatnonzero(cl == k)
        loc = np.full(n, -1, np.intp)
        loc[mem] = np.arange(len(mem))
        ek = intra & (cl[src] == k)
        cedges.append((src[ek], dst[ek]))
        order, a, R[k] = _avsdf(len(mem), loc[src[ek]], loc[dst[ek]], diag[mem], sep0)
        ring.append([int(mem[v]) for v in order])
        for p, v in enumerate(order):
            pos[mem[v]] = p
        ang[mem] = a
    inner = np.zeros(n, bool)
    oncircle = cl >= 0

    def body_dim(k):                # calculateParentNodeDimension
        on = [v for v in ring[k]]
        return 2 * (R[k] + _MARGIN) + (snap.size[on].max() if on else 0.0)

    # ---- bodies: circles 0..K-1, then the unclustered nodes ---------------
    freeidx = np.flatnonzero(cl < 0)
    B = K + len(freeidx)
    bod = np.where(cl >= 0, cl, 0)
    bod[freeidx] = K + np.arange(len(freeidx))
    BH = np.zeros((B, 2))
    BH[:K] = np.array([body_dim(k) for k in range(K)])[:, None] / 2 if K else 0
    BH[K:] = H[freeidx]
    bfixed = np.zeros(B, bool)
    bfixed[K:] = snap.fixed[freeidx]
    rep = np.full(B, _CIRCLE_REP)
    rep[K:] = o["repulsion"]
    nch = np.ones(B)
    nch[:K] = np.bincount(cl[cl >= 0], minlength=K)

    # ---- step 2: CoSE on the cluster (quotient) graph ----------------------
    q = object.__new__(_Snapshot)
    q.n = B
    q.size = 2 * BH
    q.size[:K] *= 1.2               # bigger, so inter-cluster edges end up longer
    q.fixed = bfixed
    q.pos = np.zeros((B, 2))
    q.pos[K:] = snap.pos[freeidx]
    ia, ib = bod[src], bod[dst]
    k2 = ia != ib
    key = np.unique(np.minimum(ia[k2], ib[k2]) * B + np.maximum(ia[k2], ib[k2]))
    q.src, q.dst = key // B, key % B
    comps = [sorted(c) for c in q.components]
    P = q.pos
    for P in _fcose_gen(q, comps, rng, dict(
            quality="default", ideal=_EDGE, repulsion=o["repulsion"], elastic=o["spring"],
            gravity=o["gravity"], gravity_range=o["gravity_range"], sep=75.0, samples=25,
            iterations=2500, energy=0.3)):
        pass
    BC = P + q.size / 2
    connected = len(comps) <= 1

    X = np.zeros((n, 2))

    def place():
        on = oncircle & ~inner
        c = cl[on]
        X[on] = BC[c] + R[c][:, None] * np.stack([np.cos(ang[on]), np.sin(ang[on])], 1)
        X[freeidx] = BC[K:]

    def out():
        Pn = X - H
        Pn[snap.fixed] = snap.pos[snap.fixed]
        return Pn

    place()
    yield out()

    def bounds():
        return (BC - BH).min(0) - 15, (BC + BH).max(0) + 15
    lo, hi = bounds()
    est = (hi - lo).max() if B else 0.0     # root.estimatedSize after step 2

    # ---- steps 3-5: the CiSE spring embedder --------------------------------
    n_all = n + K
    max_it = max(5 * n_all, 2500)
    init_cool = 1.0 if n_all <= 1000 else max(0.33, 1 - (n_all - 1000) / 4000 * 0.67)
    thresh = 3.0 * _EDGE / 100 * n_all
    rrange = 2 * _EDGE * o["coeff"]
    ideal = np.full(len(src), _EDGE * o["coeff"])
    oc_order = np.flatnonzero(oncircle)     # graphManager.onCircleNodes
    inter_nb = [[] for _ in range(n)]
    for a, b, i in zip(src.tolist(), dst.tolist(), intra.tolist()):
        if not i:
            inter_nb[a].append(b)
            inter_nb[b].append(a)
    inter_nb = [np.array(v, np.intp) for v in inter_nb]
    may_reverse = np.ones(K, bool)
    for k in range(K):                      # prepareCirclesForReversal
        if sum(len(inter_nb[v]) for v in ring[k]) < 2:
            may_reverse[k] = False
    can_next = np.ones(n, bool)
    can_prev = np.ones(n, bool)
    dfs = np.zeros(n)                       # displacementForSwap
    history = set()
    push = np.zeros(K)                      # innerNodePushCount
    inner_pairs = (np.zeros(0, np.intp), np.zeros(0, np.intp))
    state = dict(old_total=0.0)

    def crossings(i):
        k = cl[i]
        return _node_crossings(i, *cedges[k], pos, len(ring[k]))

    def update_conditions(i):
        k = cl[i]
        rk = ring[k]
        m = len(rk)
        cur = crossings(i)
        for nb, store in ((rk[(pos[i] + 1) % m], can_next), (rk[(pos[i] - 1) % m], can_prev)):
            pos[i], pos[nb] = pos[nb], pos[i]
            store[i] = crossings(i) <= cur
            pos[i], pos[nb] = pos[nb], pos[i]

    def set_xy(v):
        k = cl[v]
        X[v] = BC[k] + R[k] * np.array([math.cos(ang[v]), math.sin(ang[v])])

    def swap_nodes(first, second):          # CiSECircle.swapNodes
        k = cl[first]
        rk = ring[k]
        m = len(rk)
        small, big = (first, second) if pos[first] < pos[second] else (second, first)
        if rk[(pos[small] - 1) % m] == big:
            small, big = big, small
        p = rk[(pos[small] - 1) % m]
        s = sep0 + addsep[k]
        ang[big] = (ang[p] + (hd[p] + hd[big] + s) / R[k]) % _TWO_PI
        ang[small] = (ang[big] + (hd[big] + hd[small] + s) / R[k]) % _TWO_PI
        set_xy(small)
        set_xy(big)
        pos[first], pos[second] = pos[second], pos[first]
        rk[pos[first]], rk[pos[second]] = first, second
        update_conditions(first)
        update_conditions(second)
        nxt = lambda v: rk[(pos[v] + 1) % m]
        prv = lambda v: rk[(pos[v] - 1) % m]
        if nxt(first) == second:
            update_conditions(prv(first))
            update_conditions(nxt(second))
        else:
            update_conditions(nxt(first))
            update_conditions(prv(second))

    def inter_crossings(a, b):              # getInterClusterIntersections
        oa, ob = inter_nb[a], inter_nb[b]
        if not len(oa) or not len(ob):
            return 0
        o1, o2 = np.repeat(oa, len(ob)), np.tile(ob, len(oa))
        ok = o1 != o2
        o1, o2 = o1[ok], o2[ok]
        t = len(o1)
        return int(_segments_cross(np.repeat(X[a][None], t, 0), X[o1],
                                   np.repeat(X[b][None], t, 0), X[o2]).sum())

    def recalc_angles(k, keep_first=False):
        """reCalculateNodeAnglesAndPositions (first node at angle 0) or
        reCalculateNodePositions (first node keeps its angle)."""
        rk = ring[k]
        s = sep0 + addsep[k]
        a = ang[rk[0]] if keep_first else 0.0
        for i, v in enumerate(rk):
            if i:
                a += (hd[v] + s + hd[rk[i - 1]]) / R[k]
            ang[v] = a % _TWO_PI

    def reverse_if_better(k):               # CiSECircle.checkAndReverseIfReverseIsBetter
        rk = ring[k]
        m = len(rk)
        ends, others = [], []
        for v in rk:
            for w in inter_nb[v].tolist():
                ends.append(v)
                others.append(w)
        d = X[others] - BC[k]
        angle = np.arctan2(d[:, 1], d[:, 0]) % _TWO_PI
        cnt = np.maximum(np.bincount(pos[ends], minlength=m), 1)
        seq = np.repeat(np.arange(m), cnt)
        cur = np.concatenate([seq, seq])
        # shortcut: equal angles are broken by circle position, not orderMatrix
        nb = pos[np.array(ends)][np.lexsort((pos[np.array(ends)], angle))]
        if _nw_score(cur[::-1], nb) > _nw_score(cur, nb):
            for v in rk:
                pos[v] = (m - pos[v]) % m
            ring[k] = sorted(rk, key=lambda v: pos[v])
            recalc_angles(k)
            may_reverse[k] = False
            return True
        return False

    def radius_from_ring(k, first=False, inside=()):   # reCalculateCircleSizeAndRadius
        rk = ring[k]
        s = sep0 + addsep[k]
        total = diag[rk].sum()
        perimeter = total + len(rk) * s
        if first and len(inside):
            dia = perimeter / math.pi - (diag[rk].max() + _INNER_EDGE)
            big = 1.2 * diag[inside].max() + _INNER_EDGE
            dia -= big
            need = big * math.ceil(math.sqrt(len(inside)))
            if dia < need + _INNER_EDGE:
                addsep[k] = (need - dia) / len(rk)
                perimeter = total + len(rk) * (sep0 + addsep[k])
        R[k] = perimeter / _TWO_PI
        BH[k] = body_dim(k) / 2

    def find_inner(k):                      # CiSELayout.findInnerNode
        rk = ring[k]
        m = len(rk)
        indptr, ind = snap.csr
        nbr_on = lambda v: [w for w in ind[indptr[v]:indptr[v + 1]].tolist()
                            if cl[w] == k and not inner[w]]
        degree = {v: len(inter_nb[v]) + int(((cedges[k][0] == v) | (cedges[k][1] == v)).sum()) for v in rk}
        for cand in sorted(rk, key=lambda v: degree[v], reverse=True):
            if len(inter_nb[cand]):
                continue
            nbs = sorted(nbr_on(cand), key=lambda v: pos[v])
            if not nbs:
                continue
            best, start, end = m, None, None   # findMinimalSpanningSegment
            for i in range(len(nbs)):
                s_, e_ = nbs[i], nbs[i - 1]
                ln = (pos[e_] - pos[s_] + m) % m + 1
                if ln < best:
                    best, start, end = ln, s_, e_
            if start is None:
                continue
            seg, cur = [], start
            while True:
                if cur != cand:
                    seg.append(cur)
                if cur == end:
                    break
                cur = rk[(pos[cur] + 1) % m]
            bad = False
            for sp in seg:
                for w in nbr_on(sp):
                    if w == cand:
                        continue
                    dd = (pos[sp] - pos[w]) % m
                    if dd > 1:
                        dd = (pos[w] - pos[sp]) % m
                    if dd > 1:
                        bad = True
                        break
                if bad:
                    break
            if not bad:
                return cand
        return None

    def move_inside():                      # findAndMoveInnerNodes
        nonlocal inner_pairs
        A, Bp = [], []
        for k in range(K):
            limit = math.floor(nch[k] * o["max_inner"])
            found = []
            while len(found) < limit and len(ring[k]) > 2:
                v = find_inner(k)
                if v is None:
                    break
                found.append(v)
                ring[k].remove(v)              # setOnCircleNodeInner
                inner[v] = True
                for p, w in enumerate(ring[k]):
                    pos[w] = p
                pos[v] = -1
            if found:
                radius_from_ring(k, True, np.array(found))
                recalc_angles(k)
                X[found] = BC[k] + (rng.random((len(found), 2)) - 0.5) / 10
                ii, jj = np.triu_indices(len(found), 1)
                A.append(np.array(found)[ii])
                Bp.append(np.array(found)[jj])
        if A:
            inner_pairs = (np.concatenate(A), np.concatenate(Bp))
        place()

    def run_step(step, cool):
        it = 0
        total = 1000.0
        pa = pb = np.zeros(0, np.intp)
        nonlocal history
        inner_n = np.flatnonzero(inner)
        has_inner = len(inner_n) > 0
        oc_now = oc_order[~inner[oc_order]]
        while True:
            it += 1
            if it % 100 == 0:
                if step != 4 or it > max_it / 4:
                    osc = it > max_it / 3 and abs(total - state["old_total"]) < 2
                    conv = total < thresh
                    state["old_total"] = total
                    if conv or osc:
                        return
                cool = init_cool * (max_it - it) / max_it
            total = 0.0
            phase = "other"
            if step == 3:
                if it % _REVERSE_PERIOD == 0:
                    for k in range(K):
                        if may_reverse[k] and len(ring[k]) <= 52 and reverse_if_better(k):
                            break
                    place()
            elif step == 4:
                if it % _SWAP_CLEAR == 0:
                    history = set()
                ip = it % _SWAP_PERIOD
                phase = "prep" if ip >= _SWAP_IDLE else "swap" if ip == 0 else "other"
            elif has_inner and it % _ENLARGE_PERIOD == 0:     # clusterEnlargementCheck
                cnt = np.bincount(cl[inner_n], minlength=K)
                for k in np.flatnonzero(cnt).tolist():
                    if push[k] / cnt[k] > 300 * len(ring[k]):
                        push[k] = 0
                        addsep[k] += 6
                        radius_from_ring(k)
                        recalc_angles(k, keep_first=True)
                place()
            # springs (intra-cluster edges between on-circle nodes have no effect)
            act = ~(intra & ~inner[src] & ~inner[dst])
            s, t = src[act], dst[act]
            Fn = np.zeros((n, 2))
            if len(s):
                d = X[t] - X[s]
                ln = np.hypot(d[:, 0], d[:, 1])
                ok = ln > 0
                u = np.zeros_like(d)
                u[ok] = d[ok] / ln[ok, None]
                length = ln - _rect_clip(H[s], u) - _rect_clip(H[t], u)
                live = ok & (length > 0)
                f = (o["spring"] * (length - ideal[act]))[:, None] * u
                f[~live] = 0
                Fn = _accumulate(n, s, t, f)
            # repulsion between bodies near each other (the FR grid, every 10 steps)
            if it % 10 == 1:
                ii, jj = np.triu_indices(B, 1)
                gap = np.abs(BC[ii] - BC[jj]) - (BH[ii] + BH[jj])
                near = (gap <= rrange).all(1)
                pa, pb = ii[near], jj[near]
            FB = _repulse(BC, BH, rep, nch, pa, pb)
            if step == 5 and len(inner_pairs[0]):
                Fn += _repulse(X, H, np.full(n, o["repulsion"]), np.ones(n), *inner_pairs)
            if not connected:
                lo, hi = bounds()
                dc = BC - (lo + hi) / 2
                far = ((np.abs(dc) + BH) > est * o["gravity_range"]).any(1)
                FB[far] -= o["gravity"] * dc[far]
            # calcTotalForces: free nodes are bodies; on-circle forces go to the circle
            FB[K:] += Fn[freeidx]
            DB = cool * FB
            on = oc_now
            Dn = cool * Fn[on]
            rad = X[on] - BC[cl[on]]
            rad /= np.maximum(np.hypot(rad[:, 0], rad[:, 1]), 1e-12)[:, None]
            rot_n = rad[:, 0] * Dn[:, 1] - rad[:, 1] * Dn[:, 0]     # decomposeForce
            DB[:K, 0] += np.bincount(cl[on], Dn[:, 0], minlength=K)
            DB[:K, 1] += np.bincount(cl[on], Dn[:, 1], minlength=K)
            rot = np.bincount(cl[on], rot_n, minlength=K)
            if phase == "prep":
                dfs[on] = rot_n
            if phase != "swap":
                # CiSENode.move: limited, cooled again, shared by the circle's nodes
                DB = np.clip(DB, -_MAX_DISP, _MAX_DISP) * cool
                DB[:K] /= nch[:K, None]
                DB[bfixed] = 0
                BC[:] += DB
                step_abs = np.abs(DB).sum(1)
                total += float((step_abs * np.concatenate([nch[:K] + 1, np.ones(B - K)])).sum())
                # rotate
                nz = rot != 0
                theta = np.clip(np.divide(rot / np.maximum(np.array([len(r) for r in ring]), 1), R,
                                          out=np.zeros(K), where=R > 0), -_MAX_ROT, _MAX_ROT)
                ang[on] = (ang[on] + np.where(nz, theta, 0)[cl[on]]) % _TWO_PI
                total += float(rot[nz].sum())
                if has_inner:
                    X[inner_n] += DB[cl[inner_n]]
                    total += move_inner(inner_n, cool * Fn[inner_n], cool)
                place()
            else:
                perform_swap(oc_now)
            if it >= max_it:
                return
            if it % 10 == 0:
                yield out()

    def move_inner(nodes, D, cool):
        tot = 0.0
        indptr, ind = snap.csr
        for v, dv in zip(nodes.tolist(), D):
            k = cl[v]
            nb = sum(1 for w in ind[indptr[v]:indptr[v + 1]].tolist() if cl[w] == k and not inner[w])
            if nb > 4:
                dv = dv * 4 / nb
            init = dv.copy()
            c = BC[k]
            dist = math.hypot(*(X[v] + dv - c)) + diag[v]
            if dist > R[k] - _INNER_EDGE / 5:
                push[k] += dist - R[k]
                hit = _circle_hit(X[v], X[v] + dv, c, R[k] - _INNER_EDGE / 5 - diag[v])
                if hit is not None and hit > 0:
                    dv = hit * dv - dv / max(math.hypot(*dv), 1e-12)
                else:
                    dv = np.zeros(2)
            X[v] += np.clip(dv, -_MAX_DISP, _MAX_DISP) * cool
            tot += float(np.abs(np.clip(init, -_MAX_DISP, _MAX_DISP)).sum())
        return tot

    def perform_swap(oc_now):
        nonlocal history
        safe, nonsafe = [], []
        for i in oc_now.tolist():
            rk = ring[cl[i]]
            j = rk[(pos[i] + 1) % len(rk)]
            if j == i or not (can_next[i] and can_prev[j]):
                continue
            d1, d2 = dfs[i], dfs[j]
            disc = d1 - d2
            if disc < 0:
                continue
            same = (d1 > 0 and d2 > 0) or (d1 < 0 and d2 < 0)
            (safe if d1 == 0 or d2 == 0 else nonsafe).append((i, j, disc, same))
        nonsafe.sort(key=lambda p: p[2])
        done_nodes, done_pairs = set(), []
        key = lambda p: (min(p[0], p[1]), max(p[0], p[1]))
        while nonsafe:
            p = nonsafe[-1]
            i, j, disc, same = p
            if key(p) in history:
                nonsafe.pop()
                done_pairs.append(p)
                continue
            before = inter_crossings(i, j)
            swap_nodes(i, j)
            after = inter_crossings(i, j)
            if after > before or (after == before and (same or disc < _MIN_SWAP)):
                swap_nodes(i, j)
                nonsafe.pop()
                continue
            done_nodes |= {i, j}
            done_pairs.append(p)
            break
        for p in safe:
            i, j, disc, same = p
            if same or disc < _MIN_SWAP or i in done_nodes or j in done_nodes:
                continue
            if key(p) not in history:
                swap_nodes(i, j)
                done_nodes |= {i, j}
            done_pairs.append(p)
        history = {key(p) for p in done_pairs}
        dfs[:] = 0

    # CiSE.js tick: step 5, step 3 (randomize), step 5, step 4, inner nodes + step 5
    yield from run_step(5, 0.5)
    yield from run_step(3, 0.4)
    yield from run_step(5, 0.5)
    for v in oc_order.tolist():
        update_conditions(v)
    yield from run_step(4, 0.4)
    if o["inside"]:
        move_inside()
        ideal[:] = 1.5 * _EDGE * o["coeff"]
        ideal[inner[src] | inner[dst]] = _INNER_EDGE
    yield from run_step(5, 0.5)
    yield out()


def _circle_hit(E, L, C, r):
    """IGeometry.findCircleLineIntersections: the first t in [0, 1] where the
    segment E-L meets the circle (C, r), else None."""
    d, f = L - E, E - C
    a, b, c = d @ d, 2 * (f @ d), f @ f - r * r
    disc = b * b - 4 * a * c
    if disc < 0 or a == 0:
        return None
    for t in ((-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a)):
        if 0 <= t <= 1:
            return t
    return None


def _cluster_ids(graph, snap, clusters):
    """Cluster index per node (-1: unclustered) from a node field / field name
    (one cluster per distinct non-None value) or a list of node groups."""
    cl = np.full(snap.n, -1, np.intp)
    if isinstance(clusters, (list, tuple, set, frozenset, GSet)):
        items = list(clusters)
        groups = [items] if items and all(isinstance(x, Node) for x in items) else items
        for k, grp in enumerate(groups):
            if isinstance(grp, Node):
                grp = [grp]
            try:
                members = list(grp)
            except TypeError:
                raise GuessError(f"ciseLayout: expected groups of nodes, got {grp!r}") from None
            for nd in members:
                i = snap.index.get(nd._id) if isinstance(nd, Node) else None
                if i is not None and cl[i] < 0:
                    cl[i] = k
        # renumber so that empty groups leave no gaps
        used = np.unique(cl[cl >= 0])
        remap = np.full(len(groups) + 1, -1, np.intp)
        remap[used] = np.arange(len(used))
        return np.where(cl >= 0, remap[cl], -1)
    f = as_field(graph, clusters, "ciseLayout", (NODE,))
    ids = {}
    for i, nd in enumerate(snap.nodes):
        v = f.get(nd)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        cl[i] = ids.setdefault(v, len(ids))
    return cl


def install(session):
    lay = session._layouts           # shared driver (centerAfterLayout applies)
    g = session.graph

    def ciseLayout(clusters, nodeSeparation=12.5, idealInterClusterEdgeLengthCoefficient=1.4,
                   allowNodesInsideCircle=False, maxRatioOfNodesInsideCircle=0.1, springCoeff=0.45,
                   nodeRepulsion=4500, gravity=0.25, gravityRange=3.8, seed=0):
        """ciseLayout(clusters) draws each cluster's nodes on a circle and lays
        the circles out with a spring embedder (CiSE, Dogrusoz, Belviranli &
        Dilek, IEEE TVCG 2013; ported from the i-Vis group's (Bilkent)
        cytoscape.js-cise). clusters is a node field or its name -- one
        circle per value, nodes with no value (None) are placed freely, e.g.
        ciseLayout(louvain_class) or ciseLayout("dept") -- or a list of node
        groups such as groupBy(dept).

        Steps: AVSDF orders each circle to cut crossings; a CoSE spring embedder
        places the circles (as big nodes) and the free nodes; then springs on
        inter-cluster edges move and turn the circles, circles are reversed
        when that aligns them better with their neighbours, and neighbouring
        nodes on a circle swap when that does not add crossings.

        nodeSeparation (12.5) is the gap between nodes on a circle;
        idealInterClusterEdgeLengthCoefficient (1.4) scales the 50 px ideal
        length of inter-cluster edges; allowNodesInsideCircle=true lets up to
        maxRatioOfNodesInsideCircle (0.1) of a circle's nodes that only link to
        their circle neighbours move inside it; springCoeff (0.45),
        nodeRepulsion (4500), gravity (0.25) and gravityRange (3.8) tune the
        spring embedder; seed= the random start of the circle placement.

        Pinned (fixed) nodes stay put: CiSE itself has no pinning, so a pinned
        node is taken out of its cluster and treated as an immovable free node."""
        s = lay.snap()
        if s.n == 0:
            return
        cl = _cluster_ids(g, s, clusters)
        cl[s.fixed] = -1
        if (cl >= 0).any():                 # compact ids after removing pinned nodes
            _, cl[cl >= 0] = np.unique(cl[cl >= 0], return_inverse=True)
        opts = dict(sep=float(nodeSeparation), coeff=float(idealInterClusterEdgeLengthCoefficient),
                    inside=bool(allowNodesInsideCircle), max_inner=float(maxRatioOfNodesInsideCircle),
                    spring=float(springCoeff), repulsion=float(nodeRepulsion), gravity=float(gravity),
                    gravity_range=float(gravityRange))
        lay.run(s, _cise_gen(s, cl, np.random.default_rng(0 if seed is None else seed), opts))

    session.register_command("ciseLayout", ciseLayout)
