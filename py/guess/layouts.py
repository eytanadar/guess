"""Graph layouts: ports of GUESS's com/hp/hpl/guess/layout package and of the
JUNG layouts GUESS exposed (FR, KK, Spring, ISOM, DAG, Circle).

Every layout works on a numpy snapshot of the graph (``_Snapshot``) and
writes the result back through ordinary attribute assignment (``node.x = ...``)
so change tracking and patches work as usual.  Node ``x``/``y`` are used as
the algorithms' coordinates exactly as the original did.  Nodes whose
``fixed`` field is true are never written; incremental force layouts also pin
them in the simulation so they keep exerting forces from where they are.

Iterative layouts are generators that yield a fresh position array per
iteration; ``_Layouts.run`` drives them, calls ``session.tick()`` every
iteration, publishes positions about 30 times a second and, on
KeyboardInterrupt (the Stop button), writes the last finite positions before
re-raising.
"""
import heapq
import math
import time
from collections import deque
from functools import cached_property

import numpy as np

from .model import DOUBLE, INT, NODE, Edge, Field, GuessError, Node, elements_of

BOX = 1000.0          # GUESS initialised every layout with Dimension(1000, 1000)
_EXACT_N = 1200       # above this, pairwise repulsion uses the grid approximation
_BLOCK = 2_000_000    # max elements in one temporary pairwise block
_KK_FAST = 1000       # Kamada-Kawai on larger components uses sampled stress majorization


# --------------------------------------------------------------------------
# Graph snapshot
# --------------------------------------------------------------------------

def _num(v, default):
    if v is None or isinstance(v, bool):
        return float(default) if v is None else float(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(default)
    return f if math.isfinite(f) else float(default)


class _Snapshot:
    """Positions, sizes, fixed flags and edge arrays of the current graph."""

    def __init__(self, graph):
        self.graph = graph
        nodes = graph._nodes_list()
        self.nodes = nodes
        n = self.n = len(nodes)
        self.index = {nd._id: i for i, nd in enumerate(nodes)}
        sch = graph.node_schema
        dx, dy, dw, dh = (sch[k].default for k in ("x", "y", "width", "height"))
        pos = np.empty((n, 2))
        size = np.empty((n, 2))
        fixed = np.zeros(n, bool)
        for i, nd in enumerate(nodes):
            v = nd._vals
            pos[i, 0] = _num(v.get("x"), dx)
            pos[i, 1] = _num(v.get("y"), dy)
            size[i, 0] = _num(v.get("width"), dw)
            size[i, 1] = _num(v.get("height"), dh)
            fixed[i] = bool(v.get("fixed", False))
        self.pos = pos
        self.size = size
        self.fixed = fixed
        self.written = pos.copy()
        edges = graph._edges_list()
        self.edges = edges
        m = len(edges)
        idx = self.index
        self.src = np.fromiter((idx[e._n1._id] for e in edges), np.intp, m)
        self.dst = np.fromiter((idx[e._n2._id] for e in edges), np.intp, m)
        self.directed = np.fromiter((e._directed for e in edges), bool, m)
        wdef = graph.edge_schema["weight"].default
        self.weight = np.fromiter((_num(e._vals.get("weight"), wdef) for e in edges), float, m)

    # -- structure -----------------------------------------------------------
    @cached_property
    def pairs(self):
        """Unique undirected neighbour pairs (i < j), self-loops dropped."""
        a, b = self.src, self.dst
        keep = a != b
        lo = np.minimum(a[keep], b[keep])
        hi = np.maximum(a[keep], b[keep])
        if not len(lo):
            return np.zeros((0, 2), np.intp)
        key = np.unique(lo * self.n + hi)
        return np.stack([key // self.n, key % self.n], 1)

    @cached_property
    def csr(self):
        """Undirected neighbour sets as (indptr, indices)."""
        p = self.pairs
        a = np.concatenate([p[:, 0], p[:, 1]])
        b = np.concatenate([p[:, 1], p[:, 0]])
        order = np.lexsort((b, a))
        a, b = a[order], b[order]
        indptr = np.zeros(self.n + 1, np.intp)
        np.cumsum(np.bincount(a, minlength=self.n), out=indptr[1:])
        return indptr, b

    def neighbors(self, i):
        indptr, ind = self.csr
        return ind[indptr[i]:indptr[i + 1]]

    @cached_property
    def degree(self):
        return np.diff(self.csr[0])

    @cached_property
    def components(self):
        """Weakly connected components as lists of indices, largest first."""
        indptr, ind = self.csr
        comp = np.full(self.n, -1, np.intp)
        out = []
        for s in range(self.n):
            if comp[s] >= 0:
                continue
            c = len(out)
            comp[s] = c
            members = [s]
            frontier = np.array([s])
            while len(frontier):
                nb = _expand(indptr, ind, frontier)[1]
                nb = np.unique(nb[comp[nb] < 0])
                comp[nb] = c
                members.extend(nb.tolist())
                frontier = nb
            out.append(members)
        out.sort(key=len, reverse=True)
        return out

    # -- output --------------------------------------------------------------
    def write(self, pos):
        """Assign x/y of every non-fixed node whose position changed."""
        pos = np.asarray(pos, float)
        ok = np.isfinite(pos).all(1) & ~self.fixed
        changed = ok & (pos != self.written).any(1)
        nodes = self.nodes
        for i in np.flatnonzero(changed).tolist():
            nd = nodes[i]
            nd.x = float(pos[i, 0])
            nd.y = float(pos[i, 1])
        self.written[changed] = pos[changed]


def _expand(indptr, ind, frontier):
    """CSR neighbours of every node in ``frontier``: (position in frontier, neighbour)."""
    cnt = indptr[frontier + 1] - indptr[frontier]
    tot = int(cnt.sum())
    if tot == 0:
        return np.zeros(0, np.intp), np.zeros(0, np.intp)
    rep = np.repeat(np.arange(len(frontier)), cnt)
    offs = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    return rep, ind[indptr[frontier][rep] + offs]


def _bfs_hops(indptr, ind, n, sources, maxdepth=None):
    """Hop distances (int16, -1 = unreachable) from each source to all nodes."""
    sources = np.asarray(sources, np.intp)
    out = np.full((len(sources), n), -1, np.int16)
    batch = max(1, min(len(sources), 4_000_000 // max(n, 1)))
    for b0 in range(0, len(sources), batch):
        src = sources[b0:b0 + batch]
        D = out[b0:b0 + batch]
        rows = np.arange(len(src))
        D[rows, src] = 0
        flatD = D.reshape(-1)
        stamp = np.empty(D.size, np.intp)   # dedupes (row, node) pairs without sorting
        fr_r, fr_v = rows, src
        d = 0
        while len(fr_v):
            d += 1
            if maxdepth is not None and d > maxdepth:
                break
            rep, nb = _expand(indptr, ind, fr_v)
            flat = fr_r[rep] * n + nb
            flat = flat[flatD[flat] < 0]
            if not len(flat):
                break
            k = np.arange(len(flat))
            stamp[flat] = k
            flat = flat[stamp[flat] == k]
            flatD[flat] = d
            fr_r, fr_v = flat // n, flat % n
    return out


def _dijkstra_all(snap, nodes_idx):
    """Weighted shortest-path lengths (edge weight = length) between nodes_idx."""
    n = snap.n
    adj = [dict() for _ in range(n)]
    for a, b, w in zip(snap.src.tolist(), snap.dst.tolist(), snap.weight.tolist()):
        if a == b:
            continue
        w = max(abs(w), 1e-9)
        if w < adj[a].get(b, math.inf):
            adj[a][b] = w
            adj[b][a] = w
    pos = {v: k for k, v in enumerate(nodes_idx)}
    k = len(nodes_idx)
    D = np.full((k, k), np.inf)
    for si, s in enumerate(nodes_idx):
        dist = {s: 0.0}
        heap = [(0.0, s)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            j = pos.get(u)
            if j is not None:
                D[si, j] = d
            for v, w in adj[u].items():
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))
    return D


# --------------------------------------------------------------------------
# Pairwise repulsion: F_i = sum_j (p_i - p_j) / |p_i - p_j|**power
# --------------------------------------------------------------------------

def _kernel(d2, power, cut2=None):
    w = np.zeros_like(d2)
    m = d2 > 0
    if cut2 is not None:
        m &= d2 < cut2
    if power == 2:
        np.divide(1.0, d2, out=w, where=m)
    elif power == 4:
        np.divide(1.0, d2 * d2, out=w, where=m)
    else:
        w[m] = d2[m] ** (-power / 2.0)
    return w


def _rep_block(Pi, Pj, power, cut2, mass=None):
    dx = Pi[:, 0, None] - Pj[None, :, 0]
    dy = Pi[:, 1, None] - Pj[None, :, 1]
    d2 = dx * dx
    d2 += dy * dy
    w = _kernel(d2, power, cut2)
    if mass is not None:
        w *= mass[None, :]
    return np.stack([(dx * w).sum(1), (dy * w).sum(1)], 1)


def _rep_dense(Pi, Pj, power, cut2=None, mass=None):
    out = np.zeros((len(Pi), 2))
    if not len(Pj):
        return out
    step = max(1, _BLOCK // len(Pj))
    for s in range(0, len(Pi), step):
        out[s:s + step] = _rep_block(Pi[s:s + step], Pj, power, cut2, mass)
    return out


def _grid_keys(P, lo, h):
    cx = np.floor((P[:, 0] - lo[0]) / h).astype(np.intp)
    cy = np.floor((P[:, 1] - lo[1]) / h).astype(np.intp) + 1
    M = int(cy.max()) + 2
    return cx * M + cy, M


def _choose_grid(P, lo, span, cutoff):
    """Pick the cell size minimising near-field pairs + far-field node x cell work."""
    n = len(P)
    cands = []
    if cutoff is not None:
        cands.append((float(cutoff), False))
    h = span / 2.0
    while h > span / 8192:
        if cutoff is None or h <= cutoff / 4:   # coarse cells blur the cutoff
            cands.append((h, True))
        h /= 2
    best = None
    for h, far in cands:
        key, M = _grid_keys(P, lo, h)
        uk, cnt = np.unique(key, return_counts=True)
        pairs = 0
        for ox in (-1, 0, 1):
            nk = uk + ox * M
            for oy in (-1, 0, 1):
                k2 = nk + oy
                loc = np.minimum(np.searchsorted(uk, k2), len(uk) - 1)
                hit = uk[loc] == k2
                pairs += int((cnt[hit] * cnt[loc[hit]]).sum())
        cost = 2 * pairs + (n * len(uk) if far else 0)
        if best is None or cost < best[0]:
            best = (cost, h, far, key, M)
    return best[1:]


def _repulsion(P, power=2, cutoff=None, coincident=False, mass=None):
    """Sum over other nodes of (p_i - p_j)/d**power, ignoring pairs with d >= cutoff
    (each term weighted by mass[j] when masses are given).

    Exact for small graphs; for large graphs uses a uniform grid: exact for
    nodes in the 3x3 neighbouring cells, cell-centroid monopoles beyond (when
    there is no cutoff or the cutoff spans more than one cell).  With
    ``coincident=True`` also returns a mask of nodes sharing a position.
    """
    n = len(P)
    cut2 = None if cutoff is None else float(cutoff) ** 2
    F = np.zeros((n, 2))
    if n < 2:
        return (F, np.zeros(n, bool)) if coincident else F
    co = None
    if coincident:
        key = np.unique(P, axis=0, return_inverse=True, return_counts=True)
        co = key[2][key[1].ravel()] > 1
    if n <= _EXACT_N:
        F = _rep_dense(P, P, power, cut2, mass)
        return (F, co) if coincident else F
    lo = P.min(0)
    ext = P.max(0) - lo
    span = float(ext.max())
    if span == 0:
        return (F, co) if coincident else F
    _h, far, key, M = _choose_grid(P, lo, span, cutoff)
    order = np.argsort(key, kind="stable")
    ukeys, ustart, ucount = np.unique(key[order], return_index=True, return_counts=True)
    allidx = np.arange(n)
    X, Y = P[:, 0].copy(), P[:, 1].copy()
    Fx = np.zeros(n)
    Fy = np.zeros(n)
    if far:
        cell_of = np.searchsorted(ukeys, key)
        mw = np.ones(n) if mass is None else mass
        cmass = np.bincount(cell_of, mw, len(ukeys))
        cent = np.stack([np.bincount(cell_of, X * mw, len(ukeys)),
                         np.bincount(cell_of, Y * mw, len(ukeys))], 1) / cmass[:, None]
        F = _rep_dense(P, cent, power, cut2, cmass)
        Fx += F[:, 0]
        Fy += F[:, 1]
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            nk = key + ox * M + oy
            loc = np.minimum(np.searchsorted(ukeys, nk), len(ukeys) - 1)
            hit = ukeys[loc] == nk
            if not hit.any():
                continue
            if far:  # remove the monopole approximation of this near cell
                ii = allidx[hit]
                c = loc[hit]
                dx = X[ii] - cent[c, 0]
                dy = Y[ii] - cent[c, 1]
                w = _kernel(dx * dx + dy * dy, power, cut2) * cmass[c]
                Fx[ii] -= dx * w
                Fy[ii] -= dy * w
            # exact pairs, each unordered pair once: own cell (i < j) + 4 forward cells
            if (ox, oy) not in ((0, 0), (1, -1), (1, 0), (1, 1), (0, 1)):
                continue
            cnt = np.where(hit, ucount[loc], 0)
            st = np.where(hit, ustart[loc], 0)
            cum = np.cumsum(cnt)
            a = 0
            while a < n:
                base = cum[a - 1] if a else 0
                b = int(np.searchsorted(cum, base + _BLOCK, side="right"))
                b = min(max(b, a + 1), n)
                cc = cnt[a:b]
                tot = int(cc.sum())
                if tot:
                    ii = np.repeat(allidx[a:b], cc)
                    first = np.repeat(st[a:b] - (np.cumsum(cc) - cc), cc)
                    jj = order[first + np.arange(tot)]
                    if ox == 0 and oy == 0:
                        keep = ii < jj
                        ii, jj = ii[keep], jj[keep]
                    dx = X[ii] - X[jj]
                    dy = Y[ii] - Y[jj]
                    w = _kernel(dx * dx + dy * dy, power, cut2)
                    dx *= w
                    dy *= w
                    if mass is None:
                        Fx += np.bincount(ii, dx, n) - np.bincount(jj, dx, n)
                        Fy += np.bincount(ii, dy, n) - np.bincount(jj, dy, n)
                    else:
                        mi, mj = mass[ii], mass[jj]
                        Fx += np.bincount(ii, dx * mj, n) - np.bincount(jj, dx * mi, n)
                        Fy += np.bincount(ii, dy * mj, n) - np.bincount(jj, dy * mi, n)
                a = b
    F = np.stack([Fx, Fy], 1)
    return (F, co) if coincident else F


def _mean_move(step, mov):
    """Mean absolute per-axis step of the movable nodes."""
    s = step[mov]
    return float(np.abs(s).mean()) if s.size else 0.0


def _accumulate(n, a, b, f):
    """Add f to rows a and subtract it from rows b (edge forces)."""
    out = np.empty((n, 2))
    out[:, 0] = np.bincount(a, f[:, 0], minlength=n) - np.bincount(b, f[:, 0], minlength=n)
    out[:, 1] = np.bincount(a, f[:, 1], minlength=n) - np.bincount(b, f[:, 1], minlength=n)
    return out


def _jitter_coincident(P, rng, scale=1.0, movable=None):
    """Nudge nodes that share a position so force layouts can separate them."""
    if len(P) < 2:
        return P
    _, inv, cnt = np.unique(P, axis=0, return_inverse=True, return_counts=True)
    dup = cnt[inv.ravel()] > 1
    if movable is not None:
        dup &= movable
    if dup.any():
        P = P.copy()
        P[dup] += (rng.random((int(dup.sum()), 2)) - 0.5) * scale
    return P


def _bbox_rescale(P, width, height):
    """Map the bounding box of P onto [0,width] x [0,height] (GUESS Rescale)."""
    if len(P) < 2:
        return P.copy()
    lo, hi = P.min(0), P.max(0)
    ext = hi - lo
    out = np.zeros_like(P)
    for k, size in ((0, width), (1, height)):
        if ext[k] > 0:
            out[:, k] = (P[:, k] - lo[k]) / ext[k] * size
    return out


# --------------------------------------------------------------------------
# Iteration driver
# --------------------------------------------------------------------------

class _Layouts:
    def __init__(self, session):
        self.session = session
        self.graph = session.graph
        self.center_after = True

    def snap(self):
        # a new layout invalidates edge routes computed by an earlier one,
        # and the drag constraints (ring, scatter axes) of the previous layout
        self.graph.clear_bends()
        drag = getattr(self.session.view, "drag", None)
        if drag and (drag.pop("ring", None) is not None) | (drag.pop("axes", None) is not None):
            self.session.view.changed()
        if getattr(self.session.view, "guides", None):
            self.session.view.guides = []      # hive plot axes belong to that layout
            self.session.view.changed()
        return _Snapshot(self.graph)

    def finish(self):
        s = self.session
        s.flush()
        if self.center_after:
            s.emit({"type": "center", "nodes": [], "edges": []})

    def apply(self, snap, pos):
        snap.write(pos)
        self.finish()

    def run(self, snap, gen):
        """Drive a layout generator; see module docstring."""
        s = self.session
        best = snap.pos
        interval = 1 / 30
        last_write = -1e9
        cost = 0.0
        try:
            for P in gen:
                if np.isfinite(P).all():
                    best = np.array(P, float, copy=True)
                now = time.monotonic()
                # publish when the session is due to flush, but never spend more
                # than ~20% of the time writing positions and building patches
                if (now - last_write >= max(interval, 4 * cost)
                        and s.tick_due()):
                    snap.write(best)
                    s.tick()
                    cost = time.monotonic() - now
                    last_write = now
                else:
                    s.tick()
        finally:
            snap.write(best)
        self.finish()


def _iters(max_iter, default):
    if max_iter is None:
        return default
    try:
        k = int(max_iter)
    except (TypeError, ValueError):
        raise GuessError(f"iteration count must be a number, got {max_iter!r}") from None
    if k < 0:
        raise GuessError("iteration count must be >= 0")
    return k


def _scaled(base, n):
    """Default iteration count for layouts that originally ran until stopped:
    ``base`` up to 1000 nodes, then fewer so big graphs finish in seconds."""
    return base if n <= 1000 else max(base // 10, int(base * 1000 / n))


def _node_arg(graph, x, what="node"):
    if isinstance(x, Node):
        return graph._resolve(x)
    if isinstance(x, str):
        n = graph.getNodeByName(x)
        if n is not None:
            return n
    raise GuessError(f"expected a {what}, got {x!r}")


def _field_arg(graph, f):
    if isinstance(f, Field):
        return f
    if isinstance(f, str):
        got = graph.node_schema.get(f) or graph.edge_schema.get(f)
        if got is not None:
            return got
    raise GuessError(f"expected a field (e.g. freq, dept), got {f!r}")


# --------------------------------------------------------------------------
# Simple layouts
# --------------------------------------------------------------------------

def _is_int(field):
    return field.type == INT


def _random_positions(snap, width, height, rng):
    P = snap.pos.copy()
    n = snap.n
    P[:, 0] = rng.integers(0, max(1, int(width) - 4), n)   # RandomGraphLayout pad = 4
    P[:, 1] = rng.integers(0, max(1, int(height)), n)
    return P


def _circle_positions(snap):
    """JUNG CircleLayout in the 1000x1000 layout area: radius 0.45 * 1000."""
    n = snap.n
    P = snap.pos.copy()
    if n:
        r = 0.45 * BOX
        a = 2 * math.pi * np.arange(n) / n
        P[:, 0] = np.cos(a) * r + BOX / 2
        P[:, 1] = np.sin(a) * r + BOX / 2
    return P


def _circular_constrained(snap, graph, center, field, ox, oy):
    """Port of CircularConstrained: center's neighbours on a circle, radius by field."""
    maxradius, minradius, maxangle = 500.0, 30.0, 2 * math.pi
    P = snap.pos.copy()
    ci = snap.index[center._id]
    P[ci] = (ox, oy)
    numeric = field.type in (INT, DOUBLE)
    items = []  # (value, node index)
    if field.kind == NODE:
        for nb in center.getNeighbors():
            if nb is center:
                continue
            v = _num(field.get(nb), 0.0) if numeric else 1.0
            items.append((v, snap.index[nb._id]))
    else:
        for e in center.getIncidentEdges():
            if e._n1 is e._n2:
                continue
            v = _num(field.get(e), 0.0) if numeric else 1.0
            other = e._n2 if e._n1 is center else e._n1
            items.append((v, snap.index[other._id]))
    if not items:
        print("No neighbors")
        return P
    vals = np.array([v for v, _ in items])
    lo, hi = float(vals.min()), float(vals.max())
    items.sort(key=lambda t: t[0])
    step = maxangle / len(items)
    for k, (v, i) in enumerate(items):
        if not numeric or hi == lo:
            radius = (maxradius - minradius) / 2
        elif lo >= 0 and hi > 0:
            radius = minradius + (maxradius - minradius) * v / hi
        else:
            radius = minradius + (maxradius - minradius) * (v - lo) / (hi - lo)
        a = k * step
        P[i] = (ox + radius * math.cos(a), oy + radius * math.sin(a))
    return P


def _radial_positions(snap, graph, center, valid_edges=None):
    """Port of Radial (Eades, "Drawing Free Trees"): BFS tree around center."""
    P = snap.pos.copy()
    sizes = snap.size
    layer = max(10.0, float(sizes[:, 0].max(initial=0)) * 5, float(sizes[:, 1].max(initial=0)) * 5)
    idx = snap.index
    root = center
    children = {root._id: []}
    seen = {root._id}
    frontier = [root]
    while frontier:
        nxt = []
        for v in frontier:
            kids = children.setdefault(v._id, [])
            for e in v._inc.values():
                if e._directed and e._n1 is not v:
                    continue  # getOutEdges
                if valid_edges is not None and e._id not in valid_edges:
                    continue
                o = e.opposite(v)
                if o is v or o._id in seen:
                    continue
                seen.add(o._id)
                kids.append(o)
                children[o._id] = []
                nxt.append(o)
        frontier = nxt
    # subtree widths (leaves = 1), post-order without recursion
    width = {}
    order = []
    stack = [root]
    while stack:
        v = stack.pop()
        order.append(v)
        stack.extend(children[v._id])
    for v in reversed(order):
        kids = children[v._id]
        width[v._id] = sum(width[k._id] for k in kids) if kids else 1
    P[idx[root._id]] = (0.0, 0.0)
    total = width[root._id]
    work = []
    a1 = 0.0
    for k in children[root._id]:
        a2 = a1 + 2 * math.pi * width[k._id] / total
        work.append((k, layer, a1, a2))
        a1 = a2
    while work:
        v, rho, a1, a2 = work.pop()
        mid = (a1 + a2) / 2
        P[idx[v._id]] = (rho * math.cos(mid), rho * math.sin(mid))
        w = width[v._id]
        tau = 2 * math.acos(rho / (rho + layer))
        if tau < a2 - a1:
            alpha = (a1 + a2 - tau) / 2.0
            s = tau / w
        else:
            alpha = a1
            s = (a2 - a1) / w
        for k in children[v._id]:
            nxt = alpha + s * width[k._id]
            work.append((k, rho + layer, alpha, nxt))
            alpha = nxt
    return P


# --------------------------------------------------------------------------
# Force-directed layouts (GUESS)
# --------------------------------------------------------------------------

def _spring_gen(snap, iters, rng, lengths=None, tol=0.05):
    """Spring.java / WeightedSpring.java (springs of natural length 30 or by weight)."""
    P = _jitter_coincident(snap.pos, rng, 1.0, ~snap.fixed)
    n = snap.n
    mov = ~snap.fixed
    keep = snap.src != snap.dst
    a, b = snap.src[keep], snap.dst[keep]
    L = 30.0 if lengths is None else lengths[keep]
    W = H = 10000.0
    disp = np.zeros((n, 2))
    calm = 0
    for _ in range(iters):
        v = P[b] - P[a]
        ln = np.hypot(v[:, 0], v[:, 1])
        f = ((ln - L) / 150.0)[:, None] * v
        disp += _accumulate(n, a, b, f)
        R, co = _repulsion(P, 2, cutoff=100.0, coincident=True)
        R *= 2.0
        if co.any():
            R[co] += rng.random((int(co.sum()), 2))
        x, y = P[:, 0], P[:, 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            R[:, 1] += np.where(y > 0, 2.0 / np.where(y > 0, y, 1), 2.0)
            R[:, 1] -= np.where(y < H, 2.0 / np.where(y < H, H - y, 1), 2.0)
            R[:, 0] += np.where(x > 0, 2.0 / np.where(x > 0, x, 1), 2.0)
            R[:, 0] -= np.where(x < W, 2.0 / np.where(x < W, W - x, 1), 2.0)
        rl = np.hypot(R[:, 0], R[:, 1])
        ok = rl > 0
        R[ok] *= (10.0 / rl[ok])[:, None]
        disp += R
        step = np.clip(disp, -5.0, 5.0)
        step[~mov] = 0
        P = P + step
        disp *= 0.5
        yield P
        # the original ran until stopped; we stop once the average move is tiny
        calm = calm + 1 if _mean_move(step, mov) < tol else 0
        if calm >= 20:
            break


def _physics_gen(snap, iters, rng):
    """Physics.java, a port of graphopt: Coulomb repulsion + zero-length springs."""
    mass, charge, k_spring, max_move = 30.0, 0.001, 1.0, 5.0
    coulomb = 8987500000.0 * charge * charge
    n = snap.n
    mov = ~snap.fixed
    P = snap.pos.copy()
    # seperateNodes: shift coincident nodes by random integers until distinct
    for _ in range(100):
        _, inv, cnt = np.unique(P, axis=0, return_inverse=True, return_counts=True)
        inv = inv.ravel()
        dup = cnt[inv] > 1
        if not dup.any():
            break
        first = np.zeros(len(cnt), bool)
        keepers = np.zeros(n, bool)
        for i in np.flatnonzero(dup):   # leave one node of each group in place
            if not first[inv[i]]:
                first[inv[i]] = True
                keepers[i] = True
        moving = dup & ~keepers & mov
        if not moving.any():
            break
        P[moving] += rng.integers(0, 20, (int(moving.sum()), 2))
    pr = snap.pairs
    a, b = pr[:, 0], pr[:, 1]
    for _ in range(iters):
        F = coulomb * _repulsion(P, 3, cutoff=500.0)
        F += _accumulate(n, a, b, 0.5 * k_spring * (P[b] - P[a]))
        step = np.clip(F / mass, -max_move, max_move)
        step[~mov] = 0
        P = P + step
        yield P


def _fr_gen(snap, width, height, rng):
    """FruchGraphLayout.java (Fruchterman-Reingold as in Pajek/RePast), grid-snapped."""
    n = snap.n
    width, height = float(width), float(height)
    pad = 20
    mov = ~snap.fixed
    P = _jitter_coincident(snap.pos, rng, 1.0, mov)
    if n == 0:
        return
    opt = 0.46 * math.sqrt(width * height / (n + 1))
    k4 = opt ** 4
    temp = width / 10
    maxw = max(10.0, float(snap.size[:, 0].max()) * 1.5)
    maxh = max(10.0, float(snap.size[:, 1].max()) * 1.5)
    gx, gy = float(np.rint(maxw)), float(np.rint(maxh))
    keep = snap.src != snap.dst
    a, b = snap.src[keep], snap.dst[keep]

    def snapto(v, mod):
        r = np.rint(v)
        return r - np.fmod(r, mod)

    passes = 0
    while temp > 1 and passes < 500:
        if temp < min(gx, gy) and passes > 30:
            break  # every step now rounds to zero
        D = k4 * _repulsion(P, 2)
        d = P[a] - P[b]
        ln = np.hypot(d[:, 0], d[:, 1])
        ln[ln == 0] = 0.001
        f = d * (ln / opt)[:, None]           # (d/len) * len^2/opt
        D -= _accumulate(n, a, b, f)
        dl = np.hypot(D[:, 0], D[:, 1])
        big = dl > temp
        D[big] *= (temp / dl[big])[:, None]
        step = np.stack([snapto(D[:, 0], gx), snapto(D[:, 1], gy)], 1)
        step[~mov] = 0
        P = P + step
        yield P
        if passes > 30:
            temp /= 1.1
        passes += 1
    # rescale into the box, snapped to the node grid
    lo, hi = P.min(0), P.max(0)
    ext = hi - lo
    Q = np.zeros_like(P)
    for k, size, g in ((0, width, gx), (1, height, gy)):
        if ext[k] > 0:
            Q[:, k] = snapto((P[:, k] - lo[k]) / ext[k] * (size - pad), g)
    # spread nodes that landed in the same grid cell
    ncx = int(width) // int(gx) + 10
    ncy = int(height) // int(gy) + 10
    cells = np.zeros((ncx, ncy), bool)
    overlapping = 0
    for i in range(n):
        ci = min(max(int(Q[i, 0]) // int(gx), 0), ncx - 1)
        cj = min(max(int(Q[i, 1]) // int(gy), 0), ncy - 1)
        if cells[ci, cj]:
            found = False
            for t in range(1, 5):
                for s in range(t + 1):
                    ci = min(max(0, ci + t), ncx - 1)
                    cj = min(max(0, cj + s), ncy - 1)
                    if not cells[ci, cj]:
                        found = True
                        break
                    ci = min(max(0, ci - t), ncx - 1)
                    cj = min(max(0, cj - s), ncy - 1)
                    if not cells[ci, cj]:
                        found = True
                        break
                if found:
                    break
        Q[i] = (ci * gx, cj * gy)
        if cells[ci, cj]:
            overlapping += 1
            Q[i, 0] += rng.integers(0, int(maxw))
            Q[i, 1] += rng.integers(0, int(maxh))
        cells[ci, cj] = True
    if overlapping:
        print(f"\tThere are {overlapping} overlapping nodes, "
              "(you may want to increase the height/width)")
    yield Q


GEM_BATCH_INSERT = 1000   # above this many nodes, insert breadth-first layers at once


def _gem_batch_insert(snap, rng, pos, elen):
    """Fast GEM insertion for large graphs: place each BFS layer at once, every
    node at the mean of its already-placed neighbours plus jitter (new
    components start at random spots). The arrangement phase then refines."""
    n = snap.n
    placed = np.zeros(n, bool)
    spread = elen * math.sqrt(n)
    order = np.argsort(-snap.degree, kind="stable")
    for root in order:
        if placed[root]:
            continue
        pos[root] = rng.uniform(-spread, spread, 2) if placed.any() else 0.0
        placed[root] = True
        frontier = np.array([root])
        while len(frontier):
            nbrs = np.unique(np.concatenate([snap.neighbors(int(v)) for v in frontier]))
            new = nbrs[~placed[nbrs]]
            if not len(new):
                break
            for v in new.tolist():
                nb = snap.neighbors(v)
                nb = nb[placed[nb]]
                pos[v] = pos[nb].mean(0)
            pos[new] += rng.uniform(-elen, elen, (len(new), 2))
            placed[new] = True
            frontier = new
            yield (pos - pos.min(0)) * 0.25


def _gem_gen(snap, rng):
    """GEM.java (Frick, Ludwig, Mehldau): insertion + arrangement phases.

    The arrangement phase updates all nodes simultaneously per round (the
    original moved one random node at a time) so it vectorises.
    """
    n = snap.n
    if n == 0:
        return
    ELEN = 128.0
    ELENSQR = ELEN * ELEN
    MAXATTRACT = 1048576.0
    outdeg = (np.bincount(snap.src, minlength=n)
              + np.bincount(snap.dst[~snap.directed], minlength=n)).astype(float)
    pr = snap.pairs
    a, b = pr[:, 0], pr[:, 1]
    pos = np.zeros((n, 2))
    heat = np.zeros(n)
    pimp = np.zeros((n, 2))
    rot_dir = np.zeros(n)
    mass = outdeg.copy()
    st = {"temperature": 0.0, "center": np.zeros(2), "osc": 0.0, "rot": 0.0, "maxtemp": 0.0}

    def init(starttemp):
        heat[:] = np.trunc(starttemp * ELEN)
        st["temperature"] = float((heat ** 2).sum())
        pimp[:] = 0
        rot_dir[:] = 0
        mass[:] = 1 + mass / 3
        st["center"] = pos.sum(0)

    def displace(idx, imp):
        nz = (imp != 0).any(1)
        idx, imp = idx[nz], imp[nz]
        if not len(idx):
            return
        big = np.abs(imp).max(1) / 16384
        imp[big > 1] /= np.floor(big[big > 1])[:, None]
        t = np.floor(heat[idx])
        imp = imp * (t / np.hypot(imp[:, 0], imp[:, 1]))[:, None]
        pos[idx] += imp
        st["center"] = st["center"] + imp.sum(0)
        prev = pimp[idx]
        nrm = t * np.floor(np.hypot(prev[:, 0], prev[:, 1]))
        m = nrm > 0
        if m.any():
            i2, t0, im, pv, nr = idx[m], t[m], imp[m], prev[m], nrm[m]
            # GEM keeps heats as integers (Java int arithmetic truncates)
            t1 = np.trunc(t0 + t0 * st["osc"] * (im * pv).sum(1) / nr)
            t1 = np.minimum(t1, st["maxtemp"])
            rot_dir[i2] += st["rot"] * (im[:, 0] * pv[:, 1] - im[:, 1] * pv[:, 0]) / nr
            t1 = np.trunc(t1 - t1 * np.abs(rot_dir[i2]) / n)
            t1 = np.maximum(t1, 2)
            st["temperature"] += float((t1 * t1).sum() - (t0 * t0).sum())
            heat[i2] = t1
        pimp[idx] = imp

    def view():
        lo = pos.min(0)
        return (pos - lo) * 0.25   # Rescale.rescalePositions(.25, pad 0)

    def _gem_insert_each():
        inval = np.zeros(n, np.intp)
        deg = snap.degree
        v = int(np.argmax(deg))   # start at a well-connected node
        inval[v] = -1
        shake = int(0.2 * ELEN)
        for i in range(n):
            if inval.min() < 0:
                v = int(np.argmin(inval))
            else:
                v = int(np.argmax(inval == 0))
            inval[v] = 1
            nb = snap.neighbors(v)
            inval[nb[inval[nb] <= 0]] -= 1
            pos[v] = 0
            if i == 0:
                continue
            ins_nb = nb[inval[nb] > 0]
            if len(ins_nb):
                pos[v] = pos[ins_nb].sum(0)
                if len(ins_nb) > 1:
                    pos[v] = np.trunc(pos[v] / len(ins_nb))
            inserted = inval > 0
            for _ in range(10):
                if heat[v] <= 0.05 * ELEN:
                    break
                p = pos[v]
                imp = rng.integers(-shake, shake + 1, 2).astype(float)
                imp += (st["center"] / n - p) * mass[v] * 0.05
                d = p - pos[inserted]
                d2 = (d * d).sum(1)
                ok = d2 > 0
                imp += (d[ok] * (ELENSQR / d2[ok])[:, None]).sum(0)
                d = p - pos[ins_nb]
                w = np.minimum((d * d).sum(1) / mass[v], MAXATTRACT)
                imp -= (d * (w / ELENSQR)[:, None]).sum(0)
                displace(np.array([v]), imp[None, :])
            if i % 64 == 0:
                yield view()

    # ---- insert phase ----
    init(0.3)
    st["osc"], st["rot"], st["maxtemp"] = 0.4, 0.5, 1.0 * ELEN
    if n > GEM_BATCH_INSERT:
        yield from _gem_batch_insert(snap, rng, pos, ELEN)
        st["center"] = pos.sum(0)
    else:
        yield from _gem_insert_each()
    # ---- arrange phase ----
    init(1.0)
    st["osc"], st["rot"], st["maxtemp"] = 0.4, 0.9, 1.5 * ELEN
    stop_temp = 0.02 * 0.02 * ELENSQR * n
    stop_iter = 3 * n * n
    iteration = 0
    allidx = np.arange(n)
    shake = int(0.3 * ELEN)
    rounds = 0
    max_rounds = min(3 * n, 1000)   # stop_iteration is 3n^2 single-node moves
    while st["temperature"] > stop_temp and iteration < stop_iter and rounds < max_rounds:
        imp = rng.integers(-shake, shake + 1, (n, 2)).astype(float)
        imp += (st["center"] / n - pos) * (mass * 0.1)[:, None]
        imp += ELENSQR * _repulsion(pos, 2)
        if len(a):
            d = pos[a] - pos[b]
            d2 = (d * d).sum(1)
            wa = np.minimum(d2 / mass[a], MAXATTRACT) / ELENSQR
            wb = np.minimum(d2 / mass[b], MAXATTRACT) / ELENSQR
            imp[:, 0] -= np.bincount(a, d[:, 0] * wa, minlength=n) - np.bincount(b, d[:, 0] * wb, minlength=n)
            imp[:, 1] -= np.bincount(a, d[:, 1] * wa, minlength=n) - np.bincount(b, d[:, 1] * wb, minlength=n)
        displace(allidx, imp)
        iteration += n
        rounds += 1
        yield view()
    yield view()


# --------------------------------------------------------------------------
# JUNG layouts
# --------------------------------------------------------------------------

def _jung_start(snap, rng):
    """JUNG layouts start from random positions in the 1000x1000 area
    (fixed nodes stay where they are)."""
    P = rng.random((snap.n, 2)) * BOX
    P[snap.fixed] = snap.pos[snap.fixed]
    return P


def _jfr_gen(snap, rng, max_iter=700):
    """JUNG FRLayout: attraction d^2/k, repulsion k^2/d, cooling temperature."""
    n = snap.n
    if n == 0:
        return
    W = H = BOX
    mov = ~snap.fixed
    P = _jung_start(snap, rng)
    fc = math.sqrt(W * H / n)
    ac, rc = 0.75 * fc, 0.75 * fc
    temp = W / 10
    eps = 1e-6
    a, b = snap.src, snap.dst
    border = W / 50
    it = 0
    while it < max_iter and temp >= 1.0 / max(W, H):
        it += 1
        D = rc * rc * _repulsion(P, 2)
        d = P[a] - P[b]
        ln = np.maximum(np.hypot(d[:, 0], d[:, 1]), eps)
        f = d * (ln / ac)[:, None]
        D -= _accumulate(n, a, b, f)
        dl = np.maximum(np.hypot(D[:, 0], D[:, 1]), eps)
        step = D / dl[:, None] * np.minimum(dl, temp)[:, None]
        step[~mov] = 0
        P = P + step
        for k, size in ((0, W), (1, H)):
            lo = P[:, k] < border
            hi = P[:, k] > size - border
            lo &= mov
            hi &= mov
            P[lo, k] = border + rng.random(int(lo.sum())) * border * 2
            P[hi, k] = size - border - rng.random(int(hi.sum())) * border * 2
        temp *= 1.0 - it / max_iter
        yield P


def _jspring_gen(snap, iters, rng, P=None, ylock=None, tol=0.05):
    """JUNG SpringLayout (stretch 0.7, repulsion range 100, length 30)."""
    n = snap.n
    W = H = BOX
    mov = ~snap.fixed
    if P is None:
        P = _jung_start(snap, rng)
    a, b = snap.src, snap.dst
    deg = (np.bincount(a, minlength=n) + np.bincount(b, minlength=n)).astype(float)
    stretch = 0.70 ** np.maximum(deg[a] + deg[b] - 2, 0)
    vel = np.zeros((n, 2))
    calm = 0
    for _ in range(iters):
        vel /= 4
        d = P[a] - P[b]
        ln = np.hypot(d[:, 0], d[:, 1])
        ln[ln == 0] = 0.0001
        f = (1 / 3) * (30.0 - ln) / ln * stretch
        edge = _accumulate(n, a, b, d * f[:, None])
        R, co = _repulsion(P, 4, cutoff=100.0, coincident=True)
        if co.any():
            R[co] += rng.random((int(co.sum()), 2))
        rl = np.hypot(R[:, 0], R[:, 1])
        ok = rl > 0
        R[ok] *= (2.0 / rl[ok])[:, None]
        vel += R + edge
        step = np.clip(vel, -5, 5)
        step[~mov] = 0
        if ylock is not None:
            step[:, 1] = 0
        P = P + step
        P[mov] = np.clip(P[mov], 0, [W, H])
        yield P
        calm = calm + 1 if _mean_move(step, mov) < tol else 0
        if calm >= 20:
            break


def _isom_gen(snap, rng, max_epoch=2000):
    """JUNG ISOMLayout (Meyer's self-organising map)."""
    n = snap.n
    if n == 0:
        return
    W = H = BOX
    mov = ~snap.fixed
    P = _jung_start(snap, rng)
    indptr, ind = snap.csr
    radius, min_radius, rct = 5, 1, 100
    adaption = initial = 0.9
    for epoch in range(max_epoch):
        t = rng.random(2) * (W, H)
        d = P - t
        win = int(np.argmin((d * d).sum(1)))
        dist = np.full(n, -1, np.intp)
        dist[win] = 0
        frontier = np.array([win])
        level = 0
        reached = [frontier]
        while level < radius and len(frontier):
            level += 1
            nb = _expand(indptr, ind, frontier)[1]
            nb = np.unique(nb[dist[nb] < 0])
            dist[nb] = level
            frontier = nb
            reached.append(nb)
        idx = np.concatenate(reached)
        idx = idx[mov[idx]]
        if len(idx):
            f = adaption / (2.0 ** dist[idx])
            P = P.copy()
            P[idx] += f[:, None] * (t - P[idx])
        e = epoch + 1
        adaption = max(0.0, math.exp(-2.0 * e / max_epoch) * initial)
        if radius > min_radius and e % rct == 0:
            radius -= 1
        yield P


class _KK:
    """Kamada-Kawai energy with incrementally maintained gradients.

    D holds graph distances (any dtype, > 0 off the diagonal); spring length
    is unit * D and stiffness 1/D^2.
    """

    def __init__(self, P, D, unit):
        self.P = np.array(P, float)
        self.D = D
        self.unit = float(unit)
        k = len(P)
        self.G = np.zeros((k, 2))
        step = max(1, _BLOCK // max(k, 1))
        for s in range(0, k, step):
            rows = slice(s, s + step)
            Dr = D[rows].astype(float)
            dx = self.P[rows, 0, None] - self.P[None, :, 0]
            dy = self.P[rows, 1, None] - self.P[None, :, 1]
            dist = np.maximum(np.hypot(dx, dy), 1e-9)
            with np.errstate(divide="ignore", invalid="ignore"):
                c = np.where(Dr > 0, (1 - self.unit * Dr / dist) / (Dr * Dr), 0.0)
            self.G[rows, 0] = (c * dx).sum(1)
            self.G[rows, 1] = (c * dy).sum(1)

    def _col(self, m):
        d = self.D[:, m].astype(float)
        ok = d > 0
        kk = np.zeros_like(d)
        kk[ok] = 1.0 / (d[ok] * d[ok])
        return kk, self.unit * d

    def energy(self):
        k = len(self.P)
        e = 0.0
        step = max(1, _BLOCK // max(k, 1))
        for s in range(0, k, step):
            Dr = self.D[s:s + step].astype(float)
            dx = self.P[s:s + step, 0, None] - self.P[None, :, 0]
            dy = self.P[s:s + step, 1, None] - self.P[None, :, 1]
            d2 = dx * dx + dy * dy
            ok = Dr > 0
            l = self.unit * Dr
            with np.errstate(divide="ignore", invalid="ignore"):
                t = np.where(ok, 0.5 / (Dr * Dr) * (d2 + l * l - 2 * l * np.sqrt(d2)), 0.0)
            e += float(t.sum())
        return e / 2

    def delta(self, m):
        return float(np.hypot(*self.G[m]))

    def newton(self, m):
        kk, l = self._col(m)
        d = self.P[m] - self.P
        dx, dy = d[:, 0], d[:, 1]
        dist = np.maximum(np.hypot(dx, dy), 1e-9)
        d3 = dist ** 3
        gx, gy = self.G[m]
        hxx = (kk * (1 - l * dy * dy / d3)).sum()
        hxy = (kk * l * dx * dy / d3).sum()
        hyy = (kk * (1 - l * dx * dx / d3)).sum()
        den = hxx * hyy - hxy * hxy
        if not den or not math.isfinite(den):
            return 0.0, 0.0
        sx = (hxy * gy - hyy * gx) / den
        sy = (hxy * gx - hxx * gy) / den
        if not (math.isfinite(sx) and math.isfinite(sy)):
            return 0.0, 0.0
        return sx, sy

    def move(self, m, new):
        kk, l = self._col(m)
        P = self.P

        def contrib(pm):
            d = P - pm
            dist = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
            c = kk * (1 - l / dist)
            return d * c[:, None]

        self.G -= contrib(P[m].copy())
        P[m] = new
        self.G += contrib(P[m])
        d = P[m] - P
        dist = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
        c = kk * (1 - l / dist)
        self.G[m] = (d * c[:, None]).sum(0)


def _pmds_embed(D, rng, pivots=100):
    """PivotMDS (Brandes & Pich): a classical-MDS embedding from a few BFS
    columns, scaled to fit the pivot distances. D: k x k graph distances."""
    k = len(D)
    p = min(pivots, k)
    piv = [int(rng.integers(k))]
    mind = D[piv[0]].astype(float)
    for _ in range(p - 1):                       # max-min pivot selection
        nxt = int(np.argmax(mind))
        piv.append(nxt)
        mind = np.minimum(mind, D[nxt])
    C = D[piv].T.astype(float) ** 2
    C = -0.5 * (C - C.mean(0) - C.mean(1)[:, None] + C.mean())
    _, V = np.linalg.eigh(C.T @ C)
    X = C @ V[:, -2:][:, ::-1]
    Dp = D[piv].T.astype(float)
    ok = Dp > 0
    dd = np.hypot(X[:, None, 0] - X[None, piv, 0], X[:, None, 1] - X[None, piv, 1])
    r = dd[ok] / Dp[ok]
    scale = r.sum() / max((r * r).sum(), 1e-12)
    return X * scale


def _stress_fast_gen(X, D, ei, ej, fixed, rng, iters=60, samples=48):
    """Kamada-Kawai energy (stress with weights 1/d^2) minimised by Jacobi
    stress-majorization steps over every edge plus a fresh random sample of
    other nodes per iteration (weights rescaled so the sample stands for all
    pairs). Linear per iteration; within a few percent of exact KK energy.

    X: k x 2 start (in distance units), D: k x k distances, (ei, ej): edges in
    both directions as local indices. Yields X after each iteration."""
    k = len(X)
    X = np.array(X, float)
    s = min(samples, k - 1)
    rows = np.arange(k)
    de = D[ei, ej].astype(float)
    ok = de > 0
    ei, ej, de = ei[ok], ej[ok], de[ok]
    we = 1.0 / (de * de)
    free = ~np.asarray(fixed, bool)
    for _ in range(iters):
        J = rng.integers(0, k - 1, size=(k, s))
        J += J >= rows[:, None]                  # never sample yourself
        dj = D[rows[:, None], J].astype(float)
        with np.errstate(divide="ignore"):
            wj = np.where(dj > 0, (k - 1) / s / (dj * dj), 0.0)
        I = np.concatenate([np.repeat(rows, s), ei])
        Jall = np.concatenate([J.ravel(), ej])
        d = np.concatenate([dj.ravel(), de])
        w = np.concatenate([wj.ravel(), we])
        diff = X[I] - X[Jall]
        dist = np.maximum(np.hypot(diff[:, 0], diff[:, 1]), 1e-9)
        tx = X[Jall] + (d / dist)[:, None] * diff
        den = np.bincount(I, w, k)
        num = np.stack([np.bincount(I, w * tx[:, 0], k), np.bincount(I, w * tx[:, 1], k)], 1)
        upd = free & (den > 0)
        X[upd] = num[upd] / den[upd, None]
        yield X


def _local_edges(snap, comp):
    """Edges inside comp (both directions) as indices into comp."""
    loc = np.full(snap.n, -1, np.intp)
    loc[comp] = np.arange(len(comp))
    p = snap.pairs
    a, b = loc[p[:, 0]], loc[p[:, 1]]
    keep = (a >= 0) & (b >= 0)
    a, b = a[keep], b[keep]
    return np.concatenate([a, b]), np.concatenate([b, a])


def _guess_kk_gen(snap, width, height, budget_per_node=4):
    """KamadaGraphLayout.java: circle start, KK per component, rescale to box."""
    n = snap.n
    width, height = float(width), float(height)
    pad = 20
    P = snap.pos.copy()
    if n == 0:
        return
    r = min(width, height) / 2 - pad * 2
    ang = 2 * math.pi * np.arange(n) / n
    P[:, 0] = r * np.cos(ang) + width / 2
    P[:, 1] = r * np.sin(ang) + height / 2
    P[snap.fixed] = snap.pos[snap.fixed]
    yield P
    indptr, ind = snap.csr
    for comp in snap.components:
        if len(comp) < 2:
            continue
        comp = np.array(sorted(comp))
        D = _bfs_hops(indptr, ind, n, comp)[:, comp]
        diam = max(int(D.max()), 1)
        fixed = snap.fixed[comp]
        k = len(comp)
        if k > _KK_FAST:
            unit = min(width, height) / diam
            centre = np.array([width / 2, height / 2])
            rng = np.random.default_rng(0)
            X0 = (P[comp] - centre) / unit if fixed.any() else _pmds_embed(D, rng)
            for X in _stress_fast_gen(X0, D, *_local_edges(snap, comp), fixed, rng):
                Q = P.copy()
                Q[comp] = np.where(fixed[:, None], P[comp], X * unit + centre)
                yield Q
            P = Q
            continue
        kk = _KK(P[comp], D, min(width, height) / diam)
        eps = kk.energy() / k
        budget = max(5000, budget_per_node * k)
        sub = 0

        def maxdelta(kk=kk, fixed=fixed):
            dm = np.hypot(kk.G[:, 0], kk.G[:, 1])
            dm[fixed] = -1
            m = int(np.argmax(dm))
            return m, float(dm[m])

        m, dmax = maxdelta()
        while eps > 1 and sub < budget:
            rounds = 0
            while dmax > eps and sub < budget and rounds < 4 * k:
                rounds += 1
                cur = best = dmax
                stalled = 0
                for _ in range(50):
                    if cur <= eps or sub >= budget:
                        break
                    sx, sy = kk.newton(m)
                    if abs(sx) + abs(sy) < 1e-3:
                        break
                    kk.move(m, kk.P[m] + (sx, sy))
                    cur = kk.delta(m)
                    sub += 1
                    Q = P.copy()
                    Q[comp] = kk.P
                    yield Q
                    if cur < best * 0.99:
                        best, stalled = cur, 0
                    else:
                        stalled += 1
                        if stalled >= 3:
                            break
                last_m, last_d = m, dmax
                m, dmax = maxdelta()
                if dmax <= 0 or (m == last_m and dmax >= last_d * 0.99):
                    break   # the worst node cannot be improved at this epsilon
            eps -= eps / 4
        P = P.copy()
        P[comp] = kk.P
        yield P
    Q = _bbox_rescale(P, width, height)
    yield Q


def _jung_kk_gen(snap, rng, D, max_iter, exchange=True):
    """JUNG KKLayout / WeightedKK: move the worst node per iteration."""
    n = snap.n
    if n == 0:
        return
    W = H = BOX
    fixed = snap.fixed
    P = _jung_start(snap, rng)
    finite = np.isfinite(D) & (D >= 0) if D.dtype.kind == "f" else D >= 0
    diameter = float(D[finite].max()) if finite.any() else 0.0
    diameter = max(diameter, 1.0)
    Dm = np.where(finite, D, diameter + 1).astype(np.float32 if D.dtype.kind == "f" else np.int16)
    np.fill_diagonal(Dm, 0)
    Dm = np.where((Dm <= 0) & ~np.eye(n, dtype=bool), 1e-3, Dm) if Dm.dtype.kind == "f" else Dm
    unit = min(W, H) / diameter * 0.9
    if n > _KK_FAST:
        centre = np.array([W / 2, H / 2])
        X0 = (P - centre) / unit if fixed.any() else _pmds_embed(Dm, rng)
        p = snap.pairs
        ei = np.concatenate([p[:, 0], p[:, 1]])
        ej = np.concatenate([p[:, 1], p[:, 0]])
        for X in _stress_fast_gen(X0, Dm, ei, ej, fixed, rng):
            yield np.where(fixed[:, None], P, X * unit + centre)
        return
    kk = _KK(P, Dm, unit)
    EPS = 0.1
    gravity = not fixed.any()
    for _ in range(max_iter):
        dm = np.hypot(kk.G[:, 0], kk.G[:, 1])
        dm[fixed] = 0
        pm = int(np.argmax(dm))
        maxd = float(dm[pm])
        if maxd <= 0:
            break
        best, stalled = maxd, 0
        for _ in range(100):
            sx, sy = kk.newton(pm)
            if abs(sx) + abs(sy) < 1e-3:
                break
            kk.move(pm, kk.P[pm] + (sx, sy))
            cur = kk.delta(pm)
            if cur < EPS:
                break
            # Newton can orbit without converging; JUNG then spent all 100 steps
            if cur < best * 0.99:
                best, stalled = cur, 0
            else:
                stalled += 1
                if stalled >= 3:
                    break
        if gravity:
            kk.P += np.array([W / 2, H / 2]) - kk.P.mean(0)
        if exchange and maxd < EPS and n <= 150:
            _kk_try_exchange(kk, fixed)
        yield kk.P.copy()


def _kk_try_exchange(kk, fixed):
    """Swap the first pair of vertices whose exchange lowers the energy."""
    P, D, unit = kk.P, kk.D.astype(float), kk.unit
    k = len(P)
    with np.errstate(divide="ignore", invalid="ignore"):
        K = np.where(D > 0, 1.0 / (D * D), 0.0)
    L = unit * D
    dist = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])

    def f(Krow, Lrow, d):
        return 0.5 * Krow * (d * d + Lrow * Lrow - 2 * Lrow * d)

    for p in range(k - 1):
        if fixed[p]:
            continue
        base_p = f(K[p], L[p], dist[p])            # energy terms of p at its place
        for q in range(p + 1, k):
            if fixed[q]:
                continue
            mask = np.ones(k, bool)
            mask[[p, q]] = False
            old = base_p[mask].sum() + f(K[q], L[q], dist[q])[mask].sum()
            new = f(K[p], L[p], dist[q])[mask].sum() + f(K[q], L[q], dist[p])[mask].sum()
            if new < old:
                a, b = P[p].copy(), P[q].copy()
                kk.move(p, b)
                kk.move(q, a)
                return True
    return False


# --------------------------------------------------------------------------
# Layered layouts
# --------------------------------------------------------------------------

def _eades_dag(snap):
    """EadesGreedyDAG: orient every edge so the graph is acyclic.

    Undirected edges count in both directions (DirectionTransformer); arcs
    pointing backwards in the Eades ordering are reversed.  Returns unique
    arcs (u, v) as two int arrays, self-loops dropped.
    """
    n = snap.n
    s, t, dr = snap.src, snap.dst, snap.directed
    keep = s != t
    a = np.concatenate([s[keep], t[keep & ~dr]])
    b = np.concatenate([t[keep], s[keep & ~dr]])
    if len(a):
        key = np.unique(a * n + b)
        a, b = key // n, key % n
    out_adj = [[] for _ in range(n)]
    in_adj = [[] for _ in range(n)]
    for u, v in zip(a.tolist(), b.tolist()):
        out_adj[u].append(v)
        in_adj[v].append(u)
    outd = [len(x) for x in out_adj]
    ind = [len(x) for x in in_adj]
    removed = [False] * n
    sinks = deque(i for i in range(n) if outd[i] == 0)
    sources = deque(i for i in range(n) if ind[i] == 0)
    heap = [(-(outd[i] - ind[i]), i) for i in range(n)]
    heapq.heapify(heap)
    s1, s2 = [], deque()
    left = n

    def remove(v):
        removed[v] = True
        for u in in_adj[v]:
            if not removed[u]:
                outd[u] -= 1
                if outd[u] == 0:
                    sinks.append(u)
                heapq.heappush(heap, (-(outd[u] - ind[u]), u))
        for w in out_adj[v]:
            if not removed[w]:
                ind[w] -= 1
                if ind[w] == 0:
                    sources.append(w)
                heapq.heappush(heap, (-(outd[w] - ind[w]), w))

    while left:
        while sinks:
            v = sinks.popleft()
            if removed[v] or outd[v] != 0:
                continue
            s2.appendleft(v)
            remove(v)
            left -= 1
        while sources:
            v = sources.popleft()
            if removed[v] or ind[v] != 0:
                continue
            s1.append(v)
            remove(v)
            left -= 1
        while left and heap:
            negd, v = heapq.heappop(heap)
            if removed[v] or -negd != outd[v] - ind[v]:
                continue
            s1.append(v)
            remove(v)
            left -= 1
            break
    order = s1 + list(s2)
    rank = np.empty(n, np.intp)
    rank[np.array(order, np.intp)] = np.arange(n)
    fwd = rank[a] < rank[b] if len(a) else np.zeros(0, bool)
    u = np.where(fwd, a, b)
    v = np.where(fwd, b, a)
    if len(u):
        key = np.unique(u * n + v)
        u, v = key // n, key % n
    return u, v, order


def _longest_path_levels(n, u, v, order):
    """Level = longest path from a source; every arc goes to a higher level."""
    level = np.zeros(n, np.intp)
    preds = [[] for _ in range(n)]
    for x, y in zip(u.tolist(), v.tolist()):
        preds[y].append(x)
    for y in order:   # order is topological for the oriented arcs
        if preds[y]:
            level[y] = max(level[x] for x in preds[y]) + 1
    return level


def _dfs_level_lists(n, u, v, level, nlevels):
    """Nodes of each level in DFS preorder from the roots (GUESS fillLevels order)."""
    succ = [[] for _ in range(n)]
    indeg = np.zeros(n, np.intp)
    for x, y in zip(u.tolist(), v.tolist()):
        succ[x].append(y)
        indeg[y] += 1
    levels = [[] for _ in range(nlevels)]
    seen = np.zeros(n, bool)
    starts = [i for i in range(n) if indeg[i] == 0] + list(range(n))
    for r in starts:
        if seen[r]:
            continue
        stack = [r]
        while stack:
            x = stack.pop()
            if seen[x]:
                continue
            seen[x] = True
            levels[level[x]].append(x)
            stack.extend(reversed(succ[x]))
    return levels, succ


def _sugiyama_positions(snap, bends=False, bend_out=None):
    """Port of SugiyamaLayout (JGraph's Sugiyama as adapted by GUESS).

    With bends, arcs spanning several levels are routed through dummy
    vertices; if bend_out is a dict it receives {(u, v): [(x, y), ...]} with the
    dummies' centre points, u/v being node indices of the (acyclic) arc."""
    n = snap.n
    P = snap.pos.copy()
    if n == 0:
        return P
    u, v, order = _eades_dag(snap)
    level = _longest_path_levels(n, u, v, order)
    L = int(level.max()) + 1
    total = n
    chains = {}
    if bends:   # chains of dummy vertices for arcs spanning several levels
        nu, nv = [], []
        lev = level.tolist()
        for x, y in zip(u.tolist(), v.tolist()):
            prev = x
            for lv in range(lev[x] + 1, lev[y]):
                lev.append(lv)
                nu.append(prev)
                nv.append(total)
                chains.setdefault((x, y), []).append(total)
                prev = total
                total += 1
            nu.append(prev)
            nv.append(y)
        u = np.array(nu, np.intp)
        v = np.array(nv, np.intp)
        level = np.array(lev, np.intp)
    levels, succ = _dfs_level_lists(total, u, v, level, L)
    # --- solveEdgeCrosses: running-average indicators, sorted per level ---
    ind_sum = np.zeros(total)
    ind_cnt = np.ones(total)
    for lv in levels:
        for k, x in enumerate(lv):
            ind_sum[x] = k
    for _ in range(100):
        moves = 0
        sweep = [(i, True) for i in range(L - 1)] + [(i, False) for i in range(L - 1, 0, -1)]
        for i, down in sweep:
            lv = levels[i]
            before = [ind_sum[x] / ind_cnt[x] for x in lv]
            lv.sort(key=lambda x: -(ind_sum[x] / ind_cnt[x]))
            moves += sum(1 for x, bv in zip(lv, before) if ind_sum[x] / ind_cnt[x] != bv)
            for x in reversed(lv):
                val = ind_sum[x] / ind_cnt[x]
                for y in succ[x]:
                    if (level[y] > i) if down else (level[y] < i):
                        ind_sum[y] += val
                        ind_cnt[y] += 1
        if moves == 0:
            break
    # --- moveToBarycenter with priorities ---
    prio = np.array([len(succ[x]) for x in range(total)])
    grid = np.zeros(total, np.intp)
    for lv in levels:
        for k, x in enumerate(lv):
            grid[x] = k
    area = max(len(lv) for lv in levels)

    def move(lv, idx, right, pr):
        st = 1 if right else -1
        chain = [idx]
        j = idx
        while True:
            if not (0 <= grid[lv[j]] + st < area):
                return False
            k = j + st
            if k < 0 or k >= len(lv):
                break
            if grid[lv[k]] != grid[lv[j]] + st:
                break
            if prio[lv[k]] >= pr:
                return False
            chain.append(k)
            j = k
        for c in chain:
            grid[lv[c]] += st
        return True

    for _ in range(100):
        moves = 0
        for i in list(range(1, L)) + list(range(L - 1, -1, -1)):
            lv = levels[i]
            for idx, x in enumerate(lv):
                nb = [y for y in succ[x] if level[y] != i]
                if not nb:
                    continue
                target = math.floor(sum(grid[y] for y in nb) / len(nb) + 0.5)
                right = target > grid[x]
                while target != grid[x] and move(lv, idx, right, prio[x]):
                    moves += 1
        if moves == 0:
            break
    # --- drawGraph on a 250 x 150 grid from the current top-left corner ---
    minx = math.floor(float(P[:, 0].min()))
    miny = math.floor(float(P[:, 1].min()))
    X = minx + 250.0 * grid
    Y = miny + 150.0 * level
    # --- shiftLayers: slide each layer (5px steps) to shorten its edges ---
    na = np.concatenate([u, v])
    nb_ = np.concatenate([v, u])
    layer_pairs = [(na[level[na] == i], nb_[level[na] == i]) for i in range(L)]

    def tension(i):
        pa, pb = layer_pairs[i]
        if not len(pa):
            return 0.0
        return float(np.hypot(X[pa] - X[pb], Y[pa] - Y[pb]).mean())

    members = [np.array(lv, np.intp) for lv in levels]

    def optimise(i):
        prev = tension(i)
        X[members[i]] += 5
        amt = 5.0
        right = tension(i)
        X[members[i]] -= 10
        amt -= 10
        left = tension(i)
        sign = -1.0 if left < right else 1.0
        for _ in range(100000):
            X[members[i]] += sign * 5
            amt += sign * 5
            cur = tension(i)
            if cur > prev:
                X[members[i]] -= sign * 5
                amt -= sign * 5
                break
            prev = cur
        return amt

    for i in range(L):
        amt = optimise(i)
        for j in range(i - 1, -1, -1):
            X[members[j]] += amt
    for i in range(L - 1, 0, -1):
        amt = optimise(i)
        for j in range(i + 1, L):
            X[members[j]] += amt
    P[:, 0] = X[:n]
    P[:, 1] = Y[:n]
    if bend_out is not None and chains:
        hw, hh = (np.median(snap.size, axis=0) / 2).tolist()
        for arc, ds in chains.items():
            bend_out[arc] = [(float(X[d]) + hw, float(Y[d]) + hh) for d in ds]
    return P


def _sugiyama2_positions(snap):
    """Port of Sugiyama2: tiers 200px apart, nodes spread by child counts."""
    n = snap.n
    P = snap.pos.copy()
    if n == 0:
        return P
    u, v, order = _eades_dag(snap)
    level = _longest_path_levels(n, u, v, order)
    L = int(level.max()) + 1
    levels, _ = _dfs_level_lists(n, u, v, level, L)
    # original used a fixed 200px width per tier; widen it so big tiers don't pile up
    comp_w = max(200.0, 2.0 * float(snap.size[:, 0].max()) * max(len(t) for t in levels))
    child_of = {}   # parent -> set of nodes it has an edge to (directed out or undirected)
    for s, t, dr in zip(snap.src.tolist(), snap.dst.tolist(), snap.directed.tolist()):
        child_of.setdefault(s, set()).add(t)
        if not dr:
            child_of.setdefault(t, set()).add(s)
    widths = snap.size[:, 0]
    major = 0.0
    for i in range(L):
        tier = levels[i]
        children = levels[i + 1] if i + 1 < L else None
        if children is not None:
            cset = set(children)
            counts = [len(child_of.get(p, set()) & cset) for p in tier]
            childless = sum(1 for c in counts if c == 0)
            prev = 0.0
            for p, c in zip(tier, counts):
                if childless == 0:
                    nsw = c / len(children) * comp_w
                else:
                    nsw = comp_w / (childless + len(children))
                minor = prev + nsw / 2
                P[p] = (minor - widths[p] / 2, major)
                prev += nsw
        else:
            for k, p in enumerate(tier):
                P[p] = ((k + 1) / (len(tier) + 1) * comp_w, major)
        major += 200
    return P


def _dag_gen(snap, rng, iters):
    """JUNG DAGLayout: spring layout with each node held on its level's line."""
    n = snap.n
    if n == 0:
        return
    u, v, order = _eades_dag(snap)
    level = _longest_path_levels(n, u, v, order)
    height = max(int(level.max()), 1)
    P = _jung_start(snap, rng)
    ys = level * BOX / (height * 1.3)
    mov = ~snap.fixed
    P[mov, 1] = ys[mov]
    yield P
    yield from _jspring_gen(snap, iters, rng, P=P, ylock=True)


# --------------------------------------------------------------------------
# MDS
# --------------------------------------------------------------------------

def _top_eigs(matvec, n, k, rng, steps=None):
    """Largest-algebraic eigenpairs of a symmetric operator (Lanczos, full reorth)."""
    m = min(n, steps or max(4 * k + 20, 60))
    Q = np.zeros((n, m + 1))
    alpha = np.zeros(m)
    beta = np.zeros(m)
    q = rng.standard_normal(n)
    q /= np.linalg.norm(q)
    Q[:, 0] = q
    used = m
    for j in range(m):
        w = matvec(Q[:, j])
        alpha[j] = Q[:, j] @ w
        w -= Q[:, :j + 1] @ (Q[:, :j + 1].T @ w)
        w -= Q[:, :j + 1] @ (Q[:, :j + 1].T @ w)
        nb = np.linalg.norm(w)
        if nb < 1e-10:
            used = j + 1
            break
        beta[j] = nb
        Q[:, j + 1] = w / nb
    T = np.diag(alpha[:used]) + np.diag(beta[:used - 1], 1) + np.diag(beta[:used - 1], -1)
    vals, vecs = np.linalg.eigh(T)
    order = np.argsort(vals)[::-1][:k]
    return vals[order], Q[:, :used] @ vecs[:, order]


def _mds_positions(snap, rng):
    """Port of SMDS: classical MDS of a matrix that is 1 everywhere except
    edge weights on edges; nodes without edges keep their positions."""
    n = snap.n
    P = snap.pos.copy()
    keep = snap.src != snap.dst
    a, b, w = snap.src[keep], snap.dst[keep], snap.weight[keep]
    if n < 2 or not len(a):
        return P, False
    # S = D^2 - 1 (non-zero only on edge pairs; last edge wins like dp[i][j] = w)
    key = np.minimum(a, b) * n + np.maximum(a, b)
    _, last = np.unique(key[::-1], return_index=True)
    sel = len(key) - 1 - last
    i, j, s = np.minimum(a, b)[sel], np.maximum(a, b)[sel], w[sel] ** 2 - 1.0
    present = np.zeros(n, bool)
    present[a] = True
    present[b] = True

    def center(x):
        return x - x.mean()

    if n <= 400:
        S = np.zeros((n, n))
        S[i, j] = s
        S[j, i] = s
        J = np.eye(n) - 1.0 / n
        B = -0.5 * J @ S @ J
        vals, vecs = np.linalg.eigh(B)
        order = np.argsort(vals)[::-1][:2]
        vals, vecs = vals[order], vecs[:, order]
    else:
        ii = np.concatenate([i, j])
        jj = np.concatenate([j, i])
        ss = np.concatenate([s, s])

        def matvec(x):
            y = center(x)
            return -0.5 * center(np.bincount(ii, ss * y[jj], minlength=n))

        vals, vecs = _top_eigs(matvec, n, 2, rng)
    if vals[0] < 1e-5:
        return P, True   # no structure: all weights equal
    vals = np.sqrt(np.where(vals < 1e-5, 0.0, vals))
    X = vecs * vals[None, :] * 1000.0
    P[present] = X[present]
    return P, False


def _pivot_mds(snap, rng, pivots=50):
    """Fallback for mdsLayout when every weight is equal: pivot MDS on hop counts."""
    n = snap.n
    indptr, ind = snap.csr
    k = min(n, pivots)
    piv = [int(np.argmax(snap.degree))]
    mind = None
    for _ in range(k - 1):
        d = _bfs_hops(indptr, ind, n, [piv[-1]])[0].astype(float)
        d[d < 0] = np.inf
        mind = d if mind is None else np.minimum(mind, d)
        cand = np.where(np.isfinite(mind), mind, -1)
        nxt = int(np.argmax(cand))
        if cand[nxt] <= 0:
            unreached = np.flatnonzero(~np.isfinite(mind))
            if not len(unreached):
                break
            nxt = int(unreached[0])
        piv.append(nxt)
    D = _bfs_hops(indptr, ind, n, piv).astype(float).T
    D[D < 0] = D.max() + 1
    C = D * D
    C = -0.5 * (C - C.mean(0) - C.mean(1)[:, None] + C.mean())
    U, S, _ = np.linalg.svd(C, full_matrices=False)
    X = U[:, :2] * S[:2]
    if len(snap.pairs):
        el = np.hypot(*(X[snap.pairs[:, 0]] - X[snap.pairs[:, 1]]).T)
        med = float(np.median(el[el > 0])) if (el > 0).any() else 1.0
        X *= 50.0 / med
    return X


# --------------------------------------------------------------------------
# Bin packing
# --------------------------------------------------------------------------

class _Rect:
    __slots__ = ("x", "y", "w", "h", "nodes", "ox", "oy")

    def __init__(self, x, y, w, h, nodes=None):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.nodes = nodes
        self.ox, self.oy = x, y

    @property
    def size(self):
        return self.w * self.h


def _binpack_positions(snap, rescale=True):
    """Port of BinPack: pack the bounding boxes of the weak components."""
    P = snap.pos.copy()
    comps = snap.components
    if len(comps) <= 1:
        return P
    sz = snap.size
    rects = []
    maxd = -math.inf
    for c in comps:
        c = np.array(c)
        lo = P[c].min(0) - 15
        hi = (P[c] + sz[c]).max(0) + 15
        r = _Rect(lo[0], lo[1], hi[0] - lo[0], hi[1] - lo[1], c)
        rects.append(r)
        maxd = max(maxd, (r.w - 30) * (r.h - 30) / len(c))
    rects.sort(key=lambda r: r.size)
    if rescale:
        seen = {}
        for r in reversed(rects):
            test = maxd * len(r.nodes) / r.size if r.size else 0
            if len(r.nodes) > 1 and test != 1 and test > 0 and math.isfinite(test):
                f = seen.setdefault(len(r.nodes), max(0.1, 1 + math.log(test)))
                P[r.nodes] = (r.x, r.y) + (P[r.nodes] - (r.x, r.y)) * f
                # the original scaled the box too, which could clip node boxes when
                # shrinking; re-measure so packed components never overlap
                c = r.nodes
                lo = P[c].min(0) - 15
                hi = (P[c] + sz[c]).max(0) + 15
                r.x, r.y, r.w, r.h = lo[0], lo[1], hi[0] - lo[0], hi[1] - lo[1]
                r.ox, r.oy = r.x, r.y
        rects.sort(key=lambda r: r.size)
    avail = [_Rect(0.0, 0.0, sum(r.w for r in rects), sum(r.h for r in rects))]
    xc = yc = 0.0
    bottom = 0.0
    for k, tf in enumerate(reversed(rects)):
        best, bd = -1, math.inf
        for i in range(len(avail) - 1, -1, -1):
            t = avail[i]
            if tf.w <= t.w and tf.h <= t.h:
                d = math.hypot(xc - (t.x + tf.w / 2), yc - (t.y + tf.h / 2))
                if d < bd:
                    bd, best = d, i
        if best < 0:   # no room left (cannot happen in the original's tests); stack below
            tf.x, tf.y = 0.0, bottom
        else:
            bf = avail.pop(best)
            tf.x, tf.y = bf.x, bf.y
            avail.append(_Rect(bf.x + tf.w, bf.y, bf.w - tf.w, tf.h))
            avail.append(_Rect(bf.x, bf.y + tf.h, bf.w, bf.h - tf.h))
            avail.sort(key=lambda r: r.size)
        bottom = max(bottom, tf.y + tf.h)
        if k == 0:
            xc, yc = tf.w / 2, tf.h / 2
    for r in rects:
        P[r.nodes] += (r.x - r.ox, r.y - r.oy)
    return P


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Gephi layouts: ForceAtlas2 and Noverlap
# --------------------------------------------------------------------------

def _close_pairs(C, reach):
    """Index pairs (i < j) whose centres are closer than reach[i] + reach[j]."""
    n = len(C)
    empty = (np.zeros(0, np.intp), np.zeros(0, np.intp))
    if n < 2:
        return empty
    cell = 2 * float(reach.max())
    if cell <= 0:
        return empty
    lo = C.min(0)
    key, M = _grid_keys(C, lo, cell)
    order = np.argsort(key, kind="stable")
    ukeys, ustart, ucount = np.unique(key[order], return_index=True, return_counts=True)
    allidx = np.arange(n)
    out_i, out_j = [], []
    for ox, oy in ((0, 0), (1, -1), (1, 0), (1, 1), (0, 1)):
        nk = key + ox * M + oy
        loc = np.minimum(np.searchsorted(ukeys, nk), len(ukeys) - 1)
        hit = ukeys[loc] == nk
        cnt = np.where(hit, ucount[loc], 0)
        st = np.where(hit, ustart[loc], 0)
        tot = int(cnt.sum())
        if not tot:
            continue
        ii = np.repeat(allidx, cnt)
        jj = order[np.repeat(st - (np.cumsum(cnt) - cnt), cnt) + np.arange(tot)]
        if ox == 0 and oy == 0:
            keep = ii < jj
            ii, jj = ii[keep], jj[keep]
        d = C[ii] - C[jj]
        close = np.hypot(d[:, 0], d[:, 1]) < reach[ii] + reach[jj]
        out_i.append(ii[close])
        out_j.append(jj[close])
    if not out_i:
        return empty
    return np.concatenate(out_i), np.concatenate(out_j)


def _fa2_gen(snap, iters, rng, scaling=None, gravity=1.0, strong=False, linlog=False,
             dissuade=False, overlap=False, weight_influence=1.0, jitter=None):
    """ForceAtlas2 (Jacomy et al. 2014; Gephi's ForceAtlas2.java): degree+1 masses,
    repulsion k_r m_i m_j / d, linear (or lin-log) attraction, gravity toward the
    centre, and Gephi's adaptive global/local speed. Repulsion beyond the
    nearest cells uses the grid approximation (the role of Barnes-Hut)."""
    n = snap.n
    if n == 0:
        return
    half = snap.size / 2
    mov = ~snap.fixed
    C = _jitter_coincident(snap.pos + half, rng, 1.0, mov)
    origin = C.mean(0)
    C = C - origin
    keep = snap.src != snap.dst
    a, b = snap.src[keep], snap.dst[keep]
    w = np.abs(snap.weight[keep])
    if weight_influence == 0:
        w = np.ones_like(w)
    elif weight_influence != 1:
        w = w ** float(weight_influence)
    mass = 1.0 + np.bincount(a, minlength=n) + np.bincount(b, minlength=n)
    radius = snap.size.max(1) / 2
    kr = float(scaling) if scaling is not None else (2.0 if n >= 100 else 10.0)
    g = float(gravity)
    jt = float(jitter) if jitter is not None else (10.0 if n >= 50000 else 1.0)
    coef = float(mass.mean()) if dissuade else 1.0
    speed, efficiency = 1.0, 1.0
    Fold = np.zeros((n, 2))
    for _ in range(iters):
        F = kr * mass[:, None] * _repulsion(C, 2, mass=mass)
        if overlap:
            ii, jj = _close_pairs(C, radius)
            if len(ii):
                d = C[ii] - C[jj]
                f = (100 * kr * mass[ii] * mass[jj])[:, None] * d
                F += _accumulate(n, ii, jj, f)
        # gravity toward the centre
        if g:
            if strong:
                F -= (mass * g)[:, None] * C
            else:
                dist = np.hypot(C[:, 0], C[:, 1])
                F -= ((mass * g) / np.where(dist > 0, dist, 1))[:, None] * C
        # attraction along edges
        if len(a):
            d = C[a] - C[b]
            dist = np.hypot(d[:, 0], d[:, 1])
            if overlap:
                dist = dist - radius[a] - radius[b]
            if linlog:
                fac = -coef * w * np.log1p(np.maximum(dist, 0)) / np.where(dist > 0, dist, 1)
                if not overlap:
                    fac = np.where(dist > 0, fac, 0.0)
            else:
                fac = -coef * w
            if overlap:
                fac = np.where(dist > 0, fac, 0.0)
            if dissuade:
                fac = fac / mass[a]
            F += _accumulate(n, a, b, d * fac[:, None])
        F[~mov] = 0
        # adaptive speed (ForceAtlas2.java)
        swing = mass * np.hypot(*(F - Fold).T)
        traction = 0.5 * mass * np.hypot(*(F + Fold).T)
        total_swing = float(swing[mov].sum())
        total_traction = float(traction[mov].sum()) or 1e-9
        est = 0.05 * math.sqrt(n)
        jitter_tol = jt * max(math.sqrt(est), min(10.0, est * total_traction / (n * n)))
        if total_swing / total_traction > 2.0:
            if efficiency > 0.05:
                efficiency *= 0.5
            jitter_tol = max(jitter_tol, jt)
        target = jitter_tol * efficiency * total_traction / max(total_swing, 1e-9)
        if total_swing > jitter_tol * total_traction:
            if efficiency > 0.05:
                efficiency *= 0.7
        elif speed < 1000:
            efficiency *= 1.3
        speed += min(target - speed, 0.5 * speed)
        if overlap:
            fac = 0.1 * speed / (1 + np.sqrt(speed * swing))
            df = np.hypot(F[:, 0], F[:, 1])
            fac = np.where(df > 0, np.minimum(fac * df, 10.0) / np.where(df > 0, df, 1), 0.0)
        else:
            fac = speed / (1 + np.sqrt(speed * swing))
        C = C + F * fac[:, None]
        Fold = F
        yield C + origin - half


_JS_FA2_MIN = 1000   # in the browser, ForceAtlas2 on larger graphs runs in JS (Barnes-Hut)


def _js_fa2():
    """The JS ForceAtlas2 class when running in Pyodide's worker, else None."""
    try:
        import js
        from pyodide.ffi import to_js
    except ImportError:
        return None
    cls = getattr(js, "GuessFA2", None)
    return (cls, to_js) if cls is not None else None


def _fa2_js_gen(snap, iters, rng, scaling=None, gravity=1.0, strong=False, linlog=False,
                dissuade=False, overlap=False, weight_influence=1.0, jitter=None, engine=None):
    """ForceAtlas2 with Barnes-Hut repulsion in JS (web/src/fa2.ts), stepped a few
    iterations per call so the display animates and Stop works between calls."""
    import json
    cls, to_js = engine
    n = snap.n
    half = snap.size / 2
    mov = ~snap.fixed
    C = _jitter_coincident(snap.pos + half, rng, 1.0, mov)
    origin = C.mean(0)
    C = C - origin
    keep = snap.src != snap.dst
    a, b = snap.src[keep], snap.dst[keep]
    w = np.abs(snap.weight[keep])
    if weight_influence == 0:
        w = np.ones_like(w)
    elif weight_influence != 1:
        w = w ** float(weight_influence)
    mass = 1.0 + np.bincount(a, minlength=n) + np.bincount(b, minlength=n)
    opts = {"scaling": float(scaling) if scaling is not None else (2.0 if n >= 100 else 10.0),
            "gravity": float(gravity), "strong": bool(strong), "linlog": bool(linlog),
            "dissuade": bool(dissuade), "overlap": bool(overlap), "theta": 1.2,
            "jitter": float(jitter) if jitter is not None else (10.0 if n >= 50000 else 1.0)}
    sim = cls.new(to_js(C.ravel().tolist()), to_js(mass.tolist()), to_js((snap.size.max(1) / 2).tolist()),
                  to_js(snap.fixed.astype(int).tolist()), to_js(a.tolist()), to_js(b.tolist()),
                  to_js(w.tolist()), json.dumps(opts))
    done, chunk = 0, 1
    while done < iters:
        k = min(chunk, iters - done)
        t0 = time.monotonic()
        out = sim.step(k)
        P = np.frombuffer(out.to_py(), dtype=np.float64).reshape(-1, 2).copy()
        done += k
        dt = time.monotonic() - t0
        chunk = max(1, min(50, int(k * 0.06 / max(dt, 1e-4))))   # about 60 ms per call
        yield P + origin - half


def _noverlap_gen(snap, rng, margin=5.0, ratio=1.2, max_iter=1000):
    """Gephi's Noverlap: push overlapping nodes apart (nodes as circles of
    ratio * size / 2 plus margin) until no two overlap. Fixed nodes stay put."""
    n = snap.n
    if n < 2:
        return
    half = snap.size / 2
    mov = ~snap.fixed
    C = _jitter_coincident(snap.pos + half, rng, 1.0, mov)
    reach = ratio * snap.size.max(1) / 2 + margin / 2
    for _ in range(max_iter):
        ii, jj = _close_pairs(C, reach)
        if not len(ii):
            break
        d = C[ii] - C[jj]
        dist = np.hypot(d[:, 0], d[:, 1])
        zero = dist == 0
        if zero.any():
            ang = rng.random(int(zero.sum())) * 2 * math.pi
            d[zero] = np.stack([np.cos(ang), np.sin(ang)], 1)
            dist[zero] = 1.0
        push = (reach[ii] + reach[jj] - dist) * 1.01 / dist
        share_i = np.where(mov[ii], np.where(mov[jj], 0.5, 1.0), 0.0)
        share_j = np.where(mov[jj], np.where(mov[ii], 0.5, 1.0), 0.0)
        step = d * push[:, None]
        D = np.zeros((n, 2))
        for k in (0, 1):
            D[:, k] = (np.bincount(ii, step[:, k] * share_i, n) - np.bincount(jj, step[:, k] * share_j, n))
        cnt = np.bincount(ii, minlength=n) + np.bincount(jj, minlength=n)
        C = C + D / np.maximum(1.0, np.sqrt(cnt))[:, None]
        yield C - half


def _tree_positions(snap, roots, horizontal=False, gap=None):
    """Tidy tree drawing of a BFS spanning tree per component: leaves get
    consecutive slots, parents sit over the middle of their children, depth
    gives the level; components side by side."""
    n = snap.n
    P = snap.pos.copy()
    if n == 0:
        return P
    indptr, ind = snap.csr
    size = snap.size.max(1)
    unit = float(gap) if gap else max(30.0, float(np.median(size)) * 2.5)
    parent = np.full(n, -1)
    depth = np.zeros(n, int)
    seen = np.zeros(n, bool)
    children = [[] for _ in range(n)]
    order_roots = []
    comps = snap.components
    root_of = {}
    for r in roots:
        if r is not None:
            root_of[r] = True
    for comp in comps:
        cand = [v for v in comp if v in root_of]
        r = cand[0] if cand else max(comp, key=lambda v: (snap.degree[v], -v))
        order_roots.append(r)
        seen[r] = True
        q = deque([r])
        while q:
            u = q.popleft()
            for v in ind[indptr[u]:indptr[u + 1]].tolist():
                if not seen[v]:
                    seen[v] = True
                    parent[v] = u
                    depth[v] = depth[u] + 1
                    children[u].append(v)
                    q.append(v)
    slot = np.zeros(n)
    nxt = [0.0]

    def place(r):
        stack = [(r, False)]
        while stack:
            u, done = stack.pop()
            if done:
                ch = children[u]
                slot[u] = (slot[ch[0]] + slot[ch[-1]]) / 2 if ch else nxt[0]
                if not ch:
                    nxt[0] += 1
                continue
            stack.append((u, True))
            for v in reversed(children[u]):
                stack.append((v, False))

    for r in order_roots:
        place(r)
        nxt[0] += 1          # a gap between components
    a = slot * unit
    b = depth * unit * 1.6
    C = np.stack([b, a], 1) if horizontal else np.stack([a, b], 1)
    return C - snap.size / 2


def _label_boxes(snap):
    """Half-extents and centre offsets of node + visible label rectangles."""
    w, h = snap.size[:, 0].copy(), snap.size[:, 1].copy()
    off = np.zeros((snap.n, 2))
    for i, nd in enumerate(snap.nodes):
        v = nd._vals
        lab = v.get("label")
        if lab is None:
            lab = nd._name
        if v.get("labelvisible") and lab:
            lw = 5.8 * len(str(lab)) + 2       # BitmapText at 10 world units, about 0.58 em per char
            off[i, 0] = lw / 2                 # the box grows to the right of the node
            w[i] += lw
            h[i] = max(h[i], 12.0)
    return np.stack([w / 2, h / 2], 1), off


def _label_adjust_gen(snap, rng, margin=2.0, max_iter=600):
    """Gephi's Label Adjust: push nodes apart until node+label rectangles don't
    overlap (minimum-overlap axis), fixed nodes stay put."""
    n = snap.n
    if n < 2:
        return
    half, off = _label_boxes(snap)
    half = half + margin / 2
    mov = ~snap.fixed
    C = _jitter_coincident(snap.pos + snap.size / 2, rng, 1.0, mov)
    reach = np.hypot(half[:, 0], half[:, 1])
    for _ in range(max_iter):
        B = C + off
        ii, jj = _close_pairs(B, reach)
        if not len(ii):
            break
        d = B[ii] - B[jj]
        ox = half[ii, 0] + half[jj, 0] - np.abs(d[:, 0])
        oy = half[ii, 1] + half[jj, 1] - np.abs(d[:, 1])
        hit = (ox > 0) & (oy > 0)
        if not hit.any():
            break
        ii, jj, d, ox, oy = ii[hit], jj[hit], d[hit], ox[hit], oy[hit]
        sx = np.where(d[:, 0] == 0, rng.choice([-1.0, 1.0], len(d)), np.sign(d[:, 0]))
        sy = np.where(d[:, 1] == 0, rng.choice([-1.0, 1.0], len(d)), np.sign(d[:, 1]))
        along_x = ox < oy
        step = np.zeros((len(d), 2))
        step[along_x, 0] = sx[along_x] * ox[along_x] * 0.51
        step[~along_x, 1] = sy[~along_x] * oy[~along_x] * 0.51
        share_i = np.where(mov[ii], np.where(mov[jj], 1.0, 2.0), 0.0)
        share_j = np.where(mov[jj], np.where(mov[ii], 1.0, 2.0), 0.0)
        D = np.zeros((n, 2))
        for k in (0, 1):
            D[:, k] = np.bincount(ii, step[:, k] * share_i, n) - np.bincount(jj, step[:, k] * share_j, n)
        cnt = np.bincount(ii, minlength=n) + np.bincount(jj, minlength=n)
        C = C + D / np.maximum(1.0, np.sqrt(cnt))[:, None]
        yield C - snap.size / 2


def install(session):
    lay = _Layouts(session)
    g = session.graph

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def rng(seed=None):
        return np.random.default_rng(seed)

    @cmd
    def centerAfterLayout(state):
        """centerAfterLayout(state): whether the view re-centres after each layout
        (default true). Disable it to control the view yourself."""
        lay.center_after = bool(state)

    @cmd
    def randomLayout(width=None, height=None):
        """randomLayout() places nodes at random in a 1000 x 1000 area;
        randomLayout(width, height) uses a width x height area."""
        if (width is None) != (height is None):
            raise TypeError("randomLayout() or randomLayout(width, height)")
        w, h = (1000, 1000) if width is None else (width, height)
        s = lay.snap()
        lay.apply(s, _random_positions(s, w, h, rng()))

    @cmd
    def circleLayout(field=None, center=None, x=None, y=None):
        """circleLayout() places all nodes evenly on a circle (radius 450 around 500,500).

        circleLayout(field, centerNode) puts centerNode at (500, 500) and its
        neighbours on a circle around it, ordered by `field`, at a radius
        proportional to `field` (a node field of the neighbours, or an edge
        field of the connecting edges). Other nodes are left alone.
        circleLayout(field, centerNode, x, y) uses (x, y) as the centre."""
        if field is None and center is None and x is None and y is None:
            s = lay.snap()
            lay.apply(s, _circle_positions(s))
            # dragging a node now slides it around the ring (declarative dragging)
            session.view.drag["ring"] = {"cx": BOX / 2, "cy": BOX / 2, "r": 0.45 * BOX,
                                         "ids": [nd._id for nd in s.nodes]}
            session.view.changed()
            return
        if field is None or center is None or ((x is None) != (y is None)):
            raise TypeError("circleLayout(), circleLayout(field, centerNode) or "
                            "circleLayout(field, centerNode, x, y)")
        f = _field_arg(g, field)
        c = _node_arg(g, center, "center node")
        ox, oy = (500.0, 500.0) if x is None else (float(x), float(y))
        s = lay.snap()
        lay.apply(s, _circular_constrained(s, g, c, f, ox, oy))

    @cmd
    def radialLayout(center, edges=None):
        """radialLayout(centerNode) lays the graph out as a radial tree around
        centerNode (placed at 0,0), following a breadth-first spanning tree
        (Eades' radial drawing). Nodes not reachable from the centre stay put.
        radialLayout(centerNode, edges) restricts the tree to the given edges."""
        c = _node_arg(g, center, "center node")
        valid = None
        if edges is not None:
            valid = {e._id for e in elements_of(edges) if isinstance(e, Edge)}
        s = lay.snap()
        lay.apply(s, _radial_positions(s, g, c, valid))

    @cmd
    def frLayout(width=None, height=None):
        """frLayout() runs Fruchterman-Rheingold (as in Pajek) starting from the
        current positions and fits the result into a 1000 x 1000 grid with cells
        the size of the largest node; frLayout(width, height) uses that area."""
        if (width is None) != (height is None):
            raise TypeError("frLayout() or frLayout(width, height)")
        w, h = (1000, 1000) if width is None else (width, height)
        s = lay.snap()
        lay.run(s, _fr_gen(s, w, h, rng()))

    @cmd
    def jfrLayout():
        """jfrLayout() runs the JUNG Fruchterman-Rheingold layout (random start in
        a 1000 x 1000 area, up to 700 cooling iterations)."""
        s = lay.snap()
        lay.run(s, _jfr_gen(s, rng()))

    @cmd
    def kkLayout(width=None, height=None):
        """kkLayout() runs Kamada-Kawai on each connected component, starting from
        a circle, then fits the result into 1000 x 1000; kkLayout(width, height)
        uses that area instead."""
        if (width is None) != (height is None):
            raise TypeError("kkLayout() or kkLayout(width, height)")
        w, h = (1000, 1000) if width is None else (width, height)
        s = lay.snap()
        lay.run(s, _guess_kk_gen(s, w, h))

    def _hop_matrix(s):
        indptr, ind = s.csr
        return _bfs_hops(indptr, ind, s.n, np.arange(s.n))

    @cmd
    def jkkLayout1():
        """jkkLayout1() runs the JUNG Kamada-Kawai layout: unweighted graph
        distances, random start, 2000 iterations each moving the worst-placed
        node."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        lay.run(s, _jung_kk_gen(s, rng(), _hop_matrix(s), 2000))

    @cmd
    def jkkLayout2():
        """jkkLayout2() runs the JUNG Kamada-Kawai layout with integer distances
        (same algorithm as jkkLayout1)."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        lay.run(s, _jung_kk_gen(s, rng(), _hop_matrix(s), 2000))

    @cmd
    def weightedKKLayout():
        """weightedKKLayout() runs the JUNG Kamada-Kawai layout using shortest
        paths where each edge's `weight` is its length."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        keep = s.src != s.dst
        w = np.abs(s.weight[keep])
        if len(w) and w.max() == w.min() and w[0] > 0:
            H = _hop_matrix(s).astype(np.float32)
            D = np.where(H >= 0, H * np.float32(w[0]), np.inf).astype(np.float32)
        else:
            D = _dijkstra_all(s, list(range(s.n))).astype(np.float32)
        lay.run(s, _jung_kk_gen(s, rng(), D, 2000))

    @cmd
    def springLayout(max=None):
        """springLayout() runs the GUESS spring layout from the current positions
        until it settles or for 1000 iterations (fewer on graphs over 1000
        nodes: 1000 * 1000 / nodes, at least 100); springLayout(n) runs exactly
        n iterations. Stop it early with the Stop button."""
        s = lay.snap()
        n = _iters(max, _scaled(1000, s.n))
        lay.run(s, _spring_gen(s, n, rng(), tol=0.05 if max is None else -1))

    @cmd
    def jSpringLayout(max=None):
        """jSpringLayout() runs the JUNG spring layout from random positions until
        it settles or for 500 iterations (fewer on graphs over 1000 nodes);
        jSpringLayout(n) runs exactly n iterations."""
        s = lay.snap()
        n = _iters(max, _scaled(500, s.n))
        lay.run(s, _jspring_gen(s, n, rng(), tol=0.05 if max is None else -1))

    @cmd
    def weightedSpringLayout(minLength, maxLength, max=None):
        """weightedSpringLayout(minLength, maxLength[, iterations]) is springLayout
        with each edge's natural length mapped linearly from its `weight`
        (lowest weight -> minLength, highest -> maxLength). Iterations as for
        springLayout."""
        s = lay.snap()
        n = _iters(max, _scaled(1000, s.n))
        w = s.weight
        lo, hi = float(minLength), float(maxLength)
        if len(w) and w.max() > w.min():
            lengths = lo + (w - w.min()) / (w.max() - w.min()) * (hi - lo)
        else:
            lengths = np.full(len(w), lo)
        lay.run(s, _spring_gen(s, n, rng(), lengths, tol=0.05 if max is None else -1))

    @cmd
    def gemLayout(seed=None):
        """gemLayout() runs the GEM force-directed layout (Frick et al.);
        gemLayout(seed) seeds the random generator for a repeatable layout."""
        s = lay.snap()
        lay.run(s, _gem_gen(s, rng(None if seed is None else int(seed))))

    @cmd
    def isomLayout(max=None):
        """isomLayout() runs the JUNG ISOM (self-organising map) layout for 2000
        epochs; isomLayout(n) runs n epochs."""
        s = lay.snap()
        lay.run(s, _isom_gen(s, rng(), _iters(max, 2000)))

    @cmd
    def physicsLayout(max=None):
        """physicsLayout() runs the graphopt physics layout (charged nodes, springs)
        for 500 steps from the current positions (fewer on graphs over 1000
        nodes); physicsLayout(n) runs n steps."""
        s = lay.snap()
        lay.run(s, _physics_gen(s, _iters(max, _scaled(500, s.n)), rng()))

    @cmd
    def mdsLayout():
        """mdsLayout() places nodes by classical multidimensional scaling of the
        edge weights (an edge's weight is the distance between its endpoints,
        every other pair is at distance 1). Nodes without edges are not moved."""
        s = lay.snap()
        P, flat = _mds_positions(s, rng(0))
        if flat:
            print("mdsLayout: all edge weights are equal, using graph distances instead")
            P = _pivot_mds(s, rng(0))
        lay.apply(s, P)

    @cmd
    def sugiyamaLayout(bends=False):
        """sugiyamaLayout() draws the graph in layers (Sugiyama): edges are made
        acyclic, nodes put on levels so every edge points down, crossings reduced
        by barycentres, on a 250 x 150 grid. sugiyamaLayout(true) also routes
        long edges through dummy positions."""
        s = lay.snap()
        routes = {} if bends else None
        pos = _sugiyama_positions(s, bool(bends), routes)
        s.write(pos)
        if routes:
            # map acyclic arcs back to edges (an arc may run against the edge)
            for e, a, b in zip(s.edges, s.src.tolist(), s.dst.tolist()):
                if (a, b) in routes:
                    lay.graph.set_bends(e, routes[(a, b)])
                elif (b, a) in routes:
                    lay.graph.set_bends(e, routes[(b, a)][::-1])
        lay.finish()

    @cmd
    def sugiyamaLayout2():
        """sugiyamaLayout2() is a simpler layered layout: levels 200 apart, each
        node given horizontal room in proportion to its children."""
        s = lay.snap()
        lay.apply(s, _sugiyama2_positions(s))

    @cmd
    def dagLayout():
        """dagLayout() lays out a directed acyclic graph with a spring layout,
        keeping each node on a horizontal line for its level (sources at the
        top), for 500 iterations (fewer on graphs over 1000 nodes). Cycles are
        broken first."""
        s = lay.snap()
        lay.run(s, _dag_gen(s, rng(), _scaled(500, s.n)))

    @cmd
    def forceAtlas2Layout(iterations=None, scaling=None, gravity=1.0, strongGravity=False,
                          linLog=False, dissuadeHubs=False, preventOverlap=False,
                          edgeWeightInfluence=1.0):
        """forceAtlas2Layout() runs Gephi's ForceAtlas2 from the current positions
        (animated; Stop ends it early). Options, by keyword:
          iterations           steps to run (default 500, fewer on big graphs)
          scaling              repulsion strength (default 2, or 10 under 100 nodes)
          gravity              pull toward the centre (default 1)
          strongGravity=true   gravity grows with distance (keeps components close)
          linLog=true          LinLog mode: tighter, more separated clusters
          dissuadeHubs=true    pushes hubs to the periphery (authorities central)
          preventOverlap=true  keep node discs apart (best run after a first pass)
          edgeWeightInfluence  0 ignores weights, 1 uses them, >1 exaggerates
        E.g. forceAtlas2Layout(linLog=true, preventOverlap=true)"""
        s = lay.snap()
        js = _js_fa2() if s.n >= _JS_FA2_MIN else None
        if js:
            # Barnes-Hut in JS is ~20x faster than the numpy version at this size
            k = _iters(iterations, _scaled(500, s.n) * 3)
            lay.run(s, _fa2_js_gen(s, k, rng(0), scaling, float(gravity), bool(strongGravity), bool(linLog),
                                   bool(dissuadeHubs), bool(preventOverlap), float(edgeWeightInfluence), engine=js))
            return
        k = _iters(iterations, _scaled(500, s.n))
        lay.run(s, _fa2_gen(s, k, rng(0), scaling, float(gravity), bool(strongGravity), bool(linLog),
                            bool(dissuadeHubs), bool(preventOverlap), float(edgeWeightInfluence)))

    @cmd
    def noverlapLayout(margin=5, ratio=1.2):
        """noverlapLayout() nudges nodes apart until none overlap (Gephi's Noverlap):
        each node is treated as a disc of ratio x its size plus margin."""
        s = lay.snap()
        lay.run(s, _noverlap_gen(s, rng(0), float(margin), float(ratio)))

    @cmd
    def treeLayout(root=None, horizontal=False, spacing=None):
        """treeLayout() draws each connected component as a tidy tree (a
        breadth-first spanning tree from its best-connected node, or from root),
        parents centred over their children; horizontal=true grows it left to
        right; spacing sets the distance between neighbouring leaves."""
        s = lay.snap()
        roots = []
        if root is not None:
            for r in (root if isinstance(root, (list, tuple)) or hasattr(root, "__iter__") and not isinstance(root, (str, Node)) else [root]):
                nd = _node_arg(g, r, "root")
                roots.append(s.index[nd._id])
        lay.apply(s, _tree_positions(s, roots, bool(horizontal), spacing))

    @cmd
    def labelAdjustLayout(margin=2):
        """labelAdjustLayout() moves nodes just enough that nodes and their
        visible labels stop overlapping (Gephi's Label Adjust)."""
        s = lay.snap()
        lay.run(s, _label_adjust_gen(s, rng(0), float(margin)))

    @cmd
    def ringMove(node, index):
        """ringMove(node, k) moves a node to position k around the circle made by
        circleLayout() and re-spaces the ring (what dragging a node around the
        circle does)."""
        ring = session.view.drag.get("ring")
        if not ring:
            raise GuessError("ringMove works after circleLayout()")
        nd = _node_arg(g, node)
        ids = [i for i in ring["ids"] if i != nd._id and g.node_by_id(i) is not None]
        k = max(0, min(int(index), len(ids)))
        ids.insert(k, nd._id)
        n = len(ids)
        for j, i in enumerate(ids):
            a = 2 * math.pi * j / n
            m = g.node_by_id(i)
            m.x = ring["cx"] + ring["r"] * math.cos(a)
            m.y = ring["cy"] + ring["r"] * math.sin(a)
        ring["ids"] = ids
        session.view.changed()

    @cmd
    def scatterLayout(xfield, yfield, width=1000, height=1000):
        """scatterLayout(xfield, yfield) places nodes by two numeric fields (x to the
        right, y upwards) in a width x height area. Dragging a node then edits
        those two values."""
        fx, fy = _field_arg(g, xfield), _field_arg(g, yfield)
        s = lay.snap()
        P = s.pos.copy()
        vx = np.array([_num(fx.get(nd), np.nan) for nd in s.nodes])
        vy = np.array([_num(fy.get(nd), np.nan) for nd in s.nodes])
        ok = np.isfinite(vx) & np.isfinite(vy)
        if not ok.any():
            raise GuessError("no nodes have numbers in both fields")
        x0, x1 = float(vx[ok].min()), float(vx[ok].max())
        y0, y1 = float(vy[ok].min()), float(vy[ok].max())
        sx = float(width) / ((x1 - x0) or 1)
        sy = float(height) / ((y1 - y0) or 1)
        P[ok, 0] = (vx[ok] - x0) * sx
        P[ok, 1] = float(height) - (vy[ok] - y0) * sy
        lay.apply(s, P)
        session.view.drag["axes"] = {"x": fx.name, "y": fy.name, "x0": x0, "sx": sx, "y0": y0, "sy": sy,
                                     "h": float(height), "xint": _is_int(fx), "yint": _is_int(fy),
                                     "xedit": not fx.readonly and fx.compute is None,
                                     "yedit": not fy.readonly and fy.compute is None}
        session.view.changed()

    @cmd
    def hiveLayout(axis=None, position=None, scale="rank", axes=None, inner=60, length=440, curved=True):
        """hiveLayout(axis, position) draws a hive plot (Krzywinski et al.): one
        radial axis per value of the node field `axis` (the most common values,
        at most `axes` of them, the rest merged into "other"), each node placed
        along its axis by the numeric field `position` (default totaldegree),
        and edges drawn as curves between axes. scale is "rank" (default; evenly
        spread), "linear" or "log". Without `axis`: for directed graphs the
        classic source / hub / sink axes (only outgoing, both, only incoming
        edges), otherwise leaves / connectors / hubs by degree. The axes are drawn
        with their labels; any later layout removes them.
        E.g. hiveLayout(dept, pagerank) or hiveLayout(modularity_class, axes=5)"""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        nodes = s.nodes
        # 1. which axis each node is on
        if axis is not None:
            f = _field_arg(g, axis)
            vals = [f.get(nd) for nd in nodes]
            counts = {}
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
            limit = int(axes) if axes else 6
            order = sorted(counts, key=lambda v: (-counts[v], str(v)))
            keep = order[:limit] if len(order) <= limit else order[:limit - 1]
            names = [f"{f.name} = {v}" for v in keep] + (["other"] if len(order) > len(keep) else [])
            idx = {v: k for k, v in enumerate(keep)}
            ax = np.array([idx.get(v, len(keep)) for v in vals])
        else:
            outd = np.bincount(s.src[s.directed], minlength=s.n)
            ind = np.bincount(s.dst[s.directed], minlength=s.n)
            if s.directed.any():
                names = ["sources", "hubs", "sinks"]
                ax = np.where((outd > 0) & (ind == 0), 0, np.where((ind > 0) & (outd == 0), 2, 1))
            else:
                deg = s.degree
                cut = np.quantile(deg, 0.9) if s.n > 10 else deg.max()
                names = ["leaves", "connectors", "hubs"]
                ax = np.where(deg <= 1, 0, np.where(deg >= max(cut, 2), 2, 1))
        k = len(names)
        # 2. where along the axis
        if position is None:
            pv = np.array([float(len(nd._inc)) for nd in nodes])
            pname = "totaldegree"
        else:
            pf = _field_arg(g, position)
            pv = np.array([_num(pf.get(nd), np.nan) for nd in nodes])
            pv = np.where(np.isfinite(pv), pv, np.nanmin(pv) if np.isfinite(pv).any() else 0.0)
            pname = pf.name
        scale = str(scale).lower()
        t = np.zeros(s.n)
        for a in range(k):
            m = ax == a
            if not m.any():
                continue
            v = pv[m]
            if scale == "rank":
                # ties share a rank; spread evenly along the axis
                order = np.argsort(np.argsort(v, kind="stable"), kind="stable")
                t[m] = order / max(m.sum() - 1, 1)
            else:
                if scale == "log":
                    v = np.log1p(v - v.min())
                elif scale != "linear":
                    raise GuessError('scale is "rank", "linear" or "log"')
                lo, hi = v.min(), v.max()
                t[m] = (v - lo) / (hi - lo) if hi > lo else 0.5
        ang = -math.pi / 2 + 2 * math.pi * np.arange(k) / k
        r = float(inner) + t * float(length)
        cx = cy = BOX / 2
        C = np.stack([cx + r * np.cos(ang[ax]), cy + r * np.sin(ang[ax])], 1)
        lay.apply(s, C - s.size / 2)
        # 3. edges as curves between axes (control points on the bisector)
        if curved:
            span = 2 * math.pi / k
            for e in s.edges:
                i, j = s.index[e._n1._id], s.index[e._n2._id]
                if i == j:
                    continue
                ai, aj = ang[ax[i]], ang[ax[j]]
                if ax[i] == ax[j]:
                    mid = ai + span * 0.12         # same axis: a narrow loop out to the side
                else:
                    d = (aj - ai + math.pi) % (2 * math.pi) - math.pi
                    mid = ai + d / 2
                p0, p3 = C[i], C[j]
                p1 = (cx + r[i] * math.cos(mid), cy + r[i] * math.sin(mid))
                p2 = (cx + r[j] * math.cos(mid), cy + r[j] * math.sin(mid))
                pts = []
                for q in range(1, 14):
                    u = q / 14
                    b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
                    pts.append((b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                                b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]))
                g.set_bends(e, pts)
        # 4. the axes, labelled
        session.view.guides = [
            {"x1": cx + inner * 0.6 * math.cos(a), "y1": cy + inner * 0.6 * math.sin(a),
             "x2": cx + (inner + length + 25) * math.cos(a), "y2": cy + (inner + length + 25) * math.sin(a),
             "label": f"{name} ({int((ax == q).sum())})"}
            for q, (a, name) in enumerate(zip(ang, names))]
        session.view.guides_note = f"position: {pname} ({scale})"
        session.view.changed()
        session.flush()

    @cmd
    def rotateLayout(degrees=90):
        """rotateLayout(degrees) turns the layout clockwise about its centre."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        C = s.pos + s.size / 2
        mid = (C.min(0) + C.max(0)) / 2
        t = math.radians(float(degrees))
        R = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        lay.apply(s, (C - mid) @ R.T + mid - s.size / 2)

    @cmd
    def mirrorLayout(horizontal=True):
        """mirrorLayout() flips the layout left-right; mirrorLayout(false) flips it
        upside down."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        C = s.pos + s.size / 2
        k = 0 if horizontal else 1
        lo, hi = C[:, k].min(), C[:, k].max()
        C[:, k] = lo + hi - C[:, k]
        lay.apply(s, C - s.size / 2)

    @cmd
    def binPackLayout(rescale=True):
        """binPackLayout() packs the connected components next to each other,
        first rescaling them to similar densities; binPackLayout(false) packs
        them without rescaling."""
        s = lay.snap()
        lay.apply(s, _binpack_positions(s, bool(rescale)))

    @cmd
    def rescaleLayout(*d):
        """rescaleLayout(percent) scales the layout by percent (0.5 = half size)
        about its top-left corner; rescaleLayout(xpercent, ypercent) scales each
        axis separately; rescaleLayout(width, height) with integers fits the
        layout into a width x height box at the origin."""
        s = lay.snap()
        if s.n < 2:
            return lay.finish()
        P = s.pos
        lo = P.min(0)
        if len(d) == 1:
            fx = fy = float(d[0])
        elif len(d) == 2:
            if all(isinstance(v, int) and not isinstance(v, bool) for v in d):
                lay.apply(s, _bbox_rescale(P, d[0], d[1]))
                return
            fx, fy = float(d[0]), float(d[1])
        else:
            raise TypeError("rescaleLayout(percent), rescaleLayout(xpercent, ypercent) "
                            "or rescaleLayout(width, height)")
        lay.apply(s, lo + (P - lo) * (fx, fy))

    @cmd
    def translateLayout(newX, newY):
        """translateLayout(dx, dy) moves every node by (dx, dy)."""
        s = lay.snap()
        lay.apply(s, s.pos + (float(newX), float(newY)))

    @cmd
    def moveLayout(newX, newY):
        """moveLayout(x, y) moves the layout so its top-left corner is at (x, y)."""
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        lay.apply(s, s.pos - s.pos.min(0) + (float(newX), float(newY)))

    return lay
