"""Batch 7 explainers: small components, and path lengths in random graphs."""
import math

import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_small_components():
    a = App("ch11-small-components")
    G = a.ev("world['G']")
    assert len(G) == 250 and len(a.s.graph._nodes) == 250
    # the giant component (c = 1.5) is blue; every small component is a tree here
    big = max(nx.connected_components(G), key=len)
    assert a.ev("world['giant']") == set(big)
    assert all(G.subgraph(c).number_of_edges() == len(c) - 1 for c in nx.connected_components(G) if c != big)
    assert "are trees" in a.markdown()
    # theory: S solves S = 1 - e^{-cS}; pi_s sums to 1 - S
    S = a.ev("giant_S(1.5)")
    assert abs(S - (1 - math.exp(-1.5 * S))) < 1e-9 and a.ev("giant_S(0.8)") == 0
    assert abs(sum(a.ev(f"pi_s(1.5, {s})") for s in range(1, 400)) - (1 - S)) < 1e-3
    assert abs(a.ev("mean_small(0.5)") - 2.0) < 1e-9
    # components are packed apart: no two nodes on top of each other
    pts = [(n.x, n.y) for n in a.s.graph._nodes_list()]
    assert len(set((round(x), round(y)) for x, y in pts)) == len(pts)
    # clicking outlines the clicked node's component and counts its edges
    small = next(c for c in nx.connected_components(G) if c != big and len(c) >= 2)
    v = sorted(small)[0]
    a.click(v)
    assert a.node(v).strokewidth == 3 and f"**{len(small)}** nodes and **{len(small) - 1}** edges: a tree" in a.markdown()
    assert a.ev("screen_chart()") is not None
    # a new c rebuilds; below 1 there is no giant component
    a.set("slider", "mean degree c", 0.6)
    assert a.ev("world['giant']") == set() and "no giant component" in a.markdown()
    a.set("slider", "mean degree c", 1.5)
    _tab(a, "Size distribution")
    a.press("Simulate: 40 graphs")
    a.tick(41)
    assert a.ev("dist['runs']") == 40 and a.ev("dist_chart()") is not None
    outside = sum(a.ev("dist['count']").values()) / (2000 * 40)
    assert abs(outside - (1 - S)) < 0.03
    _tab(a, "Mean size")
    a.press("Simulate: sweep c")
    a.tick(30)
    rows = a.ev("sweep['rows']")
    assert len(rows) == 29
    peak = max(rows, key=lambda r: r[1])
    assert 0.8 <= peak[0] <= 1.3                     # the spike sits near c = 1
    low = next(r for r in rows if r[0] == 0.5)
    assert abs(low[1] - 2.0) < 0.3                   # 1 / (1 - c) at c = 0.5
    assert a.ev("mean_chart()") is not None and a.ev("S_chart()") is not None


def test_path_lengths():
    a = App("ch11-path-lengths")
    G = a.ev("rg['G']")
    assert len(G) == 400
    start = sorted(max(nx.connected_components(G), key=len))[0]
    a.click(start)
    a.press("Grow the ball")
    dist = nx.single_source_shortest_path_length(G, start)
    a.tick(max(dist.values()) + 1)
    assert a.ev("ring['layer']") == max(dist.values())
    assert a.node(start).strokewidth == 4
    counts = a.ev("ring_counts()")
    assert counts[1] == G.degree(start) and sum(counts.values()) == len(dist)
    assert "| 1 |" in a.markdown() and a.ev("ring_chart()") is not None
    _tab(a, "Grows like ln n")
    a.press("Simulate: n from 50 to 3,200")
    a.tick(15)
    rows = a.ev("grow['rows']")
    assert len(rows) == 14
    ell = {(n, c): e for n, c, e, _ in rows}
    assert ell[(3200, 3.0)] > ell[(50, 3.0)] and ell[(3200, 6.0)] < ell[(3200, 3.0)]
    # roughly ln n / ln c at the largest size
    assert abs(ell[(3200, 3.0)] - math.log(3200) / math.log(3)) < 1.0
    assert a.ev("grow_chart()") is not None
    _tab(a, "What's missing")
    assert "clustering C" in a.markdown() and a.ev("missing_chart()") is not None
    real, twin = a.ev("STATS['Les Misérables']")
    assert real["C"] > 3 * twin["C"] and real["kmax"] > twin["kmax"]
    a.set("dropdown", "Show", "Its random twin")
    assert all(n._name.startswith("r") for n in a.s.graph._nodes_list())
    a.set("dropdown", "Network", "Karate club")
    assert len(a.s.graph._nodes) == 34
    _tab(a, "Rings")
    assert len(a.s.graph._nodes) == 400
