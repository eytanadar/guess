"""colaLayout: a numpy port of WebCola (Cola.js, Tim Dwyer et al.), with the
defaults of the cytoscape.js-cola wrapper.

Ported from WebCola/src:
  descent.ts            -> _Descent, _PseudoRandom (stress majorization by gradient
                           descent, 4th-order Runge-Kutta, projection step), vectorised
  vpsc.ts               -> _VPSC (variable placement with separation constraints)
  rectangle.ts          -> _overlap_constraints (sweep-line non-overlap constraints),
                           _Projection (x/y projection, alignment constraints)
  layout.ts             -> _cola_gen (Layout.start phases + tick loop, flowLayout)
  linklengths.ts        -> _link_lengths (symmetric difference / Jaccard),
                           _scc (Tarjan), flow constraints (generateDirectedEdgeConstraints)
  handledisconnected.ts -> _apply_packing (separateGraphs / applyPacking)
  shortestpaths.ts      -> replaced by layouts._bfs_hops / _dijkstra_all (same result)
Recursion in the TypeScript (VPSC block trees, Tarjan) is iterative here: Pyodide's
stack is small.
"""
import bisect
import math
import time

import numpy as np

from .model import NODE, GuessError

_ZERO_UB = -1e-10       # vpsc Solver.ZERO_UPPERBOUND
_LAG_TOL = -1e-4        # vpsc Solver.LAGRANGIAN_TOLERANCE


# --------------------------------------------------------------------------
# descent.ts
# --------------------------------------------------------------------------

class _PseudoRandom:
    """descent.ts PseudoRandom: linear congruential generator."""

    def __init__(self, seed=1):
        self.seed = seed

    def next(self):
        self.seed = (self.seed * 214013 + 2531011) % 2147483648
        return (self.seed >> 16) / 32767

    def between(self, lo, hi):
        return lo + self.next() * (hi - lo)


class _Descent:
    """descent.ts Descent for k = 2, with computeDerivatives and the step-size
    products vectorised over all node pairs (k x n x n arrays)."""

    def __init__(self, x, D, seed=1):
        self.x = x                      # (2, n), updated in place
        self.k, self.n = x.shape
        self.D = D
        self.G = None
        self.threshold = 1e-4
        self.locks = {}                 # node -> (x, y)
        self.project = None
        self.random = _PseudoRandom(seed)
        n = self.n
        iu = np.triu_indices(n, 1)
        up = D[iu]
        up = up[(up > 0) & np.isfinite(up)]
        self.minD = float(up.min()) if len(up) else 1.0
        self.diag = np.eye(n, dtype=bool)
        fin = np.isfinite(D) & ~self.diag
        self.Dz = np.where(fin, D, 0.0)
        with np.errstate(divide="ignore"):
            self.invD2 = np.where(fin, 1.0 / (self.Dz * self.Dz), 0.0)
        self.invD2[~np.isfinite(self.invD2)] = 0.0      # zero ideal distance: no term

    def offset_dir(self):
        u = np.array([self.random.between(0.01, 1) - 0.5 for _ in range(self.k)])
        return u * (self.minD / math.sqrt((u * u).sum()))

    def derivatives(self, x):
        """computeDerivatives: gradient g (k, n) and Hessian H (k, n, n)."""
        n = self.n
        for _ in range(max(n, 1)):
            d = x[:, :, None] - x[:, None, :]
            d2 = d * d
            ds = d2.sum(0)
            ds[self.diag] = 1.0
            bad = ds <= 1e-9
            if not bad.any():
                break
            # coincident nodes: the later one of each pair is displaced at random
            for v in np.unique(np.nonzero(np.triu(bad, 1))[1]).tolist():
                x[:, v] += self.offset_dir()
        dist = np.sqrt(ds)
        W = self.invD2
        if self.G is not None:
            # p-stress: ignore long-range attraction between non-neighbours
            W = np.where((self.G > 1) & (dist > self.Dz), 0.0, np.minimum(self.G, 1.0) * W)
        gs = 2 * W * (dist - self.Dz) / dist
        hs = -2 * W / (ds * dist)
        g = (d * gs).sum(2)
        H = hs * (2 * ds * dist + self.Dz * (d2 - ds))
        Huu = -H.sum(2)
        idx = np.arange(n)
        H[:, idx, idx] = Huu
        maxH = max(0.0, float(Huu.max())) if n else 0.0
        for u, p in self.locks.items():
            H[:, u, u] += maxH
            g[:, u] -= maxH * (np.asarray(p) - x[:, u])
        self.g, self.H = g, H

    def step_size(self, d):
        num = float((self.g * d).sum())
        Hd = np.einsum("kij,kj->ki", self.H, d)
        den = float((d * Hd).sum())
        if den == 0 or not math.isfinite(den):
            return 0.0
        return num / den

    def step_and_project(self, x0, d, step):
        r = x0.copy()
        r[0] -= step * d[0]
        if self.project:
            self.project[0](x0[0], x0[1], r[0])
        r[1] -= step * d[1]
        if self.project:
            self.project[1](r[0], x0[1], r[1])
        return r

    def next_position(self, x0):
        self.derivatives(x0)
        alpha = self.step_size(self.g)
        r = self.step_and_project(x0, self.g, alpha)
        if self.project:
            e = x0 - r
            beta = max(0.2, min(self.step_size(e), 1.0))
            r = self.step_and_project(x0, e, beta)
        return r

    def runge_kutta(self):
        x = self.x
        a = self.next_position(x)
        b = self.next_position(x + (a - x) / 2)
        c = self.next_position(x + (b - x) / 2)
        d = self.next_position(c)
        nx = (a + 2 * b + 2 * c + d) / 6
        disp = float(((x - nx) ** 2).sum())
        x[:] = nx
        return disp

    def run(self, iterations):
        """Descent.run as a generator (yields once per Runge-Kutta step)."""
        stress = math.inf
        while iterations > 0:
            iterations -= 1
            s = self.runge_kutta()
            yield
            if s == 0 or abs(stress / s - 1) < self.threshold:
                return
            stress = s


# --------------------------------------------------------------------------
# vpsc.ts
# --------------------------------------------------------------------------

class _VPSC:
    """vpsc.ts Solver (Blocks, Block, Constraint, Variable) for unit-scale
    variables (Cola never sets Variable.scale). Block statistics live in numpy
    arrays indexed by block id; active-constraint trees are walked iteratively.

    shortcut: the merge/split loop is sequential Python -- fine for a few hundred
    nodes; for thousands it needs a compiled solver or incremental constraints."""

    def __init__(self, desired, weight, L, R, gap, eq):
        n, m = len(desired), len(L)
        self.d = np.asarray(desired, float)
        self.w = np.asarray(weight, float)
        self.L, self.R = np.asarray(L, np.intp), np.asarray(R, np.intp)
        self.gap, self.eq = np.asarray(gap, float), np.asarray(eq, bool)
        self.Ll, self.Rl, self.gl, self.eql = self.L.tolist(), self.R.tolist(), self.gap.tolist(), self.eq.tolist()
        self.cout = [[] for _ in range(n)]
        self.cin = [[] for _ in range(n)]
        for c in range(m):
            self.cout[self.Ll[c]].append(c)
            self.cin[self.Rl[c]].append(c)
        self.active = [False] * m
        self.lm = [0.0] * m
        self.inactive = np.ones(m, bool)
        self.unsat = np.zeros(m, bool)
        # Blocks(vs): one block per variable, at its desired position
        self.off = np.zeros(n)
        self.blk = np.arange(n)
        cap = 2 * n + 16
        self.bAB, self.bAD, self.bA2, self.bpos = (np.zeros(cap) for _ in range(4))
        self.bAD[:n] = self.w * self.d
        self.bA2[:n] = self.w
        self.bpos[:n] = self.d
        self.bvars = {v: [v] for v in range(n)}
        self.blist = list(range(n))
        self.bind = {v: v for v in range(n)}
        self.nid = n

    # -- blocks --------------------------------------------------------------
    def _new_block(self, v):
        if self.nid >= len(self.bpos):
            grow = len(self.bpos)
            self.bAB, self.bAD, self.bA2, self.bpos = (np.concatenate([a, np.zeros(grow)])
                                                       for a in (self.bAB, self.bAD, self.bA2, self.bpos))
        b = self.nid
        self.nid += 1
        self.bvars[b] = []
        self.bAB[b] = self.bAD[b] = self.bA2[b] = 0.0
        self.off[v] = 0.0
        self._add(b, v)
        return b

    def _add(self, b, v):
        self.blk[v] = b
        self.bvars[b].append(v)
        w = self.w[v]
        self.bAB[b] += w * self.off[v]
        self.bAD[b] += w * self.d[v]
        self.bA2[b] += w
        self.bpos[b] = (self.bAD[b] - self.bAB[b]) / self.bA2[b]

    def _insert(self, b):
        self.bind[b] = len(self.blist)
        self.blist.append(b)

    def _remove(self, b):
        i = self.bind.pop(b)
        last = self.blist.pop()
        if last != b:
            self.blist[i] = last
            self.bind[last] = i
        del self.bvars[b]

    def positions(self):
        return self.bpos[self.blk] + self.off

    def _pos(self, v):
        return self.bpos[self.blk[v]] + self.off[v]

    def slack(self, c):
        if self.unsat[c]:
            return math.inf
        return self._pos(self.Rl[c]) - self.gl[c] - self._pos(self.Ll[c])

    def cost(self):
        p = self.positions() - self.d
        return float((self.w * p * p).sum())

    def _update_block_positions(self):
        k = self.nid
        self.bAB[:k] = np.bincount(self.blk, self.w * self.off, k)
        self.bAD[:k] = np.bincount(self.blk, self.w * self.d, k)
        self.bA2[:k] = np.bincount(self.blk, self.w, k)
        live = self.bA2[:k] > 0
        self.bpos[:k][live] = (self.bAD[:k][live] - self.bAB[:k][live]) / self.bA2[:k][live]

    # -- active constraint trees ----------------------------------------------
    def _tree(self, root):
        """DFS over active constraints: [(var, constraint to parent, parent index)]."""
        out = [(root, -1, -1)]
        stack = [(root, -1, 0)]
        active, Rl, Ll = self.active, self.Rl, self.Ll
        while stack:
            v, prev, k = stack.pop()
            for c in self.cout[v]:
                if active[c] and Rl[c] != prev:
                    out.append((Rl[c], c, k))
                    stack.append((Rl[c], v, len(out) - 1))
            for c in self.cin[v]:
                if active[c] and Ll[c] != prev:
                    out.append((Ll[c], c, k))
                    stack.append((Ll[c], v, len(out) - 1))
        return out

    def _compute_lm(self, root):
        """Block.compute_lm: Lagrange multipliers of the tree's constraints."""
        order = self._tree(root)
        vs = np.fromiter((o[0] for o in order), np.intp, len(order))
        df = (2 * self.w[vs] * (self.bpos[self.blk[vs]] + self.off[vs] - self.d[vs])).tolist()
        lm, Rl = self.lm, self.Rl
        for k in range(len(order) - 1, 0, -1):
            v, c, p = order[k]
            val = df[k]
            lm[c] = val if Rl[c] == v else -val
            df[p] += val
        return order

    def _find_min_lm(self, b):
        order = self._compute_lm(self.bvars[b][0])
        m = None
        lm, eq = self.lm, self.eql
        for _, c, _ in order[1:]:
            if not eq[c] and (m is None or lm[c] < lm[m]):
                m = c
        return m

    def _find_min_lm_between(self, lv, rv):
        order = self._compute_lm(lv)
        where = {o[0]: k for k, o in enumerate(order)}
        k = where.get(rv)
        m = None
        lm, eq, Rl = self.lm, self.eql, self.Rl
        while k is not None and k > 0:
            v, c, p = order[k]
            if not eq[c] and Rl[c] == v and (m is None or lm[c] < lm[m]):
                m = c
            k = p
        return m

    def _active_directed_path(self, u, v):
        stack, seen = [u], {u}
        while stack:
            x = stack.pop()
            if x == v:
                return True
            for c in self.cout[x]:
                r = self.Rl[c]
                if self.active[c] and r not in seen:
                    seen.add(r)
                    stack.append(r)
        return False

    def _split_block(self, start):
        """Block.createSplitBlock / populateSplitBlock."""
        b = self._new_block(start)
        order = self._tree(start)
        for u, c, p in order[1:]:
            pv = order[p][0]
            self.off[u] = self.off[pv] + (self.gl[c] if self.Rl[c] == u else -self.gl[c])
            self._add(b, u)
        return b

    def _split(self, c):
        self.active[c] = False
        return self._split_block(self.Ll[c]), self._split_block(self.Rl[c])

    def _merge_across(self, into, frm, c, dist):
        self.active[c] = True
        vs = np.array(self.bvars[frm], np.intp)
        self.off[vs] += dist
        self.blk[vs] = into
        self.bvars[into].extend(self.bvars[frm])
        w = self.w[vs]
        self.bAB[into] += (w * self.off[vs]).sum()
        self.bAD[into] += (w * self.d[vs]).sum()
        self.bA2[into] += w.sum()
        self.bpos[into] = (self.bAD[into] - self.bAB[into]) / self.bA2[into]

    def _merge(self, c):
        l, r = int(self.blk[self.Ll[c]]), int(self.blk[self.Rl[c]])
        dist = self.off[self.Rl[c]] - self.off[self.Ll[c]] - self.gl[c]
        if len(self.bvars[l]) < len(self.bvars[r]):
            self._merge_across(r, l, c, dist)
            self._remove(l)
        else:
            self._merge_across(l, r, c, -dist)
            self._remove(r)

    def _split_blocks(self):
        """Blocks.split: split every block across its most negative multiplier."""
        self._update_block_positions()
        for b in list(self.blist):
            if len(self.bvars[b]) < 2:
                continue
            c = self._find_min_lm(b)
            if c is not None and self.lm[c] < _LAG_TOL:
                for nb in self._split(c):
                    self._insert(nb)
                self._remove(b)
                self.inactive[c] = True

    def _most_violated(self):
        cand = np.flatnonzero(self.inactive & ~self.unsat)
        if not len(cand):
            return None
        eqc = cand[self.eq[cand]]
        if len(eqc):
            v = int(eqc[0])
            self.inactive[v] = False
            return v
        p = self.positions()
        sl = p[self.R[cand]] - self.gap[cand] - p[self.L[cand]]
        k = int(sl.argmin())
        v = int(cand[k])
        if sl[k] < _ZERO_UB and not self.active[v]:
            self.inactive[v] = False
        return v

    def satisfy(self):
        self._split_blocks()
        while True:
            v = self._most_violated()
            if v is None or not (self.eql[v] or (self.slack(v) < _ZERO_UB and not self.active[v])):
                return
            lb, rb = int(self.blk[self.Ll[v]]), int(self.blk[self.Rl[v]])
            if lb != rb:
                self._merge(v)
                continue
            if self._active_directed_path(self.Rl[v], self.Ll[v]):
                self.unsat[v] = True            # cycle
                continue
            c = self._find_min_lm_between(self.Ll[v], self.Rl[v])
            if c is None:
                self.unsat[v] = True
                continue
            for nb in self._split(c):
                self._insert(nb)
            self._remove(lb)
            self.inactive[c] = True
            if self.slack(v) >= 0:
                self.inactive[v] = True         # satisfied by the split
            else:
                self._merge(v)

    def solve(self):
        self.satisfy()
        last, cost = math.inf, self.cost()
        for _ in range(100):                    # the TypeScript loops without a cap
            if abs(last - cost) <= 1e-4:
                break
            self.satisfy()
            last, cost = cost, self.cost()
        return cost


def _vpsc_solve(desired, weight, cons):
    """Solver.setDesiredPositions + solve; returns the variables' positions."""
    if not cons:
        return desired
    L, R, gap, eq = (np.array(a) for a in zip(*cons))
    L, R, gap, eq = L.astype(np.intp), R.astype(np.intp), gap.astype(float), eq.astype(bool)
    # all inequalities already hold at the desired positions: VPSC returns them unchanged
    if not eq.any() and (desired[R] - gap - desired[L] >= _ZERO_UB).all():
        return desired
    s = _VPSC(desired, weight, L, R, gap, eq)
    s.solve()
    return s.positions()


# --------------------------------------------------------------------------
# rectangle.ts
# --------------------------------------------------------------------------

def _overlap_constraints(cx, cy, w, h, axis, min_sep=1e-6):
    """generateXConstraints / generateYConstraints: sweep a scan line over the
    rectangles, constraining neighbours on the scan line. Returns (l, r, gap, False)."""
    n = len(cx)
    if n < 2:
        return []
    x0, X, y0, Y = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    if axis == 0:
        centre, opn, cls, size = cx, y0, Y, w
    else:
        centre, opn, cls, size = cy, x0, X, h
    # events by position, opens before closes (compareEvents)
    order = np.lexsort((np.r_[np.zeros(n), np.ones(n)], np.r_[opn, cls])).tolist()
    cen, sz = centre.tolist(), size.tolist()
    cxl, x0l, Xl, cyl, y0l, Yl = cx.tolist(), x0.tolist(), X.tolist(), cy.tolist(), y0.tolist(), Y.tolist()

    def overlap_x(u, v):            # Rectangle.overlapX, this = u
        if cxl[u] <= cxl[v] and x0l[v] < Xl[u]:
            return Xl[u] - x0l[v]
        if cxl[v] <= cxl[u] and x0l[u] < Xl[v]:
            return Xl[v] - x0l[u]
        return 0.0

    def overlap_y(u, v):
        if cyl[u] <= cyl[v] and y0l[v] < Yl[u]:
            return Yl[u] - y0l[v]
        if cyl[v] <= cyl[u] and y0l[u] < Yl[v]:
            return Yl[v] - y0l[u]
        return 0.0

    scan = []                        # (centre, index): the RBTree, ties broken by index
    prv = [set() for _ in range(n)]
    nxt = [set() for _ in range(n)]
    out = []
    for e in order:
        if e < n:
            v = e
            k = bisect.bisect_left(scan, (cen[v], v))
            scan.insert(k, (cen[v], v))
            if axis == 0:            # findXNeighbours
                for j in range(k + 1, len(scan)):
                    u = scan[j][1]
                    ox = overlap_x(u, v)
                    if ox <= 0 or ox <= overlap_y(u, v):
                        nxt[v].add(u)
                        prv[u].add(v)
                    if ox <= 0:
                        break
                for j in range(k - 1, -1, -1):
                    u = scan[j][1]
                    ox = overlap_x(u, v)
                    if ox <= 0 or ox <= overlap_y(u, v):
                        prv[v].add(u)
                        nxt[u].add(v)
                    if ox <= 0:
                        break
            else:                    # findYNeighbours
                if k + 1 < len(scan):
                    u = scan[k + 1][1]
                    if overlap_x(u, v) > 0:
                        nxt[v].add(u)
                        prv[u].add(v)
                if k > 0:
                    u = scan[k - 1][1]
                    if overlap_x(u, v) > 0:
                        prv[v].add(u)
                        nxt[u].add(v)
        else:
            v = e - n
            k = bisect.bisect_left(scan, (cen[v], v))
            del scan[k]
            for u in sorted(prv[v], key=lambda u: -cen[u]):
                out.append((u, v, (sz[u] + sz[v]) / 2 + min_sep, False))
                nxt[u].discard(v)
            for u in sorted(nxt[v], key=lambda u: cen[u]):
                out.append((v, u, (sz[v] + sz[u]) / 2 + min_sep, False))
                prv[u].discard(v)
    return out


class _Projection:
    """rectangle.ts Projection without groups: user separation / alignment
    constraints, plus non-overlap constraints when avoid_overlaps is set."""

    def __init__(self, size, fixed, pxy, constraints, avoid_overlaps, X):
        self.w, self.h = size[:, 0], size[:, 1]
        self.fixed, self.pxy, self.avoid = fixed, pxy, avoid_overlaps
        self.weight = np.where(fixed, 1000.0, 1.0)      # fixedWeight default
        self.cs = ([], [])
        for c in constraints:
            if c.get("type", "separation") == "separation":
                self.cs[0 if c["axis"] == "x" else 1].append(
                    (c["left"], c["right"], float(c["gap"]), bool(c.get("equality", False))))
        for c in constraints:
            if c.get("type") == "alignment":
                self._make_feasible(c, X)
                u = c["offsets"][0]["node"]
                for o in c["offsets"][1:]:
                    self.cs[0 if c["axis"] == "x" else 1].append((u, o["node"], float(o["offset"]), True))

    def _make_feasible(self, c, X):
        """Shove overlapping nodes of an alignment apart along its guideline."""
        if not self.avoid:
            return
        ax, dim = (1, self.h) if c["axis"] == "x" else (0, self.w)
        vs = sorted((o["node"] for o in c["offsets"]), key=lambda v: X[ax, v])
        for p, v in zip(vs, vs[1:]):
            nxt = X[ax, p] + dim[p]
            if nxt > X[ax, v]:
                X[ax, v] = nxt

    def _project(self, axis, cx, cy, desired):
        desired[self.fixed] = self.pxy[axis][self.fixed]
        cs = self.cs[axis]
        if self.avoid:
            cs = cs + _overlap_constraints(cx, cy, self.w, self.h, axis)
        desired[:] = _vpsc_solve(desired, self.weight, cs)

    def functions(self):
        return [lambda x0, y0, x: self._project(0, x0, y0, x),
                lambda x0, y0, y: self._project(1, x0, y0, y)]


# --------------------------------------------------------------------------
# linklengths.ts
# --------------------------------------------------------------------------

def _link_lengths(snap, base, kind):
    """symmetricDiffLinkLengths / jaccardLinkLengths: base * (1 + f(N(u), N(v)))."""
    nb = [set() for _ in range(snap.n)]
    for a, b in zip(snap.src.tolist(), snap.dst.tolist()):
        nb[a].add(b)
        nb[b].add(a)
    out = np.empty(len(snap.src))
    for k, (a, b) in enumerate(zip(snap.src.tolist(), snap.dst.tolist())):
        A, B = nb[a], nb[b]
        inter, union = len(A & B), len(A | B)
        if kind == "symdiff":
            f = math.sqrt(union - inter)
        else:
            f = 0.0 if min(len(A), len(B)) < 1.1 else inter / union
        out[k] = base * (1 + f)
    return out


def _scc(n, src, dst):
    """stronglyConnectedComponents (Tarjan), iterative: component id per node."""
    out = [[] for _ in range(n)]
    for a, b in zip(src, dst):
        out[a].append(b)
    index, low, onstack, comp = [-1] * n, [0] * n, [False] * n, [-1] * n
    stack, counter, ncomp = [], 0, 0
    for s in range(n):
        if index[s] >= 0:
            continue
        work = [(s, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                onstack[v] = True
            recurse = False
            while i < len(out[v]):
                w = out[v][i]
                i += 1
                if index[w] < 0:
                    work.append((v, i))
                    work.append((w, 0))
                    recurse = True
                    break
                if onstack[w]:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    onstack[w] = False
                    comp[w] = ncomp
                    if w == v:
                        break
                ncomp += 1
            if work:
                p = work[-1][0]
                low[p] = min(low[p], low[v])
    return comp


# --------------------------------------------------------------------------
# handledisconnected.ts
# --------------------------------------------------------------------------

def _apply_packing(X, size, comps, w, h, ratio=1.0, center=True):
    """separateGraphs + applyPacking: pack component boxes in rows, choosing the
    row width by golden-section search for an aspect ratio near `ratio`."""
    PAD, GOLD, EPS = 10.0, (1 + math.sqrt(5)) / 2, 1e-4
    if not comps:
        return
    graphs = []
    for c in comps:
        c = np.asarray(c)
        lo = (X[:, c] - size[c].T / 2).min(1)
        hi = (X[:, c] + size[c].T / 2).max(1)
        graphs.append({"array": c, "lo": lo, "width": hi[0] - lo[0], "height": hi[1] - lo[1]})
    graphs.sort(key=lambda g: -g["height"])
    min_width = min(g["width"] for g in graphs)
    st = {}

    def step(max_width):
        line = []
        st["rw"] = st["rh"] = 0.0
        bottom = 0.0
        for r in graphs:
            parent = None
            for p in line:
                if p["space_left"] >= r["height"] and p["x"] + p["width"] + r["width"] + PAD - max_width <= EPS:
                    parent = p
                    break
            line.append(r)
            if parent is not None:
                r["x"] = parent["x"] + parent["width"] + PAD
                r["y"] = parent["bottom"]
                r["space_left"] = r["height"]
                r["bottom"] = r["y"]
                parent["space_left"] -= r["height"] + PAD
                parent["bottom"] += r["height"] + PAD
            else:
                r["y"] = bottom
                bottom += r["height"] + PAD
                r["x"] = 0.0
                r["bottom"] = r["y"]
                r["space_left"] = r["height"]
            if r["y"] + r["height"] - st["rh"] > -EPS:
                st["rh"] = r["y"] + r["height"]
            if r["x"] + r["width"] - st["rw"] > -EPS:
                st["rw"] = r["x"] + r["width"]
        return abs((st["rw"] / st["rh"] if st["rh"] else math.inf) - ratio)

    left, right = min_width, sum(g["width"] + PAD for g in graphs)
    x1, x2 = left, right
    f1 = f2 = math.inf
    flag, dx, df = -1, math.inf, math.inf
    best_f, best = math.inf, 0.0
    it = 0
    while dx > min_width or df > EPS:
        if flag != 1:
            x1 = right - (right - left) / GOLD
            f1 = step(x1)
        if flag != 0:
            x2 = left + (right - left) / GOLD
            f2 = step(x2)
        dx, df = abs(x1 - x2), abs(f1 - f2)
        if f1 < best_f:
            best_f, best = f1, x1
        if f2 < best_f:
            best_f, best = f2, x2
        if f1 > f2:
            left, x1, f1, flag = x1, x2, f2, 1
        else:
            right, x2, f2, flag = x2, x1, f1, 0
        it += 1
        if it > 101:
            break
    step(best)
    if center:
        for g in graphs:
            # WebCola takes the corner from the node centroid, which lets packed
            # boxes overlap; the bounding box corner is used here
            off = (g["x"] - g["lo"][0] + w / 2 - st["rw"] / 2,
                   g["y"] - g["lo"][1] + h / 2 - st["rh"] / 2)
            X[0, g["array"]] += off[0]
            X[1, g["array"]] += off[1]


# --------------------------------------------------------------------------
# layout.ts: Layout.start + tick
# --------------------------------------------------------------------------

def _cola_gen(snap, o):
    from .layouts import BOX, _bfs_hops, _dijkstra_all
    n = snap.n
    fixed = snap.fixed
    size = snap.size + 2 * o["spacing"]                 # cytoscape-cola: w + 2 * nodeSpacing
    X = (snap.pos + snap.size / 2).T.copy()             # Cola works with centres
    if o["randomize"]:
        R = np.round(o["rng"].uniform(0, BOX, (2, n)))
        X[:, ~fixed] = R[:, ~fixed]

    def out():
        P = X.T - snap.size / 2
        P[fixed] = snap.pos[fixed]
        return P

    # ideal distances: shortest paths with respect to link length
    if o["lengths"] is None:
        indptr, ind = snap.csr
        hops = _bfs_hops(indptr, ind, n, np.arange(n)).astype(float)
        D = np.where(hops < 0, np.inf, hops * o["length"])
    else:
        snap.weight = o["lengths"]
        D = _dijkstra_all(snap, list(range(n)))
    G = np.full((n, n), 2.0)
    G[snap.src, snap.dst] = G[snap.dst, snap.src] = 1.0

    descent = _Descent(X, D, seed=o["seed"] + 1)
    pxy = X.copy()
    descent.locks = {i: pxy[:, i].copy() for i in np.flatnonzero(fixed).tolist()}
    descent.threshold = o["threshold"]
    comps = sorted((sorted(c) for c in snap.components), key=lambda c: c[0])
    pack = o["disconnected"] and not fixed.any()

    def separate():
        if pack:
            _apply_packing(X, size, comps, BOX, BOX)

    for _ in descent.run(o["unconstr"]):
        yield out()
    cons = list(o["constraints"])
    if o["flow"]:
        comp = _scc(n, snap.src.tolist(), snap.dst.tolist())
        cons += [{"axis": o["flow"], "left": a, "right": b, "gap": o["flow_sep"]}
                 for a, b in zip(snap.src.tolist(), snap.dst.tolist()) if comp[a] != comp[b]]
    if cons:
        descent.project = _Projection(size, fixed, pxy, cons, False, X).functions()
    for _ in descent.run(o["user"]):
        yield out()
    separate()
    if o["avoid"]:
        descent.project = _Projection(size, fixed, pxy, cons, True, X).functions()
    descent.G = G                                       # p-stress from here on
    for _ in descent.run(o["all"]):
        yield out()
    separate()
    yield out()

    # tick(): keep iterating with every constraint until the displacement of a
    # Runge-Kutta step drops below the threshold (cytoscape-cola: or time is up)
    alpha, last = 0.1, None
    t0 = time.monotonic()
    for _ in range(o["iterations"]):
        if alpha < o["threshold"]:
            break
        if o["max_time"] is not None and (time.monotonic() - t0) * 1000 > o["max_time"]:
            break
        s1 = descent.runge_kutta()
        if s1 == 0:
            alpha = 0.0
        elif last is not None:
            alpha = s1
        last = s1
        yield out()

    # GUESS additions: one zero-length projection step so the result satisfies the
    # constraints exactly (Runge-Kutta averages four projected points), then pack
    # the components again since they drift apart while ticking
    if descent.project:
        r = X.copy()
        descent.project[0](X[0], X[1], r[0])
        descent.project[1](r[0], X[1], r[1])
        X[:] = r
    separate()
    yield out()


# --------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------

def install(session):
    from .layouts import _Layouts, _field_arg, _iters, _node_arg, _num

    g = session.graph

    def colaLayout(edgeLength=None, nodeSpacing=10, avoidOverlap=True, flow=None,
                   flowSeparation=50, alignment=None, gapInequalities=None,
                   handleDisconnected=True, unconstrIter=0, userConstIter=0, allConstIter=0,
                   iterations=1000, maxSimulationTime=4000, convergenceThreshold=0.01,
                   edgeSymDiffLength=None, edgeJaccardLength=None, randomize=False, seed=0):
        """colaLayout() runs Cola (WebCola, the constraint-based layout of Tim Dwyer
        and colleagues: Dwyer, Koren & Marriott, "IPSep-CoLa", InfoVis 2006; Dwyer,
        Marriott & Stuckey, "Fast node overlap removal", GD 2005), ported from
        WebCola with the defaults of cytoscape.js-cola. It minimises stress (each
        pair of nodes as far apart as their graph distance) by gradient descent,
        and after every step projects the positions onto separation constraints
        solved with VPSC, so nodes never overlap and user constraints hold.
        It starts from the current positions and animates; Stop ends it early.

        Options, by keyword:
          edgeLength        ideal edge length (100), or an edge field giving one per edge
          edgeSymDiffLength / edgeJaccardLength
                            instead: base length scaled up by how different the two
                            end nodes' neighbourhoods are (Cola's link-length helpers)
          nodeSpacing       extra space around every node (10)
          avoidOverlap      keep node boxes apart (true)
          flow              "y": every edge points down, "x": left to right, by at least
                            flowSeparation (50); edges inside cycles are left free
          alignment         {"vertical": [[a, b, ...], ...], "horizontal": [[...]]}: each
                            list shares an x (vertical) or y (horizontal) coordinate;
                            an entry may be (node, offset)
          gapInequalities   [{"axis": "y", "left": a, "right": b, "gap": 25}, ...]: b at
                            least gap below (or right of) a; "equality": true makes it exact
          handleDisconnected  pack connected components side by side (true; skipped
                            when any node is pinned, so pinned nodes stay put)
          unconstrIter, userConstIter, allConstIter
                            Cola's initial iterations without constraints, with user
                            constraints only, and with all constraints (0, 0, 0)
          iterations        most iterations of the main loop (1000)
          maxSimulationTime stop the main loop after this many ms (4000; None for no
                            limit -- needed for exactly repeatable results on big graphs)
          convergenceThreshold  stop when a step moves nodes less than this (0.01)
          randomize         start from random positions instead (false); seed= picks them
        Pinned (fixed) nodes stay where they are. Every pair of nodes is compared,
        so it suits graphs up to a few thousand nodes."""
        lay = getattr(session, "_layouts", None) or _Layouts(session)
        s = lay.snap()
        if s.n == 0:
            return
        if flow is not None and flow not in ("x", "y"):
            raise GuessError('colaLayout flow is "x" or "y"')
        lengths, length = None, 100.0
        if edgeLength is not None and not isinstance(edgeLength, (int, float)):
            f = _field_arg(g, edgeLength)
            if f.kind == NODE:
                raise GuessError(f"colaLayout(edgeLength=...) needs a number or an edge field, got the node field {f.name}")
            lengths = np.fromiter((_num(e._vals.get(f.name), 100.0) for e in s.edges), float, len(s.edges))
        elif edgeLength is not None:
            length = float(edgeLength)
        elif edgeSymDiffLength is not None:
            lengths = _link_lengths(s, float(edgeSymDiffLength), "symdiff")
        elif edgeJaccardLength is not None:
            lengths = _link_lengths(s, float(edgeJaccardLength), "jaccard")
        if lengths is not None and not (lengths > 0).all():
            raise GuessError("colaLayout edge lengths must be positive")

        def idx(x):
            return s.index[_node_arg(g, x)._id]

        cons = []
        for key, axis in (("vertical", "x"), ("horizontal", "y")):
            for group in (alignment or {}).get(key, []):
                offs = []
                for item in group:
                    nd, off = item if isinstance(item, (tuple, list)) else (item, 0)
                    offs.append({"node": idx(nd), "offset": float(off)})
                if len(offs) > 1:
                    cons.append({"type": "alignment", "axis": axis, "offsets": offs})
        for q in gapInequalities or []:
            if q.get("axis") not in ("x", "y"):
                raise GuessError('colaLayout gapInequalities need "axis": "x" or "y"')
            cons.append({"axis": q["axis"], "left": idx(q["left"]), "right": idx(q["right"]),
                         "gap": float(q.get("gap", 0)), "equality": bool(q.get("equality", False))})

        opts = dict(spacing=float(nodeSpacing), avoid=bool(avoidOverlap), flow=flow,
                    flow_sep=float(flowSeparation), constraints=cons,
                    disconnected=bool(handleDisconnected), unconstr=_iters(unconstrIter, 0),
                    user=_iters(userConstIter, 0), all=_iters(allConstIter, 0),
                    iterations=_iters(iterations, 1000),
                    max_time=None if maxSimulationTime is None else float(maxSimulationTime),
                    threshold=float(convergenceThreshold), lengths=lengths, length=length,
                    randomize=bool(randomize), rng=np.random.default_rng(int(seed)), seed=int(seed))
        lay.run(s, _cola_gen(s, opts))

    session.register_command("colaLayout", colaLayout)
