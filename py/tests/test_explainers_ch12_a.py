"""Batch 7 explainer: the configuration model."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_configuration_model():
    a = App("ch12-configuration-model")
    ks = a.ev("ks_now()")
    M = sum(ks) // 2
    # the final network is built first and laid out; its edges are hidden, one spoke per stub
    assert a.ev("len(g.edges)") == M and a.ev("len([e for e in g.edges if e.visible])") == 0
    assert len(a.ev("getDrawings()")) == sum(ks)
    # the explainer's pairing order is the command's: edge t joins the t-th pair
    pairs = a.ev("st['pairs']")
    for t, ((i, _), (j, _)) in enumerate(pairs):
        e = a.ev(f"st['edge_at'][{t + 1}]")
        assert {e.node1.name, e.node2.name} == {f"nd{i}", f"nd{j}"}
    pos = a.ev("{n.name: (n.x, n.y) for n in g.nodes}")
    a.press("One pair")
    assert a.ev("st['step']") == 1 and len(a.ev("getDrawings()")) == sum(ks) - 2
    a.press("Pair them up")
    a.tick(M + 2)
    assert a.ev("st['step']") == M and len(a.ev("getDrawings()")) == 0
    assert a.ev("{n.name: (n.x, n.y) for n in g.nodes}") == pos            # nothing moved
    # every stub used: degrees exactly as asked (GUESS counts a self-loop once)
    loops = a.ev("sum(1 for k in st['bad'].values() if k == 'self-loop')")
    assert a.ev("sum(n.degree for n in g.nodes)") + loops == sum(ks)
    assert "Self-loops so far" in a.markdown()
    a.press("Make it simple")
    assert "Made simple" in a.markdown()
    a.press("Simulate: 1,000 pairings")
    sim = a.ev("st['sim']")
    assert abs(sim["loops"] - a.ev("expected_loops(ks_now())")) < 0.25
    assert abs(sim["repeats"] - a.ev("expected_repeats(ks_now())")) < 0.3      # exact expectation of parallel pairs
    assert a.ev("pairing_chart()") is not None
    a.press("New shuffle")
    assert a.ev("st['seed']") == 2 and a.ev("st['step']") == 0

    _tab(a, "Edge probability")
    a.press("Simulate: 2,000 pairings")
    a.tick(25)
    assert a.ev("prob['runs']") == 2000
    a.click("nd0")
    assert "likeliest partners" in a.markdown() and a.ev("prob_chart()") is not None
    worst = a.ev("max(abs(measured(i, j) - predicted(i, j)) for i in range(len(ks_now())) "
                 "for j in range(i + 1, len(ks_now())))")
    assert worst < 0.12

    _tab(a, "Expected degree")
    a.tick(15)
    assert a.ev("cl['step']") == a.ev("cl['batches']") and "asked→got" in a.markdown()
    a.press("Simulate: 200 draws")
    assert a.ev("cl_chart()") is not None and "200** draws" in a.markdown()

    _tab(a, "Bigger networks")
    a.press("Simulate: n = 50 to 3,200")
    a.tick(9)
    rows = a.ev("grow['rows']")
    assert len(rows) == 7 and rows[-1]["poisson"][0] < rows[0]["poisson"][0]
    assert a.ev("grow_chart()") is not None

    # back to the pairing: the matching's edges return on the same nodes
    _tab(a, "Pair the stubs")
    assert a.ev("len(g.edges)") == a.ev("len(st['pairs'])") and len(a.ev("getDrawings()")) == sum(a.ev("ks_now()"))
    a.set("dropdown", "Degrees", "A dozen nodes")
    assert a.ev("len(g.nodes)") == 12 and not a.errors()
