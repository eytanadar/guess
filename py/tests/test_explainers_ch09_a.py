"""Batch 6 explainers: errors in network data, and EM from repeated measurements."""
import networkx as nx
import numpy as np

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401


def test_ch09_measurement_error_measures_and_sweeps():
    a = App("ch09-measurement-error")
    T = a.ev("TRUE")
    assert a.ev("TRUE_STATS")["C"] > 0.3                     # many triangles, so spurious edges can dilute them
    # default: 20% of edges missed, nothing else
    M = a.ev("st['M']")
    assert M.number_of_edges() + len(a.ev("st['missed']")) == T.number_of_edges()
    dashed = [e for e in a.s.graph._edges_list() if e.linestyle == "dashed"]
    assert len(dashed) == len(a.ev("st['missed']"))
    assert "| clustering C |" in a.ev("stats_table()")
    # spurious edges are added as red edges, merged nodes move their edges over
    a.set("slider", "missed edges (%)", 0)
    a.set("slider", "spurious edges (% of m)", 30)
    extra = a.ev("st['extra']")
    assert len(extra) == round(0.3 * T.number_of_edges())
    assert len([e for e in a.s.graph._edges_list() if e.origin == "extra"]) == len(extra)
    assert all(not T.has_edge(*sorted(p)) for p in extra)
    a.set("slider", "pairs of nodes merged", 2)
    merged = a.ev("st['merged']")
    assert len(merged) == 2 and all(b not in a.ev("st['M']") for b in merged)
    # missing nodes are taken out of the measured network
    a.set("slider", "nodes not surveyed (%)", 20)
    assert len(a.ev("st['gone']")) == round(0.2 * len(T))
    # watching a measurement: paced, edges flash, then it settles on the same picture
    a.press("Watch it measured")
    a.tick(2)
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())
    a.tick(80)
    assert a.ev("st['events']") == [] and not any(e.linestyle == "flow" for e in a.s.graph._edges_list())
    # the sweep: 11 rates, spurious edges hurt clustering most
    a.s.dispatch(_tabs(a)._id, "change", "Which measures survive?")
    a.set("dropdown", "Error", "spurious edges")
    a.press("Simulate: sweep the error rate")
    a.tick(12)
    rows = a.ev("sim['rows']")
    assert len(rows) == 11 and rows[0][1]["C"] == 1.0
    assert rows[-1][1]["C"] < 0.75 and rows[-1][1]["c"] > 1.4
    assert "**clustering**" in a.ev("sweep_text()") and a.ev("sweep_chart()") is not None


def test_ch09_em_recovers_error_rates_and_network():
    a = App("ch09-em")
    assert "real friendships" in a.markdown()
    E, N = a.ev("data['E']"), a.ev("data['N']")
    assert N == 6 and len(E) == 435
    assert len(a.s.graph._edges_list()) == int((E > 0).sum())
    a.s.dispatch(_tabs(a)._id, "change", "Run EM")
    a.press("One iteration")
    assert a.ev("est['it']") == 1 and a.ev("param_chart()") is None
    a.press("Run EM")
    a.tick(3)
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())      # the Qs that moved most flash
    a.tick(100)
    assert a.ev("est['done']") and a.ev("est['it']") > 5
    assert abs(a.ev("est['a']") - 0.7) < 0.1 and abs(a.ev("est['b']") - 0.05) < 0.03
    assert abs(a.ev("est['rho']") - a.ev("RHO_TRUE")) < 0.03
    # EM beats keeping every pair ever seen
    Q, REAL = a.ev("est['Q']"), a.ev("REAL")
    assert int(((Q > 0.5) != REAL).sum()) < int(((E > 0) != REAL).sum()) // 5
    assert "| EM: Q > ½ |" in a.ev("confusion()") and a.ev("q_chart()") is not None
    # the EM step matches the formulas: alpha = sum E Q / (N sum Q)
    Q2, a2, b2, r2 = a.ev("em_step(data['E'], data['N'], 0.5, 0.3, 0.4)")
    assert np.isclose(a2, (E * Q2).sum() / (N * Q2.sum())) and np.isclose(r2, Q2.mean())
    # showing the truth adds the real pairs never seen
    a.call("truth.checked = true")
    a.call("show_truth(true)")
    assert len(a.s.graph._edges_list()) == int(((E > 0) | REAL).sum())
    # more measurements: fewer mistakes
    a.s.dispatch(_tabs(a)._id, "change", "How many measurements?")
    a.press("Simulate: 1 to 15 measurements")
    a.tick(16)
    rows = a.ev("sim['rows']")
    assert len(rows) == 15 and rows[-1][1]["EM: Q > ½"] < rows[0][1]["EM: Q > ½"]
    assert rows[-1][1]["seen at least once"] > rows[-1][1]["EM: Q > ½"]
    assert a.ev("sim_chart()") is not None
    # the hidden network has several components: packed, with no nodes overlapping
    P = [(nd.x, nd.y) for nd in a.s.graph._nodes_list()]
    assert min(((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 for i, (x1, y1) in enumerate(P) for x2, y2 in P[i + 1:]) > 10
    assert nx.number_connected_components(a.ev("TRUE")) > 1
