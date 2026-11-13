"""Batch 5 explainers: computing betweenness, and Dijkstra's algorithm."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_betweenness_algorithm():
    a = App("ch08-betweenness-algorithm")
    G0 = a["G0"]
    assert "Source **1**" in a.markdown()
    # forward pass, paced: sigma = the number of shortest paths from the source
    a.press("Forward pass")
    a.tick(2)
    assert a.ev("st['phase']") == "forward" and "(guess:n" in a.markdown()       # the queue, as chips
    a.tick(40)
    assert a.ev("st['phase']") == "counted"
    sigma = a.ev("st['sigma']")
    for v in G0:
        assert sigma[v] == len(list(nx.all_shortest_paths(G0, "n1", v)))
    # backward pass: delta(v) = shortest paths from the source through v (shared), source excluded
    a.press("Backward pass")
    a.tick(40)
    assert a.ev("st['phase']") == "done" and "**Done.**" in a.markdown()
    delta = a.ev("st['delta']")
    expect = {v: 0.0 for v in G0}
    for t in G0:
        if t == "n1":
            continue
        paths = list(nx.all_shortest_paths(G0, "n1", t))
        for p in paths:
            for v in p[1:-1]:
                expect[v] += 1 / len(paths)
    assert all(abs(delta[v] - expect[v]) < 1e-9 for v in G0)
    assert a.ev("one_chart()") is not None
    # a new source by clicking, then single steps
    a.click("n7")
    assert a.ev("st['src']") == "n7" and a.ev("st['phase']") == "ready"
    a.press("Step")
    a.press("Step")
    assert a.ev("st['head']") == 2
    # every source: half the sum is the betweenness
    _tab(a, "Every source")
    a.press("Next source")
    assert a.ev("acc['i']") == 1 and a.ev("acc_chart()") is not None
    a.press("Run through every source")
    a.tick(30)
    assert a.ev("acc['i']") == len(G0) and "exactly" in a.markdown()
    a.press("Start again")
    assert a.ev("acc['i']") == 0
    # cost
    _tab(a, "Cost")
    a.press("Simulate: count the steps")
    a.tick(10)
    rows = a.ev("cost['rows']")
    assert len(rows) == len(a["SIZES"]) and all(b < c for n, b, c in rows[2:])
    assert "slope" in a.markdown() and a.ev("cost_chart()") is not None


def test_dijkstra():
    a = App("ch08-dijkstra")
    R = a["ROADS"]
    assert len(a["WINDING"]) == 2 and nx.is_connected(R)
    assert all(e.labelvisible and e.label for e in a.s.graph._edges_list())          # lengths on the roads
    a.press("Step")
    assert a.ev("dk['settled']") == ["Ashby"] and "Priority queue" in a.markdown() and "(guess:n" in a.markdown()
    a.press("Run")
    a.tick(40)
    assert len(a.ev("dk['settled']")) == len(R)
    assert a.ev("dk['dist']") == nx.single_source_dijkstra_path_length(R, "Ashby", weight="km")
    log = a.ev("dk['log']")
    assert [d for _, d, _ in log] == sorted(d for _, d, _ in log)                    # settled in order of distance
    assert "**Finished.**" in a.markdown() and a.ev("dk_chart()") is not None
    a.click("Marsh")
    assert a.ev("dk['src']") == "Marsh" and a.ev("dk['settled']") == []
    _tab(a, "Fewest roads or fewest km")
    a.click("Ashby")
    assert "Marsh → Ashby" in a.markdown()
    a.press("Find the most surprising pair")
    s, t = a.ev("dk['src']"), a.ev("route['to']")
    hop, km = nx.shortest_path(R, s, t), nx.shortest_path(R, s, t, weight="km")
    assert len(km) > len(hop) and "They differ" in a.markdown()
    _tab(a, "Cost")
    a.press("Simulate: list or heap")
    a.tick(8)
    rows = a.ev("cost['rows']")
    assert len(rows) == len(a["SIZES"]) and rows[-1][1] > 5 * rows[-1][2]
    assert a.ev("cost_chart()") is not None
