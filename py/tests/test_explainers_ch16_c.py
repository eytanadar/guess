"""ch16-outbreak-percolation: the outbreak is the first case's percolation cluster."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401


def test_outbreak_is_the_percolation_cluster_and_theory_matches():
    a = App("ch16-outbreak-percolation")
    assert not a.errors(), a.errors()
    before = a.ev("{v.name: (v.x, v.y) for v in g.nodes}")
    # raising T only adds occupied edges: the first case's cluster can only grow
    sizes = []
    for t in (0.1, 0.3, 0.5, 0.8):
        a.s.run(f"tslider.value = {t}\nchange_T()")
        sizes.append(a.ev("len(cases['cluster'])"))
    assert sizes == sorted(sizes) and sizes[-1] > 50
    # the paced outbreak infects exactly the cluster
    for t in (0.3, 0.6):
        a.s.run(f"tslider.value = {t}\nchange_T()")
        a.press("To the end")
        assert not a.errors(), a.errors()
        assert a.ev("set(cases['when']) == cases['cluster']")
        assert "exactly the cluster" in a.markdown()
    # infections last exactly K steps: everyone infected ends recovered
    assert a.ev("all(cases['state'][v] == 'R' for v in cases['when'])")
    assert a.ev("{v.name: (v.x, v.y) for v in g.nodes}") == before          # nodes never move
    # outbreak sizes from GUESS's outbreaks(duration=3): bimodal above threshold
    a.tab("Outbreak sizes")
    a.s.run("tslider.value = 0.7\nchange_T()")
    a.press("Simulate: 300 outbreaks at this T")
    assert not a.errors(), a.errors()
    assert a.ev("hist['large']") > 0.3 and "split in two" in a.markdown()
    a.s.run("tslider.value = 0.1\nchange_T()")
    a.press("Simulate: 300 outbreaks at this T")
    assert a.ev("hist['large']") < 0.05
    # theory against simulation on big networks
    a.tab("Size against T")
    a.press("Simulate: sweep T on big networks")
    a.tick(40)
    assert not a.errors(), a.errors()
    rows = a.ev("sweep['rows']")
    assert len(rows["poisson"]) == a.ev("len(T_VALUES)")
    for kind in ("poisson", "powerlaw"):
        ks = a.ev(f"BIG['{kind}'][0]")
        for T, S in rows[kind]:
            th = a.ev(f"theory_S(BIG['{kind}'][0], {T})")
            if T >= 0.4:
                assert abs(S - th) < 0.06, (kind, T, S, th)
    # threshold: Poisson T_c = 1/4 for mean degree 4 (about)
    tc = a.ev("gen_funcs(BIG['poisson'][0])[2]")
    assert 0.2 < tc < 0.3
    assert a.ev("gen_funcs(BIG['powerlaw'][0])[2]") < tc
    # the network dropdown rebuilds
    a.s.run("pick_net('Heavy tail (power law)')")
    assert not a.errors(), a.errors() and a.ev("net['kind']") == "powerlaw"
