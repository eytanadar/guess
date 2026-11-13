"""Batch 9 explainers: extra edges and edge removal, and non-linear preferential attachment."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_growth_variations_replays_additions_and_removals_in_place():
    a = App("ch13-growth-variations")
    assert a.ev("len([v for v in g.nodes if v.visible])") == 3                 # the starting clique
    a.set("slider", "extra edges per step, w", 1.0)
    a.set("slider", "edges removed per step, v", 0.5)
    assert a.ev("(st['w'], st['v'])") == (1.0, 0.5)
    assert a.ev("sum(1 for e in g.edges if e.died >= 0)") > 0                   # removals recorded
    before = _positions(a)
    a.press("Grow it, node by node")
    a.tick(60)
    k = a.ev("st['k']")
    assert k == 60 and a.ev("len([v for v in g.nodes if v.visible])") == k + 3
    # an edge removed earlier is hidden; one removed this step shows once, red and dashed
    assert a.ev(f"all(not e.visible for e in g.edges if 0 <= e.died < {k})")
    assert a.ev(f"all(e.visible and e.linestyle == 'dashed' for e in g.edges if e.died == {k} and e.born <= {k})")
    md = a.markdown()
    assert "extra edges between old nodes" in md and "α = 2 + c / (c + 2w − 2v) = 2.67" in md
    assert a.ev("grow_chart()") is not None
    a.press("Show the whole network")
    assert _positions(a) == before                                             # nobody moved
    # the exact solution of the master equation: normalised, with the tail the formula says
    import math
    p = a.ev("exact_pk(2, 1.0, 0.5)")
    assert abs(p.sum() - 1) < 1e-4                                          # truncated at k = 3000
    slope = -math.log(p[2000] / p[500]) / math.log(4)
    assert abs(slope - 2.667) < 0.05
    a.tab("Change the exponent")
    a.press("Simulate: sweep the removal rate")
    a.tick(6)
    sw = a.ev("st['sweep']")
    assert [r["v"] for r in sw] == [0.0, 0.25, 0.5, 0.75]
    assert sw[-1]["fit"] > sw[0]["fit"]                                       # removals steepen the tail
    assert a.ev("sweep_alpha_chart()") is not None and a.ev("sweep_ccdf_chart()") is not None
    assert "Eq. (13.85)" in a.markdown()
    # too many removals (v >= c/2 + w): no power law
    a.set("slider", "extra edges per step, w", 0)
    a.set("slider", "edges removed per step, v", 1.5)
    a.tab("Grow it")
    assert "no longer a power law" in a.markdown()


def test_nonlinear_attachment_regimes():
    a = App("ch13-nonlinear-attachment")
    before = _positions(a)
    a.press("Grow it, node by node")
    a.tick(30)
    assert a.ev("st['k']") == 30 and "leader" in a.markdown() and a.ev("grow_chart()") is not None
    a.press("Show the whole network")
    assert _positions(a) == before
    a.set("slider", "attachment", 1.5)
    hi = a.ev("st['hist'][-1][1]")
    a.set("slider", "attachment", 0.6)
    lo = a.ev("st['hist'][-1][1]")
    assert hi > 3 * lo                                                        # condensation against no hubs
    assert abs(a.ev("solve_mu(1.0)") - 4) < 1e-3                              # mu = mean degree 2c for gamma = 1
    a.tab("Degree distributions")
    assert a.ev("dist_chart()") is not None and "stretched" in a.markdown()
    a.set("dropdown", "Axes", "log-linear")
    # the exact solution matches a simulated network at gamma = 0.8
    d = a.ev("grow_nl(8000, 0.8, 3)")
    sim = dict(a.ev(f"ccdf({d})"))
    ex = dict(a.ev("exact_ccdf(0.8, 400)"))
    assert all(abs(sim[k] - ex[k]) < 0.01 + 0.15 * ex[k] for k in (3, 5, 10, 20))
    a.tab("Condensation")
    a.press("Simulate: 250 to 4,000 nodes")
    a.tick(7)
    sim = a.ev("st['sim']")
    assert len(sim) == 5
    assert sim[-1][1.5] > 0.25 and sim[-1][0.8] < sim[0][0.8]
    assert a.ev("sim_chart()") is not None and "condensate" in a.markdown()
