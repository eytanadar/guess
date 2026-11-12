"""Batch 4 explainers: ch07-similarity and ch07-assortativity."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def test_similarity_structural_versus_regular():
    a = App("ch07-similarity")
    md = a.markdown()
    assert "Sales head" in md and "Cosine" in md
    # cosine: the Sales head shares no neighbour with the Shop head
    a.click("s0")
    assert "shares none" in a.markdown()
    assert a.ev("g.getNodeByName('h0').simcos") == 0
    # regular equivalence (even paths): the heads are alike, though they share no neighbour
    a.set("dropdown", "Measure", "Regular: σ = αAσA + I")
    sc = a.ev("scores('s0', 'Regular: σ = αAσA + I')")
    assert sc["l0"] > 0.2 and sc["h0"] > 0.05 and sc["s1"] < 1e-9
    assert a.ev("g.getNodeByName('h0').simnow") > 0.05
    # similarTo(method="regular") gives the field and the same numbers as the formula
    a.set("dropdown", "Measure", "Regular: σ = αAσ + I (similarTo)")
    live = a.ev("scores('s0', 'Regular: σ = αAσ + I (similarTo)', live=True)")
    assert abs(a.ev("g.getNodeByName('l0').similarity") - live["l0"]) < 1e-9
    a.set("slider", "α", 0.5)
    a.set("dropdown", "Measure", "Jaccard (shared / all neighbours)")
    a.click("s1")
    assert abs(a.ev("g.getNodeByName('s2').similarity") - 1.0) < 1e-9     # same single neighbour
    a.set("dropdown", "Measure", "Pearson correlation")
    # roles tab: structural groups by department, regular by job
    a.s.dispatch(_tabs(a)._id, "change", "Roles")
    a.set("dropdown", "Measure", "Cosine (shared neighbours)")
    assert "who works together" in a.markdown() and "different departments | **0.000**" in a.markdown()
    a.set("dropdown", "Measure", "Regular: σ = αAσA + I")
    assert "finds **roles**" in a.markdown() and "different departments | **0.000**" not in a.markdown()


def test_assortativity_category_value_degree_and_shuffle():
    a = App("ch07-assortativity")
    md = a.markdown()
    assert "mixing matrix" in md and "Q = " in md
    r_grade = a.ev("grade_r()")
    assert r_grade > 0.3 and a.ev("assortativity(age)") > 0.3
    tabs = _tabs(a)
    a.s.dispatch(tabs._id, "change", "Value")
    assert "assortativity coefficient r" in a.markdown()
    # degree: another network loads into its own graph, and back
    a.s.dispatch(tabs._id, "change", "Degree")
    assert a.ev("graphNames()[0]") == "compare" and a.ev("len(g.nodes)") == 34
    assert "Karate club" in a.markdown() and "disassortative" in a.markdown()
    a.set("dropdown", "Network", "Dolphins")
    assert a.ev("len(g.nodes)") == 62
    a.press("Compare all the networks")
    assert "| Power grid (region) |" in a.markdown() and a.ev("len(g.nodes)") == 62
    a.set("dropdown", "Network", "This school")
    assert a.ev("graphNames()[0]") == "school"
    # shuffling keeps every degree and drains the grade mixing
    a.s.dispatch(tabs._id, "change", "Shuffle")
    deg = a.ev("sorted((n.name, n.degree) for n in g.nodes)")
    m = a.ev("len(g.edges)")
    a.press("Shuffle, keeping degrees")
    a.tick(40)
    assert a.ev("sorted((n.name, n.degree) for n in g.nodes)") == deg and a.ev("len(g.edges)") == m
    assert a.ev("shuffle['swaps']") > 40 and a.ev("grade_r()") < r_grade
    assert any(w > 3 for w in a.ev("[e.width for e in g.edges]"))          # the newest swap is marked
    a.press("Simulate 20 full shuffles")
    assert len(a.ev("shuffle['null']")) == 20 and "20 full shuffles" in a.markdown()
    assert a.ev("max(abs(x[0]) for x in shuffle['null'])") < 0.2
    a.press("Restore")
    assert a.ev("abs(grade_r() - %r)" % r_grade) < 1e-9
    a.s.dispatch(tabs._id, "change", "Category")
    assert a.ev("graphNames()[0]") == "school"
