"""Batch 9 explainers: modularity by node moves, and spectral modularity maximization."""
import numpy as np

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_modularity_by_hand_optimise_and_partitioning():
    a = App("ch14-modularity")
    # Q matches GUESS's modularity() for the same division (karate counted unweighted, as in the book)
    a.call("true_split()")
    assert abs(a.ev("q_of(st['side'])") - a.ev("modularity(grp)")) < 1e-9
    assert abs(a.ev("st['qtrue']") - 0.3715) < 0.02
    a.click("n5")
    assert a.ev("st['side']['n5']") != a.ev("st['truth']['n5']") and "Moved node **5**" in a.markdown()
    assert a.ev("g.getNodeByName('n5').strokewidth") > 0                 # the moved node is outlined
    a.call("one_group()")
    assert abs(a.ev("q_of(st['side'])")) < 1e-12                          # everyone together: Q = 0
    a.call("all_alone()")
    assert a.ev("q_of(st['side'])") < 0
    # the node-moving algorithm, paced: Q never ends lower than it started and reaches the karate optimum
    a.tab("Optimise")
    a.press("New random start")
    q0 = a.ev("q_of(st['side'])")
    a.press("Optimise")
    a.tick(40)
    assert a.ev("st['run']['steps']") >= 30 and a.ev("opt_chart()") is not None
    a.press("To the end")
    assert a.ev("st['run']['done']") and a.ev("q_of(st['side'])") >= q0
    assert abs(a.ev("q_of(st['side'])") - 0.3718) < 0.002                 # the best two-group split of the club
    a.press("Simulate: 20 random starts")
    a.tick(25)
    assert len(a.ev("st['starts']")) == 20 and "20 starts" in a.markdown()
    # partitioning (equal halves) against community detection (free sizes) on unequal planted groups
    a.set("dropdown", "Network", "Planted groups: 24 + 12 (block model)")
    a.tab("Equal halves or free?")
    a.press("Cut into equal halves")
    a.press("Best modularity")
    rows = a.ev("cmp_state['rows']")
    halves, free = rows[0], rows[1]
    assert halves[1] == "18 + 18" and free[1] == "24 + 12" and free[3] > halves[3]


def test_spectral_split_more_groups_and_compare():
    a = App("ch14-spectral-modularity")
    B, u = a.ev("st['B']"), a.ev("st['u']")
    assert abs(float(u @ B @ u) - a.ev("st['beta']")) < 1e-9                # u is B's leading eigenvector
    assert "β₁ =" in a.markdown()
    a.press("Split by the signs")
    side = {v._name: v.grp for v in a.s.graph._nodes_list()}
    agree, _nmi = a.ev(f"agreement({side!r})")
    assert agree >= 32                                                      # the karate split comes out nearly right
    assert a.ev("vector_chart()") is not None
    # repeated bisection, paced: Q rises with every split and stops when no split helps
    a.tab("More groups")
    a.press("Split again")
    a.tick(12)
    hist = a.ev("st['hist']")
    assert len(hist) >= 3 and all(q2 > q1 for (_a, q1), (_b, q2) in zip(hist, hist[1:]))
    assert not a.ev("st['timer'].running") and "No group can be split" in a.markdown()
    assert a.ev("matrix_chart()") is not None
    # three planted groups: found exactly by repeated bisection
    a.set("dropdown", "Network", "Planted groups: 3 × 15 (block model)")
    a.tab("Compare")
    parts = a.ev("full_spectral()")
    assert len(parts) == 3 and "NMI 1.00" in a.markdown()
    a.press("Simulate: harder and harder groups")
    a.tick(14)
    sim = a.ev("st['sim']")
    assert len(sim) == 12 and sim[0][1] > 0.9 and sim[-1][1] < 0.4          # easy groups found, impossible ones not
    a.set("dropdown", "Network", "Dolphins (62)")
    assert np.allclose(a.ev("st['B']").sum(axis=1), 0)                      # rows of B add to zero
