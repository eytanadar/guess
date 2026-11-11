"""Tests for guess.morelayouts and the Gephi-plugin options added to layouts.py
(rescaleLayout(nodes, ...), forceAtlas2Layout(gravitySources=...))."""
import math

import numpy as np
import pytest

from guess import Session
from tests.test_gython import SAMPLE, Recorder


@pytest.fixture
def g():
    rec = Recorder()
    sess = Session(rec)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    sess.rec = rec
    return sess


def centres(s, nodes=None):
    nodes = list(s.graph._nodes_list()) if nodes is None else nodes
    return {n._name: (n.x + n.width / 2, n.y + n.height / 2) for n in nodes}


def run(s, code):
    ok = s.run(code)
    assert ok, s.rec.of("error")[-1:] if s.rec.of("error") else code


def error(s, code):
    s.rec.clear()
    assert not s.run(code)
    return s.rec.of("error")[-1]["text"]


def test_multipartite_columns_share_x_and_are_in_value_order(g):
    run(g, "multipartiteLayout(dept)")
    by = {}
    for n in g.graph._nodes_list():
        by.setdefault(n.dept, set()).add(round(n.x + n.width / 2, 6))
    assert all(len(xs) == 1 for xs in by.values())
    xs = [next(iter(by[d])) for d in sorted(by)]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)
    run(g, "multipartiteLayout(dept, vertical=true)")
    ys = {}
    for n in g.graph._nodes_list():
        ys.setdefault(n.dept, set()).add(round(n.y + n.height / 2, 6))
    assert all(len(v) == 1 for v in ys.values())


def test_multipartite_reduces_crossings_against_a_shuffled_order(g):
    run(g, "makeSample('davis')")
    run(g, "randomLayout()")
    run(g, "multipartiteLayout(bipartite)")

    def crossings():
        es = []
        for e in g.graph._edges_list():
            a, b = e._n1, e._n2
            if a.bipartite > b.bipartite:
                a, b = b, a
            es.append((a.y, b.y))
        c = 0
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                c += (es[i][0] - es[j][0]) * (es[i][1] - es[j][1]) < 0
        return c
    ordered = crossings()
    rng = np.random.default_rng(1)
    for n in g.graph._nodes_list():          # same columns, rows shuffled
        n.y = float(rng.uniform(0, 1000))
    assert ordered < crossings()


def test_concentric_rings_by_value_highest_inside(g):
    run(g, "concentricLayout(dept)")
    c = centres(g)
    r = {}
    for n in g.graph._nodes_list():
        x, y = c[n._name]
        r.setdefault(n.dept, []).append(math.hypot(x - 500, y - 500))
    for d, rs in r.items():
        assert max(rs) - min(rs) < 1e-6, d
    radii = [r[d][0] for d in sorted(r)]
    assert radii == sorted(radii)          # text values in order, outward
    run(g, "concentricLayout(degree, 4)")
    c = centres(g)
    top = max(g.graph._nodes_list(), key=lambda n: n.degree)
    low = min(g.graph._nodes_list(), key=lambda n: n.degree)
    assert math.hypot(c[top._name][0] - 500, c[top._name][1] - 500) < math.hypot(c[low._name][0] - 500, c[low._name][1] - 500)


def test_concentric_ring_fits_its_nodes(g):
    run(g, "concentricLayout(dept)")
    c = centres(g)
    pts = np.array([c[n._name] for n in g.graph._nodes_list() if n.dept == "dept1"])
    d = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
    np.fill_diagonal(d, np.inf)
    assert d.min() >= 10 - 1e-6          # node width 10: no overlaps on the ring


def test_dual_circle(g):
    run(g, "dualCircleLayout(10)")
    nodes = sorted(g.graph._nodes_list(), key=lambda n: (-n.degree, n._id))
    c = centres(g)
    r = [math.hypot(c[n._name][0] - 500, c[n._name][1] - 500) for n in nodes]
    assert max(r[:10]) - min(r[:10]) < 1e-6
    assert max(r[10:]) - min(r[10:]) < 1e-6
    assert r[0] < r[10]
    assert "count" in error(g, "dualCircleLayout(0)")


def test_ordered_layout_fixes_one_axis(g):
    run(g, "orderedLayout(degree, iterations=40)")
    nodes = g.graph._nodes_list()
    lo = min(n.degree for n in nodes)
    hi = max(n.degree for n in nodes)
    for n in nodes:
        assert abs((n.x + n.width / 2) - (n.degree - lo) / (hi - lo) * 1000) < 1e-6
    ys = [n.y for n in nodes]
    assert np.ptp(ys) > 50                # the free axis spread out
    run(g, "orderedLayout(degree, axis='y', inverted=true, iterations=10)")
    for n in nodes:
        assert abs((n.y + n.height / 2) - (1 - (n.degree - lo) / (hi - lo)) * 1000) < 1e-6
    assert "edge" in error(g, "orderedLayout(freq)") or "node" in error(g, "orderedLayout(freq)")
    assert '"x" or "y"' in error(g, "orderedLayout(degree, axis='z')")


def test_ordered_layout_leaves_fixed_nodes(g):
    run(g, "v1.fixed = true\nv1.x = 3\nv1.y = 4")
    run(g, "orderedLayout(degree, iterations=5)")
    assert (g.graph._nodes["v1"].x, g.graph._nodes["v1"].y) == (3, 4)


def test_hairball_plot(g):
    run(g, "hairballLayout()")
    nodes = sorted(g.graph._nodes_list(), key=lambda n: (-n.degree, n._id))
    c = centres(g)
    xs = [c[n._name][0] for n in nodes]
    assert xs == sorted(xs)                              # busiest on the left
    top = nodes[0]
    assert c[top._name][1] == pytest.approx(0)           # highest degree at the top
    assert c[nodes[-1]._name][1] == pytest.approx(1000 - nodes[-1].degree / top.degree * 1000)
    edges = len({frozenset((e._n1._id, e._n2._id)) for e in g.graph._edges_list() if e._n1 is not e._n2})
    assert len(g.view.guides) == 2 + 2 * edges            # two axes, a tick per neighbour
    run(g, "hairballLayout(neighbors=false)")
    assert len(g.view.guides) == 2
    run(g, "gemLayout(3)")
    assert g.view.guides == []                           # another layout clears it


def test_circle_pack_no_overlap_and_groups_together(g):
    for code in ("circlePackLayout()", "circlePackLayout(dept)", "circlePackLayout(dept, degree, padding=2)"):
        run(g, code)
        nodes = g.graph._nodes_list()
        c = np.array([centres(g, [n])[n._name] for n in nodes])
        r = np.array([max(n.width, n.height) / 2 for n in nodes])
        d = np.hypot(*(c[:, None, :] - c[None, :, :]).transpose(2, 0, 1))
        np.fill_diagonal(d, np.inf)
        assert (d - r[:, None] - r[None, :] >= -1e-6).all(), code
    # the dept1 nodes lie within one circle that holds no one else
    run(g, "circlePackLayout(dept)")
    pts = {d: [] for d in {n.dept for n in g.graph._nodes_list()}}
    for n in g.graph._nodes_list():
        pts[n.dept].append(centres(g, [n])[n._name])
    m = np.array(pts["dept1"])
    mid = (m.min(0) + m.max(0)) / 2
    rad = np.hypot(*(m - mid).T).max()
    others = np.array([p for d, ps in pts.items() if d != "dept1" for p in ps])
    assert (np.hypot(*(others - mid).T) > rad).all()
    assert any(gd["label"] == "dept1" for gd in g.view.guides)


def test_circle_pack_siblings_matches_known_properties():
    import random

    from guess.morelayouts import _C, _pack_siblings
    rnd = random.Random(0)
    for n in (1, 2, 3, 7, 40):
        cs = [_C(r) for r in np.random.default_rng(n).uniform(1, 10, n)]
        R = _pack_siblings(cs, rnd)
        for i, a in enumerate(cs):
            assert math.hypot(a.x, a.y) + a.r <= R + 1e-6       # all inside the enclosing circle
            for b in cs[i + 1:]:
                assert math.hypot(a.x - b.x, a.y - b.y) >= a.r + b.r - 1e-6


def test_isometric_layers(g):
    run(g, "gemLayout(3)")
    run(g, "isometricLayout(dept)")
    nodes = g.graph._nodes_list()
    depts = sorted({n.dept for n in nodes})
    assert {n.zlayer for n in nodes} == set(range(len(depts)))
    for n in nodes:
        assert n.zlayer == depts.index(n.dept)
    # the planes stack upwards: each layer's outline (and label) is higher on screen
    labels = [gd for gd in g.view.guides if gd["label"]]
    assert [gd["label"] for gd in labels] == depts
    ys = [gd["y1"] for gd in labels]
    assert ys == sorted(ys, reverse=True) and len(set(ys)) == len(ys)
    # a node's position is its plane position projected, raised by its layer
    a = math.radians(30)
    gap = labels[0]["y1"] - labels[1]["y1"]
    for n in nodes:
        x, y = n.x + n.width / 2, n.y + n.height / 2
        u_minus_v = (x - 500) / math.cos(a)
        u_plus_v = (y - 500 + n.zlayer * gap) / math.sin(a)
        assert abs(u_minus_v) < 1e5 and abs(u_plus_v) < 1e5
    first = {n._name: (n.x, n.y) for n in nodes}
    run(g, "isometricLayout(dept)")                  # again: no compounding
    assert np.allclose([(n.x, n.y) for n in nodes], [first[n._name] for n in nodes])
    assert len(g.view.guides) == 5 * len(depts)
    run(g, "isometricLayout(degree, 3)")
    assert {n.zlayer for n in nodes} <= {0, 1, 2}
    assert "angle" in error(g, "isometricLayout(dept, angle=95)")


def test_undo_restores_positions(g):
    before = {n._name: (n.x, n.y) for n in g.graph._nodes_list()}
    for code in ("multipartiteLayout(dept)", "concentricLayout(dept)", "dualCircleLayout()",
                 "orderedLayout(degree, iterations=5)", "hairballLayout()", "circlePackLayout(dept)",
                 "isometricLayout(dept)"):
        run(g, code)
        run(g, "undo()")
        assert {n._name: (n.x, n.y) for n in g.graph._nodes_list()} == before, code


def test_errors_name_the_problem(g):
    assert "dpet" in error(g, "multipartiteLayout('dpet')")
    assert "ring" in error(g, "concentricLayout(dept, 0)")


def test_rescale_part_of_the_layout(g):
    run(g, "circleLayout()")
    part = [n for n in g.graph._nodes_list() if n.dept == "dept1"]
    rest = {n._name: (n.x, n.y) for n in g.graph._nodes_list() if n.dept != "dept1"}
    c0 = np.array(list(centres(g, part).values()))
    run(g, "rescaleLayout(dept == 'dept1', 2)")
    c1 = np.array(list(centres(g, part).values()))
    m0 = (c0.min(0) + c0.max(0)) / 2
    assert c1 - m0 == pytest.approx(2 * (c0 - m0))
    assert {n._name: (n.x, n.y) for n in g.graph._nodes_list() if n.dept != "dept1"} == rest
    run(g, "rescaleLayout(dept == 'dept1', 1, 0.5)")
    c2 = np.array(list(centres(g, part).values()))
    assert np.ptp(c2[:, 1]) == pytest.approx(np.ptp(c1[:, 1]) / 2)


def test_force_atlas_gravity_sources(g):
    run(g, "makeSample('karate')")
    run(g, "randomLayout()")
    run(g, "forceAtlas2Layout(iterations=300, gravity=5, gravitySources=[n0, n33])")
    c = centres(g)
    # each node ends up nearer the source it is closer to in hops, mostly
    import networkx as nx
    G = nx.Graph([(e._n1._name, e._n2._name) for e in g.graph._edges_list()])
    d1 = nx.single_source_shortest_path_length(G, "n0")
    d2 = nx.single_source_shortest_path_length(G, "n33")
    agree = total = 0
    for n in G:
        if n in ("n0", "n33") or d1[n] == d2[n]:
            continue
        near = "n0" if d1[n] < d2[n] else "n33"
        far = "n33" if near == "n0" else "n0"
        total += 1
        agree += math.dist(c[n], c[near]) < math.dist(c[n], c[far])
    assert agree / total > 0.8
    assert "gravitySources" in error(g, "forceAtlas2Layout(iterations=1, gravitySources=[])")

