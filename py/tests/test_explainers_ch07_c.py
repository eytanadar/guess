"""Batch 4 explainers: clustering, reciprocity and structural balance."""
from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401


def test_ch07_clustering_triangles_degree_and_rewiring():
    a = App("ch07-clustering")
    assert "C = 3 ×" in a.markdown() and "Click a character" in a.markdown()
    a.click("Valjean")
    md = a.markdown()
    assert "**Valjean** has" in md and "Local clustering" in md
    assert any(e.width == 4.5 for e in a.s.graph._edges_list())          # triangle-closing edges
    a.click("Myriel")
    assert a.s.view.drawings                                              # open triples drawn dashed
    a.s.dispatch(_tabs(a)._id, "change", "Clustering and degree")
    assert not a.errors()
    assert a.ev("max(n.localc for n in g.nodes)") == 1.0
    assert a.ev("degree_chart()") is not None
    a.s.dispatch(_tabs(a)._id, "change", "Rewire")
    c0 = a.ev("global_c(live['G'])")
    deg0 = a.ev("sorted(d for _, d in live['G'].degree())")
    a.press("Rewire, keeping degrees")
    a.tick(5)
    assert a.ev("rw['swaps']") == 5 and a.ev("len(g.edges)") == a.ev("len(ORIGINAL)")
    a.press("Pause")
    a.press("200 swaps at once")
    assert a.ev("global_c(live['G'])") < c0 - 0.1
    assert a.ev("sorted(d for _, d in live['G'].degree())") == deg0
    assert a.ev("sorted(n.degree for n in g.nodes)") == a.ev("sorted(d for _, d in G0.degree())")
    assert a.ev("rewire_chart()") is not None
    a.press("Simulate: 20 randomised copies")
    assert len(a.ev("rw['sims']")) == 20 and max(a.ev("rw['sims']")) < c0
    assert "randomised copies" in a.markdown()
    a.press("Restore")
    assert abs(a.ev("global_c(live['G'])") - c0) < 1e-12
    assert abs(a.ev("transitivity()") - c0) < 1e-9


def test_ch07_reciprocity_and_balance():
    a = App("ch07-reciprocity-balance")
    assert a.ev("graphNames()[0]") == "nominations"
    r0 = a.ev("recip(REAL)")
    assert 0.3 < r0 < 0.9 and f"r = **{r0:.2f}**" in a.markdown()
    assert a.ev("abs(reciprocity() - recip(REAL)) < 1e-9")
    a.click("A1")
    assert "**A1** names" in a.markdown()
    a.press("Shuffle the nominations")
    assert a.ev("recip(noms['edges'])") < r0
    assert a.ev("len(g.edges)") == len(a.ev("REAL"))
    a.press("Real nominations")
    assert a.ev("abs(reciprocity() - recip(REAL)) < 1e-9")
    a.press("Simulate: 50 shuffles")
    assert len(a.ev("noms['sims']")) == 50 and a.ev("noms_chart()") is not None
    # balance
    a.s.dispatch(_tabs(a)._id, "change", "Structural balance")
    assert not a.errors() and a.ev("graphNames()[0]") == "signed"
    bad0 = len(a.ev("unbalanced()"))
    assert bad0 > 0 and f"**{bad0}** are unbalanced" in a.markdown()
    e = a.s.graph._edges_list()[0]
    s0 = a.ev("SIGN[key('%s', '%s')]" % (e._n1._name, e._n2._name))
    assert a.s.dispatch("graph", "clickEdge", ["e", e._id]) is not False and not a.errors()
    assert a.ev("SIGN[key('%s', '%s')]" % (e._n1._name, e._n2._name)) == -s0
    a.press("Settle (triad dynamics)")
    for _ in range(300):
        a.tick()
        if not a.ev("unbalanced()"):
            a.tick()
            break
    assert not a.ev("unbalanced()") and "**Balanced**" in a.markdown()
    r = a.ev("structuralBalance('sign')")
    assert r["balanced"] and a.ev("balance_chart()") is not None
    a.press("New random signs")
    a.press("Simulate: 40 runs")
    sims = a.ev("bal['sims']")
    assert len(sims) == 40 and all(big >= 4 for _, big in sims)
    assert "simulated runs" in a.markdown()
    a.s.dispatch(_tabs(a)._id, "change", "Reciprocity")
    assert not a.errors() and a.ev("graphNames()[0]") == "nominations"
