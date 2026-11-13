"""Batch 13 explainers: spectra of networks, and synchronization."""
import math

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_spectra():
    a = App("ch17-spectra")
    # a random graph: kappa_1 near c + 1, outside the semicircle of radius 2 sqrt(c)
    c = a.ev("mean_degree()")
    k1, k2 = a.ev("float(st['vals'][-1])"), a.ev("float(st['vals'][-2])")
    assert abs(k1 - (c + 1)) < 1.0 and k2 < 2 * math.sqrt(c) + 0.6 < k1
    assert a.ev("hist_chart() is not None") and "semicircle" in a.markdown()
    # eigenvectors one at a time, without moving anyone
    before = _positions(a)
    a.press("Show eigenvectors one by one")
    a.tick(3)
    assert a.ev("st['shown']") == 2 and _positions(a) == before
    # the Laplacian: one zero eigenvalue per component
    a.set("dropdown", "Matrix", "Laplacian L = D − A")
    import networkx as nx
    G = a.ev("toNetworkX(directed=False)")
    zeros = a.ev("int((abs(st['vals']) < 1e-8).sum())")
    assert zeros == nx.number_connected_components(G) and "spectral gap" in a.markdown()
    a.set("dropdown", "Matrix", "Normalised Laplacian")
    assert -1e-9 < a.ev("float(st['vals'][0])") and a.ev("float(st['vals'][-1])") <= 2 + 1e-9
    # hubs push kappa_1 up to at least sqrt(k_max)
    a.set("dropdown", "Matrix", "Adjacency A")
    a.set("dropdown", "Network", "Hubs (power-law degrees)")
    kmax = a.ev("float(st['deg'].max())")
    assert a.ev("float(st['vals'][-1])") >= math.sqrt(kmax) - 1e-9
    # growing n: kappa_1 stays apart from the bulk edge
    a.tab("Grow n")
    a.press("Simulate: grow n")
    a.tick(6)
    grow = a.ev("st['grow']")
    assert len(grow) == 4 and all(k1 > k2 + 1 for _n, k1, k2, _c in grow)
    assert a.ev("grow_chart() is not None") and a.ev("grow_hist_chart() is not None")
    # a growing hub: kappa_1 approaches sqrt(k_max)
    a.tab("Hubs")
    a.press("Simulate: bigger and bigger hubs")
    a.tick(8)
    hubs = sorted(a.ev("st['hubs']"))
    assert len(hubs) == 6
    km, k1, _r = hubs[-1]
    assert math.sqrt(km) <= k1 < 1.3 * math.sqrt(km)
    assert a.ev("hub_chart() is not None")


def test_synchronization():
    a = App("ch17-synchronization")
    before = _positions(a)
    assert a.ev("osc['rs'][-1][1]") < 0.3                        # random phases to start
    a.press("Run the oscillators")
    a.tick(20)
    assert a.ev("osc['t']") > 0 and len(a.ev("osc['lit']")) > 0
    for e in a.ev("osc['lit']"):
        assert e.linestyle == "flow"
    a.press("Jump ahead")
    a.press("Jump ahead")
    assert a.ev("osc['rs'][-1][1]") > 0.6                        # K = 0.25, above the threshold: in step
    # phases are colours on a wheel: nodes in step look alike
    cols = a.ev("[v.color for v in g.nodes]")
    assert len(cols) == 150 and a.ev("wheel_chart() is not None") and a.ev("r_chart() is not None")
    assert _positions(a) == before                               # oscillators never move
    # no coupling: they drift apart again
    a.set("slider", "coupling K", 0.0)
    a.press("Scramble the phases")
    a.press("Jump ahead")
    assert a.ev("osc['rs'][-1][1]") < 0.3
    # the sweep: hubs synchronize at weaker coupling than a random network; the ring hardly at all
    a.tab("Coupling sweep")
    a.press("Simulate: sweep the coupling")
    a.tick(40)
    sw = a.ev("{k: dict(v) for k, v in osc['sweep'].items()}")
    first = {net: min((K for K, r in pts.items() if r > 0.5), default=9) for net, pts in sw.items()}
    assert first["powerlaw"] <= first["random"] < first["ring"]
    assert a.ev("k_crit(osc['sweepA']['powerlaw'])") < a.ev("k_crit(osc['sweepA']['random'])")
    assert a.ev("sweep_chart() is not None") and "K_c (theory)" in a.markdown()
    # the master stability table: shortcuts cut lambda_max / lambda_2
    a.tab("Master stability")
    lap = a.ev("osc['lap'][0]")
    ring, sw_ = lap["ring"], lap["smallworld"]
    assert ring[1] / ring[0] > 5 * (sw_[1] / sw_[0])
    for net in ["Ring (each linked to 6 neighbours)", "Small world (ring with 10% shortcuts)", "Hubs (power-law degrees)"]:
        a.set("dropdown", "Network", net)
        assert len(a.ev("osc['names']")) > 100
