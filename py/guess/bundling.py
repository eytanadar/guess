"""Edge bundling: MINGLE and force-directed edge bundling (FDEB).

Both take edges as an (m, 4) array of (x1, y1, x2, y2) and return, for each
edge, a list of points from the first end to the second (ends included).

MINGLE (Gansner, Hu, North, Scheidegger: Multilevel Agglomerative Edge
Bundling for Visualizing Large Graphs, PacificVis 2011). Ported from the
JavaScript implementation by Nicolas Garcia Belmonte,
https://github.com/philogb/mingle (MIT licence):

    Copyright (c) 2013 Twitter - Author: Nicolas Garcia Belmonte
    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to permit
    persons to whom the Software is furnished to do so, subject to the
    following conditions: The above copyright notice and this permission
    notice shall be included in all copies or substantial portions of the
    Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

FDEB (Holten, van Wijk: Force-Directed Edge Bundling for Graph
Visualization, EuroVis 2009), written from the paper.
"""
import math

import numpy as np

PHI = (1 + math.sqrt(5)) / 2


# ---------------------------------------------------------------------------
# MINGLE
# ---------------------------------------------------------------------------

class _MNode:
    """An edge, or a bundle of them coalesced into one edge (s -> e)."""
    __slots__ = ("s", "e", "parents", "leaf", "inner", "up")

    def __init__(self, s, e, parents=None, leaf=None):
        self.s, self.e = np.asarray(s, float), np.asarray(e, float)
        self.parents = parents       # the nodes this one bundles (None for an edge)
        self.leaf = leaf             # index of the original edge
        self.up = None               # the bundle node this one went into
        # ink below this node (from its own ends to its parents' ends, recursively)
        self.inner = 0.0 if not parents else sum(
            float(np.hypot(*(self.s - p.s)) + np.hypot(*(self.e - p.e))) + p.inner for p in parents)

    def ink(self):
        return float(np.hypot(*(self.s - self.e))) + self.inner


class _Group:
    """Nodes bundled together this round, their total ink and meeting points."""
    __slots__ = ("members", "ink", "m1", "m2")

    def __init__(self, members, ink, m1=None, m2=None):
        self.members, self.ink, self.m1, self.m2 = members, ink, m1, m2


def _bundle_cost(members, angle_strength):
    """Best meeting points m1, m2 for a set of nodes bundled together, by
    golden-section search along the line between their start and end
    centroids. Returns (ink, m1, m2)."""
    S = np.array([m.s for m in members])
    E = np.array([m.e for m in members])
    inner = sum(m.inner for m in members)
    top, bottom = S.mean(0), E.mean(0)

    def evaluate(x):
        x /= 2
        m1 = top + (bottom - top) * x
        m2 = top + (bottom - top) * (1 - x)
        seg = float(np.hypot(*(m1 - m2)))
        ink = seg + float(np.hypot(*(S - m1).T).sum() + np.hypot(*(E - m2).T).sum()) + inner
        # the sharpest turn an edge makes into or out of the bundle
        if seg > 1e-12:
            d = (m1 - m2) / seg
            with np.errstate(invalid="ignore", divide="ignore"):
                a = np.hypot(*(S - m1).T)
                c1 = np.where(a > 1e-12, ((S - m1) @ d) / np.where(a > 1e-12, a, 1), 1.0)
                b = np.hypot(*(E - m2).T)
                c2 = np.where(b > 1e-12, ((E - m2) @ -d) / np.where(b > 1e-12, b, 1), 1.0)
            alpha = float(np.arccos(np.clip(np.concatenate([c1, c2]), -1, 1)).max())
        else:
            alpha = 0.0
        return ink * (1 + math.sin(alpha) / angle_strength), ink, m1, m2

    # golden-section search on [0, 1] (as the original, bracket (0, 1, 0.72))
    a, b, c, tau = 0.0, 1.0, 0.72, 0.1
    resphi = 2 - PHI
    fb = evaluate(b)[0]
    for _ in range(40):
        x = b + resphi * (c - b) if c - b > b - a else b - resphi * (b - a)
        if abs(c - a) < tau * (abs(b) + abs(x)):
            break
        fx = evaluate(x)[0]
        if fx < fb:
            if c - b > b - a:
                a, b, fb = b, x, fx
            else:
                c, b, fb = b, x, fx
        elif c - b > b - a:
            c = x
        else:
            a = x
    _cost, ink, m1, m2 = evaluate((a + c) / 2)
    return ink, m1, m2


def _knn(coords, k):
    """Indices of each row's k nearest other rows (4D Euclidean), in blocks."""
    n = len(coords)
    k = min(k, n - 1)
    out = np.empty((n, k), np.int64)
    sq = (coords ** 2).sum(1)
    for i0 in range(0, n, 512):
        blk = coords[i0:i0 + 512]
        d = sq[i0:i0 + 512, None] + sq[None, :] - 2 * blk @ coords.T
        d[np.arange(len(blk)), np.arange(i0, i0 + len(blk))] = np.inf
        idx = np.argpartition(d, k - 1, axis=1)[:, :k] if k < n - 1 else np.argsort(d, 1)[:, :k]
        out[i0:i0 + 512] = idx
    return out


def mingle(edges, neighbors=10, angle_strength=1.2, max_levels=30):
    """MINGLE bundling. Returns a polyline (list of (x, y)) per edge."""
    edges = np.asarray(edges, float)
    m = len(edges)
    if m == 0:
        return []
    nodes = [_MNode(edges[i, :2], edges[i, 2:], leaf=i) for i in range(m)]
    if m > 1:
        nb = _knn(edges, neighbors)
        adj = {id(nodes[i]): {id(nodes[j]) for j in nb[i]} for i in range(m)}
        for i in range(m):                       # the proximity graph is undirected
            for j in nb[i]:
                adj[id(nodes[j])].add(id(nodes[i]))
        by_id = {id(n): n for n in nodes}
        for _level in range(max_levels):
            group = {}                                   # id(node) -> its _Group
            for n in nodes:
                group[id(n)] = _Group([n], n.ink())
            assigned = set()
            gain_total = 0.0
            for u in nodes:
                if id(u) in assigned:
                    continue
                gu = group[id(u)]
                best = None
                for vid in adj.get(id(u), ()):
                    gv = group[vid]
                    if gv is gu:
                        continue
                    combined = gu.members + gv.members
                    ink_c, m1, m2 = _bundle_cost(combined, angle_strength)
                    gain = gu.ink + gv.ink - ink_c
                    if best is None or gain > best[0]:
                        best = (gain, _Group(combined, ink_c, m1, m2))
                assigned.add(id(u))
                if best is not None and best[0] > 1e-9:
                    gain, merged = best
                    for x in merged.members:
                        group[id(x)] = merged
                        assigned.add(id(x))
                    gain_total += gain
            if gain_total <= 1e-9:
                break
            # coalesce each group into one node; it inherits its members' neighbours
            new_nodes, seen = [], set()
            for n in nodes:
                grp = group[id(n)]
                if id(grp) in seen:
                    continue
                seen.add(id(grp))
                g = grp.members
                if len(g) == 1:
                    new_nodes.append(n)
                    continue
                b = _MNode(grp.m1, grp.m2, parents=g)
                for x in g:
                    x.up = b
                ids = {id(x) for x in g}
                adj[id(b)] = {y for x in g for y in adj.pop(id(x), ()) if y not in ids}
                by_id[id(b)] = b
                new_nodes.append(b)
            # neighbours now point at the bundles that replaced them
            for n in new_nodes:
                fixed = set()
                for y in adj.get(id(n), ()):
                    t = by_id[y]
                    while t.up is not None:
                        t = t.up
                    if t is not n:
                        fixed.add(id(t))
                adj[id(n)] = fixed
            nodes = new_nodes
            if len(nodes) <= 1:
                break
    # each edge runs: its start, its bundles' starts outward, then back in to its end
    leaves = [None] * m
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if n.parents:
            stack.extend(n.parents)
        else:
            leaves[n.leaf] = n
    out = []
    for i in range(m):
        chain = []
        n = leaves[i].up
        while n is not None:
            chain.append(n)
            n = n.up
        starts = [tuple(x.s) for x in chain]
        ends = [tuple(x.e) for x in reversed(chain)]
        out.append([tuple(edges[i, :2])] + starts + ends + [tuple(edges[i, 2:])])
    return out


# ---------------------------------------------------------------------------
# FDEB
# ---------------------------------------------------------------------------

def _compatibility(edges, threshold, max_pairs_per_edge):
    """Compatible edge pairs (i, j, flip) by Holten and van Wijk's four
    measures (angle, scale, position, visibility), each edge keeping its most
    compatible partners. flip: the edges run in opposite directions, so their
    subdivision points pair up in reverse."""
    P0, P1 = edges[:, :2], edges[:, 2:]
    vec = P1 - P0
    length = np.hypot(vec[:, 0], vec[:, 1])
    mid = (P0 + P1) / 2
    unit = vec / np.where(length > 0, length, 1)[:, None]
    m = len(edges)
    I, J, F = [], [], []
    for i0 in range(0, m, 256):
        i = np.arange(i0, min(m, i0 + 256))
        cos = unit[i] @ unit.T
        ca = np.abs(cos)
        la = (length[i, None] + length[None, :]) / 2
        lmin = np.minimum(length[i, None], length[None, :])
        lmax = np.maximum(length[i, None], length[None, :])
        with np.errstate(divide="ignore", invalid="ignore"):
            cs = 2 / (la / np.where(lmin > 0, lmin, np.inf) + lmax / np.where(la > 0, la, 1))
            dm = np.hypot(mid[i, None, 0] - mid[None, :, 0], mid[i, None, 1] - mid[None, :, 1])
            cp = la / (la + dm)

            def vis(a_idx, b_all, a_rows):
                # visibility of the b edges seen from the a edges (projections onto a's line)
                a0, a1 = P0[a_idx][:, None, :], P1[a_idx][:, None, :]
                d = a1 - a0
                dd = (d ** 2).sum(-1)
                dd = np.where(dd > 0, dd, 1)
                t0 = (((P0[None, :, :] - a0) * d).sum(-1)) / dd
                t1 = (((P1[None, :, :] - a0) * d).sum(-1)) / dd
                q0 = a0 + t0[..., None] * d
                q1 = a0 + t1[..., None] * d
                qm = (q0 + q1) / 2
                span = np.hypot(*(q1 - q0).transpose(2, 0, 1))
                gap = np.hypot(*(mid[a_rows][:, None, :] - qm).transpose(2, 0, 1))
                return np.maximum(0, 1 - 2 * gap / np.where(span > 0, span, np.inf))
            v1 = vis(i, None, i)
            # the other direction: project these edges onto every other edge's line
            d = P1 - P0
            dd = np.where((d ** 2).sum(-1) > 0, (d ** 2).sum(-1), 1)
            t0 = (((P0[i][:, None, :] - P0[None, :, :]) * d[None]).sum(-1)) / dd[None]
            t1 = (((P1[i][:, None, :] - P0[None, :, :]) * d[None]).sum(-1)) / dd[None]
            q0 = P0[None] + t0[..., None] * d[None]
            q1 = P0[None] + t1[..., None] * d[None]
            span = np.hypot(*(q1 - q0).transpose(2, 0, 1))
            gap = np.hypot(*(mid[None] - (q0 + q1) / 2).transpose(2, 0, 1))
            v2 = np.maximum(0, 1 - 2 * gap / np.where(span > 0, span, np.inf))
        c = np.nan_to_num(ca * cs * cp * np.minimum(v1, v2))
        c[np.arange(len(i)), i] = 0
        c[:, length == 0] = 0
        for r, row in enumerate(c):
            js = np.flatnonzero(row >= threshold)
            if len(js) > max_pairs_per_edge:
                js = js[np.argpartition(-row[js], max_pairs_per_edge - 1)[:max_pairs_per_edge]]
            I.extend([i[r]] * len(js))
            J.extend(js.tolist())
            F.extend((cos[r, js] < 0).tolist())
    return np.array(I, np.int64), np.array(J, np.int64), np.array(F, bool)


def fdeb(edges, stiffness=0.1, threshold=0.6, cycles=6, iterations=50, step=0.04,
         max_pairs_per_edge=40):
    """Force-directed edge bundling. Returns a polyline per edge.

    Each edge gets subdivision points joined by springs; compatible edges'
    corresponding points attract each other. Each cycle doubles the points,
    halves the step and shortens the iterations (by 2/3). Runs in a unit box,
    so the constants don't depend on the layout's scale."""
    edges = np.asarray(edges, float)
    m = len(edges)
    if m == 0:
        return []
    lo = np.array([edges[:, [0, 2]].min(), edges[:, [1, 3]].min()])
    scale = max(float(np.ptp(edges[:, [0, 2]])), float(np.ptp(edges[:, [1, 3]])), 1e-9)
    unit_edges = (edges - np.tile(lo, 2)) / scale
    P0, P1 = unit_edges[:, :2], unit_edges[:, 2:]
    length = np.hypot(*(P1 - P0).T)
    I, J, F = _compatibility(unit_edges, threshold, max_pairs_per_edge)
    P = 1
    pts = ((P0 + P1) / 2)[:, None, :]                       # (m, P, 2) interior points
    S, its = float(step), float(iterations)
    still = length == 0
    for cycle in range(int(cycles)):
        for _ in range(max(1, int(round(its)))):
            full = np.concatenate([P0[:, None, :], pts, P1[:, None, :]], axis=1)
            k = stiffness / (np.where(length > 0, length, 1) * (P + 1))
            spring = k[:, None, None] * (full[:, :-2] + full[:, 2:] - 2 * pts)
            elec = np.zeros_like(pts)
            for c0 in range(0, len(I), 20000):
                ii, jj, ff = I[c0:c0 + 20000], J[c0:c0 + 20000], F[c0:c0 + 20000]
                q = pts[jj]
                q = np.where(ff[:, None, None], q[:, ::-1], q)
                diff = q - pts[ii]
                dist = np.hypot(diff[..., 0], diff[..., 1])
                np.add.at(elec, ii, diff / np.where(dist > 1e-6, dist, np.inf)[..., None])
            move = S * (spring + elec / max_pairs_per_edge)
            pts = pts + move
            pts[still] = ((P0 + P1) / 2)[still][:, None, :]
        if cycle == int(cycles) - 1:
            break
        # double the subdivision points (resample each polyline evenly)
        full = np.concatenate([P0[:, None, :], pts, P1[:, None, :]], axis=1)
        P2 = 2 * P
        seg = np.hypot(*np.diff(full, axis=1).transpose(2, 0, 1))
        cum = np.concatenate([np.zeros((m, 1)), np.cumsum(seg, 1)], 1)
        total = np.where(cum[:, -1] > 0, cum[:, -1], 1)
        targets = np.linspace(0, 1, P2 + 2)[1:-1]
        new = np.empty((m, P2, 2))
        for e in range(m):
            t = targets * total[e]
            new[e, :, 0] = np.interp(t, cum[e], full[e, :, 0])
            new[e, :, 1] = np.interp(t, cum[e], full[e, :, 1])
        pts, P = new, P2
        S /= 2
        its *= 2 / 3
    full = np.concatenate([P0[:, None, :], pts, P1[:, None, :]], axis=1) * scale + lo
    return [[tuple(p) for p in full[e]] for e in range(m)]
