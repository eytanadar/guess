"""Batch 7 explainers: the random graph, and the giant component."""
import math

import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_random_graph_builds_edge_by_edge_on_fixed_nodes():
    a = App("ch11-random-graph")
    edges = a.ev("st['edges']")
    assert a.ev("len([e for e in g.edges if e.visible])") == 0 and len(a.s.graph._nodes_list()) == 50
    before = _positions(a)
    a.press("Add edges one at a time")
    a.tick(6)
    shown = [e for e in a.s.graph._edges_list() if e.visible]
    assert len(shown) == a.ev("st['k']") == 6
    assert sum(1 for e in shown if e.linestyle == "flow") == 1          # the newest edge, highlighted
    a.press("Show all edges")
    assert a.ev("len([e for e in g.edges if e.visible])") == len(edges)
    assert _positions(a) == before                                      # nobody moved
    assert "mean degree so far" in a.markdown()
    # G(n, m): exactly round(c n / 2) edges
    a.set("dropdown", "Model", "G(n, m)")
    assert len(a.ev("st['edges']")) == 75
    # degrees: the chart has the data and both formulas; the simulation pools 100 graphs
    a.press("Show all edges")
    _tab(a, "Degrees")
    assert a.ev("degree_chart()") is not None
    a.press("Simulate: 100 graphs of 1000 nodes")
    a.tick(25)
    sim = a.ev("st['sim']")
    assert sim["graphs"] == 100
    tot = sum(sim["hist"].values())
    mean = sum(k * v for k, v in sim["hist"].items()) / tot
    assert abs(mean - 3) < 0.1 and "**Simulated:**" in a.markdown()
    # clustering: the real network beats random graphs of the same size
    _tab(a, "Clustering")
    md = a.markdown()
    assert "Les Misérables" in md and "c/(n−1)" in md
    r = a.ev("real_stats(real_choice[0])")
    assert r["n"] == 77 and r["m"] == 254 and r["C"] > 3 * r["Crand"]
    a.set("dropdown", "Real network", "Karate club (34 people)")
    assert "Karate" in a.markdown()
    a.press("Simulate: C as n grows")
    a.tick(8)
    rows = a.ev("st['csim']")
    assert len(rows) == 7 and rows[-1][1] < rows[0][1] and a.ev("c_chart()") is not None


def test_giant_component_appears_past_c_1():
    a = App("ch11-giant-component")
    before = _positions(a)
    assert abs(a.ev("theory_S(2)") - 0.7968) < 1e-3 and a.ev("theory_S(0.9)") == 0
    a.press("Sweep c from 0 to 4")
    a.tick(90)
    seen = a.ev("st['seen']")
    assert len(seen) == 81 and seen[4.0][0] > 0.9 and seen[0.5][0] < 0.2
    assert _positions(a) == before                                      # revealed in place
    # the visible edges are exactly those whose threshold has been reached
    c = a.ev("st['c']")
    assert all(e.visible == (e.born <= c) for e in a.s.graph._edges_list())
    # the largest component in the drawing matches networkx on the visible edges
    G = nx.Graph()
    G.add_nodes_from(v._name for v in a.s.graph._nodes_list())
    G.add_edges_from((e._n1._name, e._n2._name) for e in a.s.graph._edges_list() if e.visible)
    giant = max(nx.connected_components(G), key=len)
    assert sum(1 for v in a.s.graph._nodes_list() if v.color == "250,160,50") == len(giant)
    assert "theory for n → ∞" in a.markdown() and a.ev("transition_chart()") is not None
    _tab(a, "Simulate")
    a.press("Simulate: 100 and 3,000 nodes")
    a.tick(35)
    rows = a.ev("st['sim']")
    assert len(rows) == 31
    at2 = next(r for r in rows if abs(r[0] - 2) < 1e-9)
    assert abs(at2[2] - a.ev("theory_S(2)")) < 0.05                     # n = 3000 is close to the theory
    _tab(a, "Solving for S")
    a.call("show(2.0)")
    a.press("Iterate S ← 1 − e^(−cS)")
    a.tick(30)
    cob = a.ev("st['cob']")
    assert cob[0] == 0.02 and abs(cob[-1] - a.ev("theory_S(2)")) < 1e-3 and a.ev("cob_chart()") is not None
    _tab(a, "Only one giant")
    assert "1,000,000" in a.markdown()
