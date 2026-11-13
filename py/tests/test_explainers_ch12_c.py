"""Batch 8 explainers: generating functions, and small component sizes from them."""
import numpy as np

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401  (the fixture runs in the data folder)


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_generating_functions():
    a = App("ch12-generating-functions")
    pk = a.ev("net['pk']")
    assert abs(a.ev("g0(1.0)") - 1) < 1e-9
    assert abs(a.ev("mean_k()") - 3) < 0.01                                   # Poisson, mean 3
    # g0(z): every node tested; the share that passes is near g0(z)
    a.press("Test all at once")
    z = a.ev("passing['z']")
    share = a.ev("passing['ok'] / passing['tested']")
    assert a.ev("passing['tested']") == 300 and abs(share - a.ev(f"g0({z})")) < 0.1
    assert share == 1 or any(str(e.color).startswith("230,60,50") for e in a.s.graph._edges_list())   # failed ends
    a.press("Test every node")
    a.tick(3)
    assert a.ev("passing['tested']") == 36 and a.ev("g0_chart()") is not None and a.ev("pk_chart()") is not None

    _tab(a, "Adding degrees")
    a.press("2,000 pairs at once")
    sums = a.ev("pairs['sums']")
    sq = np.convolve(pk, pk)
    assert abs(sum(s * c for s, c in sums.items()) / 2000 - 2 * float((np.arange(len(pk)) * pk).sum())) < 0.6
    a.press("Pick pairs of nodes")
    a.tick(2)
    assert a.ev("pairs['total']") == 2002 and "(guess:n" in a.markdown() and a.ev("pairs_chart()") is not None
    assert abs(sq.sum() - 1) < 1e-9

    _tab(a, "Excess degree g₁")
    q = a.ev("qk()")
    assert abs(q.sum() - 1) < 1e-9 and abs(q[2] - 3 * pk[3] / float((np.arange(len(pk)) * pk).sum())) < 1e-12
    a.press("Follow random edges")
    a.tick(3)
    came, at, exc = a.ev("walk['last']")
    assert a.node(at).strokewidth == 3 and any(e.linestyle == "flow" for e in a.s.graph._edges_list()) or exc == 0
    a.press("3,000 edges at once")
    k = a.ev("net['k']")
    mean_exc = sum(x * c for x, c in a.ev("walk['counts']").items()) / a.ev("walk['total']")
    m1 = sum(k.values()) / len(k)
    m2 = sum(v * v for v in k.values()) / len(k)
    assert abs(mean_exc - (m2 - m1) / m1) < 0.25                             # the network's own excess degree
    assert a.ev("walk_chart()") is not None

    _tab(a, "Second neighbours")
    a.press("Random node")
    assert "different second neighbours" in a.markdown()
    a.press("Count for every node")
    assert "the formula's value exactly" in a.markdown()
    coef = a.ev("compose(net['pk'], qk())")
    assert abs(float((np.arange(len(coef)) * coef).sum()) - (a.ev("mean_k2()") - a.ev("mean_k()"))) < 0.05
    a.click(a.s.graph._nodes_list()[0])
    assert a.ev("second['at']") == a.s.graph._nodes_list()[0]._name

    for choice in ["Exponential, mean 3", "Power law, α = 2.5 (k ≥ 1)", "Les Misérables (real network)",
                   "Power grid region (real network)"]:
        a.set("dropdown", "Degrees", choice)
        assert abs(a.ev("g0(1.0)") - 1) < 1e-9
    assert len(a.s.graph._nodes_list()) == 400                                # power grid region
    a.press("Count for every node")
    assert "is not random wiring" in a.markdown()


def test_small_component_sizes():
    a = App("ch12-small-component-sizes")
    th, pi, _h1 = a.ev("solution()")
    # Poisson with mean 1.5: S solves S = 1 - exp(-1.5 S)
    S = th["S"]
    assert abs(S - (1 - np.exp(-1.5 * S))) < 1e-6 and 0.55 < S < 0.6
    assert abs(pi[1:].sum() - (1 - S)) < 0.01                                # small components hold 1 - S
    assert abs(pi[1] - np.exp(-1.5)) < 1e-9                                  # an isolated node: p_0
    a.press("Iterate h₁ ← z g₁(h₁)")
    a.tick(3)
    assert a.ev("it['t']") == 3 and "Round **3**" in a.markdown()
    h0 = a.ev("times_z(compose(solution()[0]['pk'], it['h1']))")
    assert np.allclose(h0[1:4], pi[1:4])                                      # three rounds fix π1..π3
    a.tick(40)
    assert a.ev("it['t']") == 30

    _tab(a, "Against simulation")
    a.press("Simulate: 20 networks")
    a.tick(25)
    assert a.ev("sim['runs']") == 20
    small = a.ev("sum(sim['counts'].values()) / sim['nodes']")
    assert abs(small - (1 - S)) < 0.02
    big_comp = a.ev("shown['comps'][0][0]")
    a.click(big_comp)
    assert "giant component" in a.markdown()
    single = a.ev("[c[0] for c in shown['comps'] if len(c) == 2]")
    if single:
        a.click(single[0])
        assert "a **tree**" in a.markdown() and a.node(single[0]).strokewidth == 3

    _tab(a, "Mean size")
    a.press("Simulate: sweep ⟨k⟩")
    a.tick(20)
    pts = dict(a.ev("sweep['pts']"))
    assert len(pts) == 15 and pts[1.0] == max(pts.values())                   # the peak at the transition
    assert abs(pts[0.4] - a.ev("theory(0.4)")["mean_s"]) < 0.15              # 1 + c/(1 - c) = 1.67 below it
    assert a.ev("mean_chart()") is not None

    a.set("dropdown", "Degrees", "Exponential degrees")
    a.set("slider", "mean degree", 4)                                         # below the transition at 1/2
    th = a.ev("solution()")[0]
    assert th["S"] == 0 and abs(th["mean_s"] - (1 + 0.4 / (1 - 0.8))) < 1e-6  # g1'(1) = 2c for exponential
