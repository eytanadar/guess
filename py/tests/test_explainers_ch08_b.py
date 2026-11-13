"""Batch 5 explainers: computing degrees and clustering, and breadth-first search."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401


def test_ch08_degrees_clustering_counts_pairs():
    a = App("ch08-degrees-clustering")
    assert "Click a node" in a.markdown()
    a.press("Check its pairs")                                   # starts with the best-connected node
    a.tick(3)
    assert a.ev("one['i']") == 3 and a.ev("one['node']") is not None
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())     # the pair being checked
    a.press("All pairs at once")
    name = a.ev("one['node']")
    G = a.ev("net['G']")
    k = G.degree(name)
    assert a.ev("one['i']") == k * (k - 1) // 2
    assert len(a.ev("one['closed']")) == nx.triangles(G, name)
    assert "](guess:n" in a.ev("one_text()") and a.ev("one_chart()") is not None
    a.s.dispatch(_tabs(a)._id, "change", "Every node")
    a.press("Check every node")
    a.tick(2)
    assert len(a.ev("allpass['done']")) == 2
    a.press("All nodes at once")
    total = sum(d * (d - 1) // 2 for _, d in G.degree())
    assert a.ev("allpass['checks']") == total
    assert a.ev("allpass['tri']") == 3 * sum(nx.triangles(G).values()) // 3
    assert f"{nx.transitivity(G):.3f}" in a.ev("every_text()")
    assert a.ev("every_chart()") is not None
    a.press("Reset")
    assert a.ev("allpass['checks']") == 0
    # the network with hubs needs more checks for about the same number of edges
    a.set("dropdown", "Network", "Even: every node has 4 neighbours")
    H = a.ev("net['G']")
    assert sum(d * (d - 1) // 2 for _, d in H.degree()) < total
    a.s.dispatch(_tabs(a)._id, "change", "Hubs cost more")
    assert "| Even |" in a.ev("cost_table()")
    a.press("Simulate: bigger networks")
    a.tick(10)
    rows = a.ev("sim['rows']")
    assert len(rows) == 7 and rows[-1][3] / rows[0][3] > rows[-1][1] / rows[0][1]
    assert a.ev("sim_chart()") is not None and "slope" in a.ev("sim_text()")


def test_ch08_bfs_queue_naive_and_paths():
    a = App("ch08-bfs")
    G = a.ev("G0")
    a.press("Search")
    a.tick(3)
    assert a.ev("st['read']") == 3 and "In the queue" in a.ev("search_text()")
    a.press("Pause")
    a.press("Run to the end")
    assert a.ev("st['dist']") == dict(nx.single_source_shortest_path_length(G, "v0"))
    n, m = G.number_of_nodes(), G.number_of_edges()
    assert a.ev("st['ops']") == n + 2 * m
    a.set("dropdown", "Version", "Naive: rescan every node each round")
    a.press("Run to the end")
    ecc = nx.eccentricity(G, "v0")
    assert a.ev("st['ops']") == n * (ecc + 2) + 2 * m
    assert a.ev("search_chart()") is not None
    a.click("v7")
    assert a.ev("st['src']") == "v7" and a.ev("st['dist']") == {"v7": 0}
    a.s.dispatch(_tabs(a)._id, "change", "Shortest paths")
    overlay = a.ev("len([e for e in g.edges if e.overlay])")
    assert overlay == n - 1                                      # one predecessor each: a tree
    _, _, sigma = a.ev("all_preds('v7')")
    t = max(sigma, key=sigma.get)
    a.set("dropdown", "Keep", "All predecessors (every shortest path)")
    a.click(t)
    assert sigma[t] == len(list(nx.all_shortest_paths(G, "v7", t)))
    assert f"**{sigma[t]}** shortest paths" in a.ev("paths_text()")
    assert a.ev("len([e for e in g.edges if e.overlay])") > overlay
    a.s.dispatch(_tabs(a)._id, "change", "Running time")
    assert a.ev("len([e for e in g.edges if e.overlay])") == 0 and a.ev("all(e.visible for e in g.edges)")
    a.press("Simulate: bigger networks")
    a.tick(10)
    assert len(a.ev("rt['rows']")) == 7 and "O(n²)" in a.ev("rt_text()")
