"""Batch 7 explainers: excess degree and the friendship paradox, and the giant component in the configuration model."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401  (the fixture runs in the data folder)


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_excess_degree():
    a = App("ch12-excess-degree")
    G = a.ev("net['G']")
    k = dict(G.degree())
    mean = sum(k.values()) / len(k)
    k2 = sum(x * x for x in k.values()) / len(k)
    assert f"**⟨k⟩ = {mean:.2f}**" in a.markdown() and f"**⟨k²⟩/⟨k⟩ = {k2 / mean:.2f}**" in a.markdown()
    a.press("Follow random edges")
    a.tick(10)
    assert a.ev("walk['total']") == 10
    came, end = a.ev("walk['last']")
    assert a.node(end).strokewidth == 3 and G.has_edge(came, end)
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())        # the edge just followed
    a.press("2,000 at once")
    got = a.ev("sum(net['k'][v] * c for v, c in walk['counts'].items()) / walk['total']")
    assert abs(got - k2 / mean) < 0.12 * k2 / mean                            # nodes reached along edges: <k^2>/<k>
    assert len(a.ev("walk_chart()")._id) > 0

    _tab(a, "Friendship paradox")
    a.click("Valjean")
    nb = list(G["Valjean"])
    assert f"**Valjean** has **{len(nb)}** friends" in a.markdown() and "(guess:n" in a.markdown()
    assert a.node("Valjean").strokewidth == 4
    a.press("Compare the networks")
    a.tick(10)
    assert len(a.ev("compare['rows']")) == 7 and "| Karate club |" in a.markdown()
    assert a.ev("paradox_chart()") is not None

    _tab(a, "Second neighbours")
    a.click("Valjean")
    assert "first neighbours (orange)" in a.markdown()
    assert nx.transitivity(G) > 0 and f"| this network | {nx.transitivity(G):.3f} |" in a.markdown()
    a.press("Wire at random")
    assert a.ev("net['random']") and "random rewiring" in a.markdown()
    a.press("Simulate: bigger networks")
    a.tick(8)
    rows = a.ev("sim['rows']")
    assert len(rows) == 6 and rows[-1][1] < rows[0][1]                        # clustering falls as n grows
    assert abs(rows[-1][1] - rows[-1][2]) < 0.5 * rows[-1][2]                  # and follows the formula
    a.press("Real network")
    assert not a.ev("net['random']")
    a.set("dropdown", "Network", "Power grid region (400 stations)")
    assert a.ev("net['n']") == 400


def test_giant_component_configuration_model():
    a = App("ch12-giant-component")
    assert "**giant component**" in a.markdown() and "u = p₁/3p₃ = **0.333**" in a.markdown()
    assert abs(a.ev("shown['S']") - a.ev("theory13(0.5)[1]")) < 0.1
    a.set("slider", "share of degree-3", 20)
    assert "no giant component" in a.markdown() and a.ev("shown['S']") < 0.2
    a.set("slider", "share of degree-3", 80)
    assert a.ev("shown['S']") > 0.9
    assert all(v.strokewidth > 1 for v in a.s.graph._nodes_list() if v._name in a.ev("shown['giant']"))
    a.press("Simulate: sweep p₃")
    a.tick(45)
    rows = a.ev("sweep13['rows']")
    assert len(rows) == 40 and rows[(3000, 0.1)] < 0.05 and rows[(3000, 0.8)] > 0.9

    _tab(a, "Solve u = g₁(u)")
    a.press("Iterate u ← g₁(u)")
    a.tick(30)
    us = a.ev("cob['u']")
    assert us[0] == 0 and abs(us[-1] - a.ev("theory13(0.8)[0]")) < 1e-4
    assert all(x <= y + 1e-12 for x, y in zip(us, us[1:]))                    # the staircase climbs
    assert a.ev("cob_chart()") is not None

    _tab(a, "Power laws")
    assert a.ev("shown['kind']") == "pl" and "always a giant component" in a.markdown()
    assert a.ev("theory_pl(2.5)[1]") > 0.5 and a.ev("theory_pl(3.6)[1]") < 1e-3   # threshold near alpha = 3.48
    a.press("Simulate: sweep α")
    a.tick(25)
    rows = a.ev("sweeppl['rows']")
    assert rows[(5000, 2.1)] > rows[(5000, 3.9)]

    _tab(a, "Diameter")
    a.press("Simulate: growing networks")
    a.tick(20)
    rows = a.ev("dist['rows']")
    assert len(rows) == 14
    d13 = [d for kd, n, d in rows if kd == "13"]
    assert d13[-1] > d13[0] + 4                                              # grows like log n
    assert a.ev("dist_chart()") is not None and "| 6400 |" in a.markdown()
