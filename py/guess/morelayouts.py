"""More layouts, the equivalents of several Gephi layout plugins:

    multipartiteLayout(field)        one column per value (Multipartite Layout)
    concentricLayout(field)          rings by value, highest in the centre (Concentric)
    dualCircleLayout(count)          hubs on an inner circle, the rest outside (Circular Layout)
    orderedLayout(field)             one axis from a field, a force on the other (Ordered Layout, EventGraphLayout)
    hairballLayout()                 the Hairball Buster plot: rank by degree against degree
    circlePackLayout(field, ...)     nested circles by one or more fields (Circle Pack)
    isometricLayout(field)           stacked layers seen at an angle (Isometric Layout, Network Splitter 3D)

Like every layout they write positions as one undo step, leave `fixed` nodes
where they are and re-centre the view afterwards (centerAfterLayout).
"""
import math
import random

import numpy as np

from .layouts import BOX, _bfs_hops, _fa2_gen, _iters, _Layouts, _num, _scaled
from .model import INT, NODE, Field, GuessError, as_field


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _node_field(graph, f, what):
    fld = as_field(graph, f, what, kinds=(NODE,))
    return fld


def _values(fld, snap):
    out = []
    for nd in snap.nodes:
        try:
            out.append(fld.get(nd))
        except Exception:   # noqa: BLE001  (a computed field that fails for one node)
            out.append(None)
    return out


def _sort_key(v):
    """Numbers in numeric order, then everything else as text; None last."""
    if v is None:
        return (2, "")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0, float(v))
    return (1, str(v))


def _numeric(vals):
    return all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in vals)


def _diam(snap):
    return snap.size.max(1)


def _ring_positions(count, radius, cx, cy, start=-math.pi / 2):
    a = start + 2 * math.pi * np.arange(count) / max(count, 1)
    return np.stack([cx + radius * np.cos(a), cy + radius * np.sin(a)], 1)


def _circle_guides(cx, cy, r, segments=48):
    """A circle as guide segments (the renderer draws guides as lines)."""
    out = []
    for k in range(segments):
        a0, a1 = 2 * math.pi * k / segments, 2 * math.pi * (k + 1) / segments
        out.append({"x1": cx + r * math.cos(a0), "y1": cy + r * math.sin(a0),
                    "x2": cx + r * math.cos(a1), "y2": cy + r * math.sin(a1), "label": ""})
    return out


def _label_guide(x, y, text):
    """A label on its own (a zero-length guide)."""
    return {"x1": x, "y1": y, "x2": x, "y2": y, "label": str(text)}


# --------------------------------------------------------------------------
# circle packing (d3-hierarchy's packSiblings and packEnclose: Wang et al.'s
# front-chain packing, and Welzl's smallest enclosing circle)
# --------------------------------------------------------------------------

class _C:
    __slots__ = ("x", "y", "r")

    def __init__(self, r, x=0.0, y=0.0):
        self.x, self.y, self.r = x, y, r


def _place(b, a, c):
    """Put c tangent to both a and b."""
    dx, dy = b.x - a.x, b.y - a.y
    d2 = dx * dx + dy * dy
    if d2:
        a2 = (a.r + c.r) ** 2
        b2 = (b.r + c.r) ** 2
        if a2 > b2:
            x = (d2 + b2 - a2) / (2 * d2)
            y = math.sqrt(max(0.0, b2 / d2 - x * x))
            c.x = b.x - x * dx - y * dy
            c.y = b.y - x * dy + y * dx
        else:
            x = (d2 + a2 - b2) / (2 * d2)
            y = math.sqrt(max(0.0, a2 / d2 - x * x))
            c.x = a.x + x * dx - y * dy
            c.y = a.y + x * dy + y * dx
    else:
        c.x = a.x + c.r
        c.y = a.y


def _intersects(a, b):
    dr = a.r + b.r - 1e-6
    dx, dy = b.x - a.x, b.y - a.y
    return dr > 0 and dr * dr > dx * dx + dy * dy


class _Link:
    __slots__ = ("c", "next", "prev")

    def __init__(self, c):
        self.c, self.next, self.prev = c, None, None


def _score(node):
    a, b = node.c, node.next.c
    ab = a.r + b.r
    dx = (a.x * b.r + b.x * a.r) / ab
    dy = (a.y * b.r + b.y * a.r) / ab
    return dx * dx + dy * dy


def _encloses_not(a, b):
    dr = a.r - b.r
    dx, dy = b.x - a.x, b.y - a.y
    return dr < 0 or dr * dr < dx * dx + dy * dy


def _encloses_weak(a, b):
    dr = a.r - b.r + max(a.r, b.r, 1) * 1e-9
    dx, dy = b.x - a.x, b.y - a.y
    return dr > 0 and dr * dr > dx * dx + dy * dy


def _encloses_weak_all(a, B):
    return all(_encloses_weak(a, b) for b in B)


def _basis2(a, b):
    x21, y21, r21 = b.x - a.x, b.y - a.y, b.r - a.r
    ln = math.sqrt(x21 * x21 + y21 * y21)
    return _C((ln + a.r + b.r) / 2, (a.x + b.x + x21 / ln * r21) / 2, (a.y + b.y + y21 / ln * r21) / 2)


def _basis3(a, b, c):
    x1, y1, r1 = a.x, a.y, a.r
    a2, a3 = x1 - b.x, x1 - c.x
    b2, b3 = y1 - b.y, y1 - c.y
    c2, c3 = b.r - r1, c.r - r1
    d1 = x1 * x1 + y1 * y1 - r1 * r1
    d2 = d1 - b.x * b.x - b.y * b.y + b.r * b.r
    d3 = d1 - c.x * c.x - c.y * c.y + c.r * c.r
    ab = a3 * b2 - a2 * b3
    xa = (b2 * d3 - b3 * d2) / (ab * 2) - x1
    xb = (b3 * c2 - b2 * c3) / ab
    ya = (a3 * d2 - a2 * d3) / (ab * 2) - y1
    yb = (a2 * c3 - a3 * c2) / ab
    A = xb * xb + yb * yb - 1
    B = 2 * (r1 + xa * xb + ya * yb)
    C = xa * xa + ya * ya - r1 * r1
    r = -((B + math.sqrt(max(0.0, B * B - 4 * A * C))) / (2 * A) if abs(A) > 1e-6 else C / B)
    return _C(r, x1 + xa + xb * r, y1 + ya + yb * r)


def _basis(B):
    if len(B) == 1:
        return _C(B[0].r, B[0].x, B[0].y)
    if len(B) == 2:
        return _basis2(B[0], B[1])
    return _basis3(B[0], B[1], B[2])


def _extend_basis(B, p):
    if _encloses_weak_all(p, B):
        return [p]
    for i in range(len(B)):
        if _encloses_not(p, B[i]) and _encloses_weak_all(_basis2(B[i], p), B):
            return [B[i], p]
    for i in range(len(B) - 1):
        for j in range(i + 1, len(B)):
            if (_encloses_not(_basis2(B[i], B[j]), p) and _encloses_not(_basis2(B[i], p), B[j])
                    and _encloses_not(_basis2(B[j], p), B[i])
                    and _encloses_weak_all(_basis3(B[i], B[j], p), B)):
                return [B[i], B[j], p]
    raise GuessError("circle packing failed (degenerate circles)")


def _enclose(circles, rnd):
    circles = list(circles)
    rnd.shuffle(circles)
    i, n, B, e = 0, len(circles), [], None
    while i < n:
        p = circles[i]
        if e is not None and _encloses_weak(e, p):
            i += 1
        else:
            B = _extend_basis(B, p)
            e = _basis(B)
            i = 0
    return e


def _pack_siblings(circles, rnd):
    """Place circles (radii set) tightly around the origin; returns the
    enclosing radius (d3.packSiblings)."""
    n = len(circles)
    if n == 0:
        return 0.0
    a = circles[0]
    a.x = a.y = 0.0
    if n == 1:
        return a.r
    b = circles[1]
    a.x, b.x, b.y = -b.r, a.r, 0.0
    if n == 2:
        return a.r + b.r
    c = circles[2]
    _place(b, a, c)
    a, b, c = _Link(a), _Link(b), _Link(c)
    a.next = c.prev = b
    b.next = a.prev = c
    c.next = b.prev = a
    i = 3
    while i < n:
        cc = circles[i]
        _place(a.c, b.c, cc)
        c = _Link(cc)
        j, k, sj, sk = b.next, a.prev, b.c.r, a.c.r
        restart = False
        while True:
            if sj <= sk:
                if _intersects(j.c, c.c):
                    b = j
                    a.next, b.prev = b, a
                    restart = True
                    break
                sj += j.c.r
                j = j.next
            else:
                if _intersects(k.c, c.c):
                    a = k
                    a.next, b.prev = b, a
                    restart = True
                    break
                sk += k.c.r
                k = k.prev
            if j is k.next:
                break
        if restart:
            continue
        c.prev, c.next = a, b
        a.next = b.prev = b = c
        aa = _score(a)
        c = c.next
        while c is not b:
            ca = _score(c)
            if ca < aa:
                a, aa = c, ca
            c = c.next
        b = a.next
        i += 1
    chain = [b.c]
    c = b.next
    while c is not b:
        chain.append(c.c)
        c = c.next
    e = _enclose(chain, rnd)
    for cc in circles:
        cc.x -= e.x
        cc.y -= e.y
    return e.r


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    lay = getattr(session, "_layouts", None) or _Layouts(session)
    state = {"iso": None}     # isometricLayout: plane positions, to redo it without compounding

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def graph():
        return session.graph

    def set_guides(guides, note=""):
        session.view.guides = guides
        session.view.guides_note = note
        session.view.changed()

    # ---- multipartite ------------------------------------------------------------
    @cmd
    def multipartiteLayout(field, gap=None, vertical=False):
        """multipartiteLayout(field) puts the nodes in one column per value of a
        node field (in value order: kind, year, level, ...), ordering each column
        to reduce edge crossings; vertical=true makes rows instead. gap is the
        distance between columns (default: they fill 1000 units). The
        multipartite version of bipartiteLayout."""
        fld = _node_field(graph(), field, "multipartiteLayout")
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        vals = _values(fld, s)
        keys = sorted({_sort_key(v) for v in vals})
        col_of = {k: j for j, k in enumerate(keys)}
        col = np.array([col_of[_sort_key(v)] for v in vals])
        k = len(keys)
        cross = 0 if vertical else 1        # the axis along a column
        along = 1 - cross
        # start from the current order along the column, then barycentre sweeps
        cur = s.pos[:, cross] + s.size[:, cross] / 2
        members = [list(np.flatnonzero(col == j)) for j in range(k)]
        for j in range(k):
            members[j].sort(key=lambda i: (cur[i], i))
        nb = [s.neighbors(i) for i in range(s.n)]

        def rel():
            r = np.zeros(s.n)
            for m in members:
                for p, i in enumerate(m):
                    r[i] = (p + 0.5) / len(m)
            return r

        order = list(range(k)) + list(range(k - 2, -1, -1))
        for _ in range(4):
            for j in order:
                r = rel()
                keyed = []
                for p, i in enumerate(members[j]):
                    other = [x for x in nb[i] if col[x] != j]
                    keyed.append((float(np.mean(r[other])) if other else r[i], p, i))
                keyed.sort()
                members[j] = [i for _, _, i in keyed]
        diam = _diam(s)
        tallest = max(len(m) for m in members)
        step = max(1.4 * float(diam.max()), (BOX - 100) / max(tallest - 1, 1))
        g_ = float(gap) if gap is not None else ((BOX - 100) / (k - 1) if k > 1 else 0.0)
        P = s.pos.copy()
        for j, m in enumerate(members):
            span = step * (len(m) - 1)
            for p, i in enumerate(m):
                c = np.empty(2)
                c[along] = 50 + j * g_
                c[cross] = BOX / 2 - span / 2 + p * step
                P[i] = c - s.size[i] / 2
        lay.apply(s, P)

    # ---- concentric --------------------------------------------------------------
    @cmd
    def concentricLayout(field, rings=None):
        """concentricLayout(field) puts the nodes on rings by their value of a
        field, the highest value in the centre (degree, a score, a level). A
        numeric field with many values is cut into `rings` equal ranges
        (default 8); a text field gets one ring per value. Each ring is ordered
        so neighbours of the ring inside sit near them, and spaced to fit the
        nodes' sizes. Compare twopiLayout(root), rings by distance from one node."""
        fld = _node_field(graph(), field, "concentricLayout")
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        vals = _values(fld, s)
        nr = 8 if rings is None else int(rings)
        if nr < 1:
            raise GuessError("concentricLayout needs at least one ring")
        distinct = sorted({_sort_key(v) for v in vals})
        if _numeric(vals) and len(distinct) > nr and any(v is not None for v in vals):
            num = np.array([np.nan if v is None else float(v) for v in vals])
            lo, hi = np.nanmin(num), np.nanmax(num)
            b = np.where(np.isnan(num), -1, np.minimum(((num - lo) / ((hi - lo) or 1) * nr).astype(int), nr - 1))
            ring = np.where(b < 0, nr, nr - 1 - b)          # highest range in the centre; missing outside
        else:
            # one ring per value: numbers highest first, text in order; None outermost
            nums = [d for d in distinct if d[0] == 0][::-1]
            rest = [d for d in distinct if d[0] != 0]
            pos = {d: i for i, d in enumerate(nums + rest)}
            ring = np.array([pos[_sort_key(v)] for v in vals])
        used = sorted(set(ring.tolist()))
        diam = _diam(s)
        P = s.pos.copy()
        cx = cy = BOX / 2
        r_prev, d_prev = 0.0, 0.0
        placed = np.zeros(s.n, bool)
        angle = np.arctan2(s.pos[:, 1] - cy, s.pos[:, 0] - cx)
        for k, rg in enumerate(used):
            m = np.flatnonzero(ring == rg)
            d = float(diam[m].max()) * 1.25
            if k == 0 and len(m) == 1:
                r = 0.0
            else:
                r = max(len(m) * d / (2 * math.pi), r_prev + (d + d_prev) / 2 + d if k else 0.0, d)
            # order: by the mean angle of neighbours already placed, else the current angle
            key = []
            for i in m:
                nb = [x for x in s.neighbors(i) if placed[x]]
                if nb:
                    a = math.atan2(np.sin(angle[nb]).mean(), np.cos(angle[nb]).mean())
                else:
                    a = angle[i]
                key.append((a, i))
            key.sort()
            m = [i for _, i in key]
            Q = _ring_positions(len(m), r, cx, cy, start=key[0][0] if key else 0.0)
            for p, i in enumerate(m):
                P[i] = Q[p] - s.size[i] / 2
                angle[i] = math.atan2(Q[p][1] - cy, Q[p][0] - cx)
            placed[m] = True
            r_prev, d_prev = r, d
        lay.apply(s, P)

    # ---- dual circle -------------------------------------------------------------
    @cmd
    def dualCircleLayout(count=None, field="degree"):
        """dualCircleLayout(count) puts the `count` nodes with the highest value
        of field (default degree) on an inner circle and everyone else on an
        outer circle, each outer node near the inner nodes it links to (Gephi's
        Dual Circle Layout). count defaults to the square root of the number of
        nodes."""
        fld = _node_field(graph(), field, "dualCircleLayout")
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        k = max(1, int(round(math.sqrt(s.n)))) if count is None else int(count)
        if not 0 < k <= s.n:
            raise GuessError(f"dualCircleLayout(count): count should be between 1 and {s.n}")
        v = np.array([_num(x, -np.inf) for x in _values(fld, s)])
        order = sorted(range(s.n), key=lambda i: (-v[i], i))
        inner, outer = order[:k], order[k:]
        diam = _diam(s)
        d = float(diam.max()) * 1.4
        r1 = max(k * d / (2 * math.pi), 2 * d if k > 1 else 0.0)
        r2 = max(len(outer) * d / (2 * math.pi), r1 * 2, r1 + 3 * d)
        cx = cy = BOX / 2
        P = s.pos.copy()
        Q = _ring_positions(k, r1, cx, cy)
        ang = {}
        for p, i in enumerate(inner):
            P[i] = Q[p] - s.size[i] / 2
            ang[i] = math.atan2(Q[p][1] - cy, Q[p][0] - cx)
        key = []
        for i in outer:
            nb = [x for x in s.neighbors(i) if x in ang]
            if nb:
                a = math.atan2(sum(math.sin(ang[x]) for x in nb), sum(math.cos(ang[x]) for x in nb))
            else:
                a = 10.0                          # unconnected to the hubs: together at the end
            key.append((a, -v[i], i))
        key.sort()
        start = key[0][0] if key and key[0][0] < 10 else -math.pi / 2
        Q = _ring_positions(len(outer), r2, cx, cy, start=start)
        for p, (_, _, i) in enumerate(key):
            P[i] = Q[p] - s.size[i] / 2
        lay.apply(s, P)

    # ---- ordered -----------------------------------------------------------------
    @cmd
    def orderedLayout(field, axis="x", iterations=None, inverted=False, length=1000, gravity=1.0):
        """orderedLayout(field) fixes each node's position on one axis by a
        numeric field (a year, a step, an order) and runs a ForceAtlas2 force
        on the other axis only, so connected nodes come together without
        breaking the order (Gephi's Ordered Layout and EventGraphLayout).
        axis="y" orders from top to bottom; inverted=true reverses; length is
        the span of the ordered axis. Nodes without a value go in the middle."""
        fld = _node_field(graph(), field, "orderedLayout")
        ax = str(axis).lower()
        if ax not in ("x", "y"):
            raise GuessError('orderedLayout axis is "x" or "y"')
        lock = 0 if ax == "x" else 1
        free = 1 - lock
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        v = np.array([_num(x, np.nan) for x in _values(fld, s)])
        if not np.isfinite(v).any():
            raise GuessError(f"{fld.name} has no numbers to order by")
        lo, hi = np.nanmin(v), np.nanmax(v)
        t = np.where(np.isfinite(v), (v - lo) / ((hi - lo) or 1), 0.5)
        if inverted:
            t = 1 - t
        half = s.size / 2
        pos = s.pos.copy()
        pos[:, lock] = BOX / 2 - float(length) / 2 + t * float(length) - half[:, lock]
        # a free axis with no spread can't separate nodes: start from a random spread
        mov = ~s.fixed
        if mov.any() and np.ptp(pos[mov, free]) < 1:
            r = np.random.default_rng(0)
            pos[mov, free] = BOX / 2 + r.uniform(-BOX / 4, BOX / 4, int(mov.sum()))
        pos[s.fixed] = s.pos[s.fixed]
        s.pos = pos
        k = _iters(iterations, _scaled(400, s.n))
        target = pos[:, lock].copy()

        def pinned():
            # the force never moves the ordered axis, but the start's nudge of
            # coincident nodes and float rounding can: put it back exactly
            for P in _fa2_gen(s, k, np.random.default_rng(0), gravity=float(gravity), lock=lock):
                P = P.copy()
                P[mov, lock] = target[mov]
                yield P
        lay.run(s, pinned())

    # ---- Hairball Buster -------------------------------------------------------
    @cmd
    def hairballLayout(neighbors=True, logX=False, logY=False, width=1000, height=1000):
        """hairballLayout() draws a Hairball Buster plot (node-neighbour
        centrality, Matties et al., JHU/APL): nodes sorted by degree, the
        busiest on the left, each at x = its rank and y = its degree (upwards),
        with a short tick, level with each node, under the rank of every one of
        its neighbours, so each row of ticks shows who a node is tied to. Hubs
        tied mostly to hubs, to leaves, or to a clique stand out at a glance,
        and two graphs can be compared plot to plot. Edges are left as they are:
        g.edges.visible = false shows the plot alone. neighbors=false leaves
        out the ticks (drawn for up to 5000 edges); logX/logY use log scales.
        Any later layout removes the axes and ticks."""
        gr = graph()
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        dfield = gr.node_schema["degree"]
        deg = np.array([_num(dfield.get(nd), 0) for nd in s.nodes])
        order = sorted(range(s.n), key=lambda i: (-deg[i], i))
        rank = np.empty(s.n)
        for p, i in enumerate(order):
            rank[i] = p
        W, H = float(width), float(height)
        xs = np.log10(rank + 1) / (math.log10(s.n) or 1) if logX else rank / max(s.n - 1, 1)
        top = deg.max() or 1
        ys = np.log10(deg + 1) / math.log10(top + 1) if logY else deg / top
        X, Y = xs * W, H - ys * H
        P = np.stack([X, Y], 1) - s.size / 2
        lay.apply(s, P)
        guides = [{"x1": 0.0, "y1": H, "x2": W + 20, "y2": H, "label": "rank by degree"},
                  {"x1": 0.0, "y1": H, "x2": 0.0, "y2": -20.0, "label": f"degree (max {int(top)})"}]
        pairs = s.pairs
        if neighbors and len(pairs) and len(pairs) <= 5000:
            tick = max(3.0, min(12.0, 0.6 * H / max(top, 1)))
            for a, b in pairs.tolist():
                for me, other in ((a, b), (b, a)):
                    guides.append({"x1": X[other], "y1": Y[me] - tick / 2, "x2": X[other], "y2": Y[me] + tick / 2,
                                   "label": ""})
        set_guides(guides)

    # ---- circle packing ------------------------------------------------------------
    @cmd
    def circlePackLayout(*fields, padding=4, outlines=True):
        """circlePackLayout(field) packs the nodes as circles inside one circle
        per value of a field; circlePackLayout(field1, field2, ...) nests them
        (each value of field2 a circle inside its field1 circle, and so on). Each
        node keeps its size, so nothing overlaps; padding is the gap between
        circles. The group circles are drawn and labelled (outlines=false
        leaves them out); any later layout removes them. Without a field all
        nodes are packed into one circle. (Bostock's d3 circle packing.)"""
        gr = graph()
        flds = [_node_field(gr, f, "circlePackLayout") for f in fields]
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        pad = float(padding)
        rnd = random.Random(0)
        vals = [_values(f, s) for f in flds]
        leaves = [_C(float(max(s.size[i])) / 2 + pad / 2) for i in range(s.n)]

        groups = []        # (depth, label, circle) for the outlines

        def build(idx, depth):
            """Pack the nodes idx by fields[depth:]; returns a circle whose
            children have positions relative to it."""
            if depth == len(flds):
                kids = sorted(idx, key=lambda i: (-leaves[i].r, i))
                circles = [leaves[i] for i in kids]
                r = _pack_siblings(circles, rnd)
                return _Group(r + pad, [(leaves[i], i) for i in kids])
            by = {}
            for i in idx:
                by.setdefault(_sort_key(vals[depth][i]), []).append(i)
            children = []
            for key in sorted(by):
                sub = build(by[key], depth + 1)
                sub.label = "" if key[0] == 2 else (str(vals[depth][by[key][0]]))
                sub.depth = depth
                children.append(sub)
            children.sort(key=lambda c: -c.r)
            circles = [c.circle for c in children]
            r = _pack_siblings(circles, rnd)
            return _Group(r + pad, children)

        root = build(list(range(s.n)), 0)
        P = s.pos.copy()
        guides = []

        def place(grp, ox, oy):
            for item in grp.children:
                if isinstance(item, tuple):
                    c, i = item
                    P[i] = (ox + c.x, oy + c.y) - s.size[i] / 2
                else:
                    cx, cy = ox + item.circle.x, oy + item.circle.y
                    groups.append((item.depth, item.label, cx, cy, item.circle.r))
                    place(item, cx, cy)

        place(root, BOX / 2, BOX / 2)
        lay.apply(s, P)
        if outlines and flds and len(groups) <= 300:
            segs = 48 if len(groups) <= 60 else 24
            for depth, label, cx, cy, r in groups:
                guides += _circle_guides(cx, cy, r - pad / 2, segs)
                if label and len(groups) <= 120:
                    guides.append(_label_guide(cx, cy - r - 10, label))
            set_guides(guides, " / ".join(f.name for f in flds))

    # ---- isometric layers ------------------------------------------------------------
    @cmd
    def isometricLayout(field, layers=None, angle=30, gap=None):
        """isometricLayout(field) stacks the graph in layers by a node field and
        shows them at an angle, as planes one above the other: each layer keeps
        the current layout's shape, squashed into a diamond, the lowest value at
        the bottom (Gephi's Isometric Layout and Network Splitter 3D). Edges
        between layers run between the planes. A text field gives one layer per
        value; a numeric field with many values is cut into `layers` equal
        ranges (default 5). angle tilts the planes (30 = isometric; smaller is
        flatter); gap is the distance between layers. The layer number goes in
        the zlayer field, and the planes are outlined; run it again to change
        the field or angle without compounding. Any other layout removes the
        outlines."""
        gr = graph()
        fld = _node_field(gr, field, "isometricLayout")
        a = math.radians(float(angle))
        if not 0 < a < math.pi / 2:
            raise GuessError("isometricLayout angle should be between 0 and 90 degrees")
        s = lay.snap()
        if s.n == 0:
            return lay.finish()
        vals = _values(fld, s)
        nl = 5 if layers is None else int(layers)
        if nl < 1:
            raise GuessError("isometricLayout needs at least one layer")
        distinct = sorted({_sort_key(v) for v in vals})
        if _numeric(vals) and len(distinct) > nl:
            num = np.array([np.nan if v is None else float(v) for v in vals])
            lo, hi = np.nanmin(num), np.nanmax(num)
            z = np.where(np.isnan(num), 0, np.minimum(((num - lo) / ((hi - lo) or 1) * nl).astype(int), nl - 1))
            step = (hi - lo) / nl
            names = [f"{lo + k * step:.3g}–{lo + (k + 1) * step:.3g}" for k in range(nl)]
        else:
            pos = {d: i for i, d in enumerate(distinct)}
            z = np.array([pos[_sort_key(v)] for v in vals])
            names = ["(none)" if d[0] == 2 else str(next(v for v in vals if _sort_key(v) == d)) for d in distinct]
        # the plane positions: the last isometricLayout's, if nothing has moved since
        centre = s.pos + s.size / 2
        prev = state["iso"]
        plane = centre.copy()
        if prev is not None:
            for i, nd in enumerate(s.nodes):
                rec = prev.get(nd._id)
                if rec is not None and abs(rec[2] - centre[i, 0]) < 1e-6 and abs(rec[3] - centre[i, 1]) < 1e-6:
                    plane[i] = rec[:2]
        mid = (plane.min(0) + plane.max(0)) / 2
        u, v = plane[:, 0] - mid[0], plane[:, 1] - mid[1]
        rh = (np.ptp(u) + np.ptp(v)) * math.sin(a)     # height of one plane (a diamond) on screen
        nz = int(z.max()) + 1 if len(z) else 1
        # planes overlap a little; many layers share about three planes' height
        g_ = float(gap) if gap is not None else max(rh, 1.0) * min(0.75, 2.0 / max(nz - 1, 1))
        X = (u - v) * math.cos(a)
        Y = (u + v) * math.sin(a) - z * g_
        out = np.stack([X + BOX / 2, Y + BOX / 2], 1)
        lay.apply(s, out - s.size / 2)
        f = gr.addNodeField("zlayer", INT, -1)
        for i, nd in enumerate(s.nodes):
            f.set(nd, int(z[i]))
        state["iso"] = {nd._id: (plane[i, 0], plane[i, 1], out[i, 0], out[i, 1]) for i, nd in enumerate(s.nodes)}
        # outline each plane: the projected square around the layout
        hu = np.ptp(plane[:, 0]) / 2 + 20
        hv = np.ptp(plane[:, 1]) / 2 + 20
        guides = []
        for k in sorted(set(z.tolist())):
            corners = [(-hu, -hv), (hu, -hv), (hu, hv), (-hu, hv)]
            pts = [((cu - cv) * math.cos(a) + BOX / 2, (cu + cv) * math.sin(a) - k * g_ + BOX / 2)
                   for cu, cv in corners]
            for j in range(4):
                (x1, y1), (x2, y2) = pts[j], pts[(j + 1) % 4]
                guides.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label": ""})
            rx, ry = pts[1]
            guides.append(_label_guide(rx + 30, ry, names[k] if k < len(names) else str(k)))
        set_guides(guides, f"layers: {fld.name}")


class _Group:
    """A packed group: its circle (radius r, position relative to its parent)
    and its children (groups, or (circle, node index) leaves)."""

    def __init__(self, r, children):
        self.circle = _C(r)
        self.children = children
        self.label = ""
        self.depth = 0

    @property
    def r(self):
        return self.circle.r


__all__ = ["install"]
