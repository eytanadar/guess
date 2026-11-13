"""Networks explainers, Chapter 8 (part a): running time and storing a network.
Uses the App driver from test_explainers."""
from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401  (the fixture runs in the data folder)


def _switch(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_complexity_times_grow_with_the_right_slopes():
    a = App("ch08-complexity")
    shown = lambda: a.ev("len([v for v in g.nodes if v.visible])")
    assert shown() == a["SHOWN"]
    before = a.ev("{v.name: (v.x, v.y) for v in g.nodes}")
    _switch(a, "Time it")
    assert "Simulate" in a.ev("time_text()") and a.ev("time_chart()") is None
    a.press("Simulate")
    assert shown() == 0                                  # laid out once, then revealed
    a.tick(2)
    assert 0 < shown() <= 50
    assert any(v.strokecolor == "200,40,40" for v in a.s.graph.nodes if v.visible)   # the newest nodes outlined
    a.tick(8)
    assert shown() == a["SHOWN"]
    assert a.ev("{v.name: (v.x, v.y) for v in g.nodes}") == before                    # nobody moved
    rows = a["sim"]["rows"]
    fit = a["fit"]
    slopes = {k.split(",")[0]: fit(v)[0] for k, v in rows.items()}
    assert 0.7 < slopes["count degrees"] < 1.3 and 0.7 < slopes["breadth-first search"] < 1.3
    assert 1.6 < slopes["check every pair"] < 2.4 and 2.5 < slopes["check every triple"] < 3.4
    assert a.ev("time_chart()") is not None and "| check every triple, O(n³) | 3 |" in a.ev("time_text()")
    _switch(a, "Extrapolate")
    a.set("slider", "n = 10^…", 9)
    text = a.ev("extrapolate_text()")
    assert "1,000,000,000" in text and "years" in text and "run the simulation first" not in text
    _switch(a, "Big-O")
    assert a.ev("growth_chart()") is not None


def test_storing_lookups_edits_memory_and_simulation():
    a = App("ch08-storing")
    adj = a["adj"]
    assert sum(len(v) for v in adj.values()) == 2 * len(a.s.graph.edges)
    a.click("n03")
    md = a.markdown()
    assert f"in **{len(adj[3])}** reads" in md and "**10** cells" in md and "(guess:n" in md
    target = adj[3][-1]                                  # the last entry: the scan reads them all
    a.click(f"n{target:02d}")
    a.tick(len(adj[3]) + 2)
    assert a.ev("st['found']") is True and a.ev("st['pos']") == len(adj[3])
    assert f"Found** after {len(adj[3])} read" in a.markdown()
    assert any(e.linestyle == "flow" for e in a.s.graph.edges)
    absent = next(j for j in range(1, 11) if j != 3 and j not in adj[3])
    a.click("n03")
    a.click(f"n{absent:02d}")
    a.tick(len(adj[3]) + 2)
    assert a.ev("st['found']") is False and "Not there" in a.markdown()
    # add and remove keep the list, the graph and the matrix in step
    _switch(a, "Add and remove")
    m = len(a.s.graph.edges)
    a.click("n03")
    a.click(f"n{absent:02d}")
    assert len(a.s.graph.edges) == m + 1 and absent in adj[3] and 3 in adj[absent]
    a.click("n03")
    a.click(f"n{absent:02d}")
    assert len(a.s.graph.edges) == m and absent not in adj[3]
    assert "reads to find it" in a.ev("edit_text()") and a.ev("matrix_chart()") is not None
    _switch(a, "Memory")
    a.set("slider", "n = 10^…", 6)
    assert "1,000,000" in a.ev("memory_text()") and "GB" in a.ev("memory_text()")
    _switch(a, "Simulate")
    a.press("Simulate")
    a.tick(8)
    rows = a["sim"]["rows"]
    assert len(rows) == 6 and all(1 < r[1] < 6 for r in rows)
    assert sum(r[2] for r in rows) > sum(r[1] for r in rows)     # hubs make scans longer
    assert a.ev("sim_chart()") is not None
