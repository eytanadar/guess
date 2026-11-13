"""Batch 6 explainers: the small-world effect, and degree distributions and power laws."""
import math

import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_small_world():
    a = App("ch10-small-world")
    G = a.ev("net['G']")
    a.click("Valjean")
    dist = nx.single_source_shortest_path_length(G, "Valjean")
    far = max(dist.values())
    assert f"the farthest are **{far}** hops" in a.markdown() and "Valjean" in a.markdown()
    assert a.node("Valjean").strokewidth == 4 and a.ev("rings_chart()") is not None
    a.press("Spread out from here")
    a.tick(2)
    assert a.ev("rings['layer']") == 2
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())        # the ring being reached
    _tab(a, "All pairs")
    a.press("Measure from 40 sources")
    a.tick(5)
    assert a.ev("pairs['i']") == 5 and a.ev("pairs_chart()") is not None
    a.press("All pairs")
    ell = nx.average_shortest_path_length(G.subgraph(max(nx.connected_components(G), key=len)))
    assert abs(a.ev("net['ell']") - ell) < 1e-9 and "(exact)" in a.markdown()
    _tab(a, "Grows like log n")
    a.press("Simulate: random networks")
    a.tick(10)
    rows = a.ev("growth['rows']")
    assert len(rows) == 7 and rows[-1][1] > rows[0][1]                         # longer, but slowly
    ratios = [ell / math.log(n) for n, ell in rows]                          # ell grows like log n
    assert max(ratios) / min(ratios) < 1.3 and a.ev("growth_chart()") is not None
    a.press("Measure them all")
    a.tick(2)
    _tab(a, "Six degrees")                                                     # leaving mid-tour goes back
    assert a.ev("net['choice']").startswith("Les Mis") and len(a.s.graph._nodes_list()) == 77
    _tab(a, "Grows like log n")
    a.press("Measure them all")
    a.tick(12)
    measured = a.ev("MEASURED")
    assert len(measured) == 8 and a.ev("net['choice']").startswith("Les Mis")
    grid = next(v for k, v in measured.items() if k.startswith("Power grid"))
    assert grid[1] == max(v[1] for v in measured.values())                    # the grid is the big world
    _tab(a, "Six degrees")
    a.click("Napoleon")
    a.click("Gavroche")
    a.set("slider", "your guess", 9)
    a.press("Reveal")
    d = nx.shortest_path_length(G, "Napoleon", "Gavroche")
    assert f"**{d}** hops: you said 9, too many" in a.markdown()


def test_degree_distributions():
    a = App("ch10-degree-distributions")
    fits = a.ev("FITS")
    net = next(k for k in fits if k.startswith("Internet"))
    assert fits[net]["kmin"] == 5 and abs(fits[net]["alpha"] - 2.08) < 0.02   # the whole Internet, as in the book
    lr = a.ev("LR")
    assert lr[net] > 0 and lr["US power grid"] < 0                            # power law vs exponential tails
    assert "washingtonmonthly" in a.markdown()
    for v in ["Log–log histogram", "Logarithmic bins", "Cumulative (log–log)"]:
        a.set("dropdown", "View", v)
        assert a.ev("hist_chart()") is not None
    bins = a.ev("log_bins()")
    n = len(a.s.graph._nodes_list())
    assert len(bins) >= 4 and bins[0][1] > 10 * bins[-1][1]                   # densities fall over the bins
    a.press("Count, node by node")
    a.tick(4)
    assert 0 < a.ev("count['i']") < n and a.ev("hist_chart()") is not None
    _tab(a, "Fit a power law")
    a.press("Best k_min")
    r = a.ev("fit_state['result']")
    assert r["kmin"] == a.ev("kslider.value") and "α = " in a.markdown()
    tail = [v for v in a.s.graph._nodes_list() if v.degree >= r["kmin"]]
    assert all(v.strokewidth == 3 for v in tail) and a.ev("fit_chart()") is not None
    a.set("slider", "k_min", 3)
    assert a.ev("fit_state['result']['kmin']") == 3
    a.set("dropdown", "Network", "Internet (300-AS sample)")
    _tab(a, "Fit a power law")
    a.press("Best k_min")
    assert "snowball sample" in a.markdown()
    _tab(a, "Whole networks")
    assert a.ev("whole_chart()") is not None and "| Internet | 22,963 |" in a.markdown()
    a.press("Simulate: samples")
    a.tick(25)
    rows = a.ev("sim['rows']")
    assert len(rows) == 20
    spread = lambda size: [al for s, al in rows if s == size]
    assert max(spread(10000)) - min(spread(10000)) < max(spread(100)) - min(spread(100))
    assert all(math.isfinite(al) for _, al in rows)
    a.press("Back to the curves")
    assert a.ev("sim['rows']") == []
