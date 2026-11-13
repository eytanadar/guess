"""ch16-si-in-time: SI on networks against the first-order, pair and degree-based theories."""
import math

import numpy as np

from tests.test_explainers import App


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_si_in_time_outbreak_theories_and_simulation():
    a = App("ch16-si-in-time")
    assert not a.errors(), a.errors()
    net = a.ev("net")
    assert set(net) == {"poisson", "hubs", "blogs", "lesmis"}
    for key, d in net.items():
        n = len(d["names"])
        # each kept to one connected piece, and kappa1 between <k> and sqrt(kmax) bounds
        assert d["kappa"] >= d["deg"].mean() - 1e-9 and d["kappa"] >= math.sqrt(d["deg"].max()) - 1e-9
        assert n > 50
    # a paced outbreak: nobody moves, infections only grow, each new case came along an edge from an infected node
    before = _positions(a)
    a.press("Start an outbreak")
    a.tick(3)
    sim = a.ev("sim")
    assert sim["times"] and sim["t"] > 0
    names = net["poisson"]["names"]
    nb = net["poisson"]["nbrs"]
    idx = net["poisson"]["idx"]
    for v, p in sim["parent"].items():
        if p is not None:
            assert idx[p] in nb[idx[v]] and sim["times"][p] < sim["times"][v]
    a.press("To the end")
    assert all(t <= a.ev("sim")["t"] for t in a.ev("sim")["times"].values())
    assert _positions(a) == before
    assert "infected" in a.markdown()
    # theories: all start near 1/n and end near 1; first-order runs ahead of the pair approximation
    th = a.ev("solve_all('poisson', 1.0, 6)")
    n = len(names)
    for name, pts in th.items():
        assert abs(pts[0][1] - 6 / n) < 1e-6 and pts[-1][1] > 0.95, name   # starts at c/n, c = 6
    mid = len(th["first-order"]) // 6
    assert th["first-order"][mid][1] >= th["pair approximation"][mid][1] - 1e-9
    # simulate: the average lies closest to the pair approximation on a locally tree-like network
    a.tab("Theory and simulation")
    a.press("Simulate: average 40 outbreaks")
    a.tick(20)
    curve, rec = a.ev("averaged()")
    assert rec["runs"] == 40
    errs = {k: a.ev(f"error_of(averaged()[0], solve_all('poisson', 1.0, 6)[{k!r}])")
            for k in ("fully mixed", "first-order", "pair approximation", "degree-based")}
    assert errs["pair approximation"] < errs["first-order"] and errs["pair approximation"] < 0.06
    assert "Closest here" in a.markdown()
    # early growth: first-order reaches 10% first; the simulated average is nearest the pair approximation
    a.tab("Early growth")
    times = a.ev("gap_at_10('poisson', 1.0)")
    assert times["first-order"] <= min(times.values()) + 1e-9
    sim_t = times["simulated average"]
    assert abs(sim_t - times["pair approximation"]) < abs(sim_t - times["first-order"])
    assert "time to reach" in a.markdown()
    # who first: central nodes are infected earlier
    a.tab("Who is infected first")
    rec = a.ev("sim['avg'][sim_key()]")
    mt = rec["tsum"] / rec["runs"]
    v1 = net["poisson"]["v1"]
    assert np.corrcoef(np.argsort(np.argsort(v1)), np.argsort(np.argsort(mt)))[0, 1] < -0.3
    assert "rank correlation" in a.markdown()
    assert not a.errors(), a.errors()


def test_si_in_time_clustered_network_and_switching():
    a = App("ch16-si-in-time")
    a.set("dropdown", "Network", "Les Misérables (many triangles)")
    assert a.ev("sim['key']") == "lesmis"
    a.tab("Theory and simulation")
    a.press("Simulate: average 40 outbreaks")
    a.tick(20)
    th = a.ev("solve_all('lesmis', 1.0, 6)")
    curve = a.ev("averaged()[0]")
    e1 = a.ev("error_of(averaged()[0], solve_all('lesmis', 1.0, 6)['first-order'])")
    e2 = a.ev("error_of(averaged()[0], solve_all('lesmis', 1.0, 6)['pair approximation'])")
    assert e2 < e1                                   # triangles: first-order is far off, pair much closer
    assert "triangles" in a.markdown()
    a.set("dropdown", "Network", "A few hubs (power-law degrees)")
    a.tab("Outbreak")
    a.click(a.ev("net['hubs']['names'][0]"))
    assert a.ev("sim['seed']") == a.ev("net['hubs']['names'][0]")
    assert not a.errors(), a.errors()
