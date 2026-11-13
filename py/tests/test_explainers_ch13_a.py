"""Batch 8 explainer: Price's model of citations."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_price_model_grows_in_place_and_fits():
    a = App("ch13-price-model")
    n = len(a.s.graph._nodes_list())
    assert n == 250 and a.ev("len([v for v in g.nodes if v.visible])") == 1        # only paper 0 so far
    before = _positions(a)
    a.press("Grow it, paper by paper")
    a.tick(12)
    k = a.ev("st['k']")
    assert 1 <= k <= 12
    assert a.ev("len([v for v in g.nodes if v.visible])") == k + 1
    # every shown citation points from a newer paper to an older one, and the newest are highlighted
    assert a.ev("all(e.node1.born > e.node2.born for e in g.edges if e.visible)")
    assert a.ev("len([e for e in g.edges if e.visible and e.linestyle == 'flow'])") == len(a.ev("st['cites'][st['k']]"))
    newest = a.node(f"nd{k}")
    assert newest.color == "255,215,80" and newest.strokewidth == 3                   # the arriving paper
    md = a.markdown()
    assert f"**Paper {k}** of 250" in md and "The rich get richer" in md
    a.press("All papers at once")
    assert a.ev("all(v.visible for v in g.nodes)") and _positions(a) == before        # nobody moved
    assert a.ev("st['indeg']") == a.ev("[v.indegree for v in sorted(g.nodes, key=lambda v: v.born)]")
    # the growth chart: each leader's citations over time end at its final in-degree
    ser = a.ev("st['series']")
    assert all(pts[-1][1] == a.ev("st['final']")[i] for i, pts in ser.items())
    # distribution: a fitted line on the drawn network, then a big simulation against the exact formula
    _tab(a, "Distribution")
    assert "theory says **2 + a/c = 2.33**" in a.markdown()
    a.press("Simulate: 20,000 papers")
    a.tick(8)
    assert a.ev("sim['n']") == 20000
    import re
    m = re.search(r"\*\*20,000 papers\*\* simulated off screen: α = \*\*([0-9.]+)", a.markdown())
    assert m and abs(float(m.group(1)) - 2.33) < 0.12                  # fitted in k + a, close to 2 + a/c
    assert "Fitting k + a, not k" in a.markdown()
    # the exact formula: P(K >= 0) = 1 and it falls with k
    assert abs(a.ev("exact_ccdf(0, 3, 1)") - 1) < 1e-9
    assert a.ev("exact_ccdf(10, 3, 1)") < a.ev("exact_ccdf(2, 3, 1)") < 1
    # sweep a: measured alpha rises with a, close to 2 + a/c
    _tab(a, "Vary a")
    a.press("Simulate: sweep a")
    a.tick(10)
    rows = a.ev("sweep['rows']")
    assert len(rows) == 7
    assert rows[0][1] < rows[-1][1]
    assert all(abs(al - (2 + av / 3)) < 0.25 for av, al, _s, _k in rows[:5])
    # real citations: read straight from the GDF
    _tab(a, "Real citations")
    assert "**1,044** papers" in a.markdown() and "Price network with the same n and c" in a.markdown()
    # sliders rebuild: a larger a gives a larger theoretical exponent
    a.set("slider", "a, the head start", 3)
    assert a.ev("alpha_theory()") == 3.0 and a.ev("len([v for v in g.nodes if v.visible])") == 250
