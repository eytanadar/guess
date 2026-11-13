"""Batch 12 explainer: SIR and SIS in time, against the degree-based approximation."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_sir_sis_in_time():
    a = App("ch16-sir-sis-in-time")
    assert a.ev("graphNames()")[0] == "poisson" and set(a.ev("graphNames()")) == {"poisson", "powerlaw"}
    assert a.ev("k2_over_k('powerlaw')") > 1.5 * a.ev("k2_over_k('poisson')")
    before = _positions(a)
    # SIR, step by step: every transmission goes along an edge and is highlighted
    a.press("Run the epidemic")
    a.tick(5)
    assert a.ev("run['t']") >= 5
    for e in a.ev("run['lit']"):
        assert e.linestyle == "flow"
    a.press("To the end")
    curve = a.ev("run['curve']")
    assert curve[-1][1] == 0 or a.ev("run['t']") == 120                # SIR ends when no one is infected
    assert curve[-1][2] > 0.3                                          # a real outbreak at beta 0.12, gamma 0.2
    # the degree-based theory ends in the same place, give or take
    th = a.ev("run['theory']")
    assert abs(th[-1][2] - curve[-1][2]) < 0.2 and th[-1][1] < 0.01
    assert a.ev("time_chart()") is not None and "degree-based approximation" in a.markdown()
    assert _positions(a) == before                                     # nodes never move
    # SIS settles at an endemic level close to the theory
    a.set("dropdown", "Model", "SIS")
    a.press("To the end")
    sis = a.ev("run['curve']")
    tail = sum(x for _t, x, _r in sis[-30:]) / 30
    assert tail > 0.1 and abs(tail - a.ev("run['theory'][-1][1]")) < 0.15
    # hubs are infected most of the time: prevalence rises with degree, as predicted
    a.tab("Who is infected (SIS)")
    a.press("Run a long SIS epidemic")
    d = a.ev("degs['poisson']")
    prev = a.ev("run['prev']")
    order = sorted(d, key=lambda v: -d[v])
    q = len(order) // 4
    assert sum(prev[v] for v in order[:q]) / q > sum(prev[v] for v in order[-q:]) / q + 0.1
    assert a.ev("prevalence_chart()") is not None and "five biggest hubs" in a.markdown()
    # the heavy-tailed network: prevalence by degree too, after switching networks
    a.set("dropdown", "Network", "Heavy-tailed degrees (power law)")
    assert a.ev("graphNames()")[0] == "powerlaw" and a.ev("len(emap)") > 0
    # the threshold: the heavy-tailed network keeps the infection alive at low beta
    a.tab("The threshold")
    a.press("Simulate: SIS at each β")
    a.tick(12)
    rows = a.ev("run['sweep']")
    assert len(rows) == 10
    low = [r for r in rows if r[0] <= 0.04]
    assert max(r[3] for r in low) > max(r[1] for r in low) + 0.05
    assert a.ev("beta_c('powerlaw', 0.3)") < a.ev("beta_c('poisson', 0.3)")
    assert a.ev("internet_threshold()") < 0.02
    assert a.ev("sweep_chart()") is not None and "β_c" in a.markdown()
