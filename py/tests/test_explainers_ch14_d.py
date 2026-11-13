"""Batch 10 explainers: Girvan-Newman edge removal and hierarchical clustering, with dendrograms."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _dendrograms(a):
    return [w._state.get("spec") for w in a.s.gui.widgets.values()
            if w.kind == "chart" and w._state.get("spec") and w._state["spec"].get("kind") == "dendrogram"]


def test_girvan_newman_removes_busiest_edges_and_builds_the_tree():
    a = App("ch14-girvan-newman")
    seq = a.ev("gn['seq']")
    assert len(seq) == 78                                     # every karate edge, one at a time
    # each removed edge had the highest betweenness at that moment (recomputed after every removal)
    G = nx.karate_club_graph()
    G = nx.relabel_nodes(G, {v: f"n{v}" for v in G})
    for s in seq[:5]:
        btw = nx.edge_betweenness_centrality(G, normalized=False)
        assert abs(max(btw.values()) - s["top"]) < 1e-9
        G.remove_edge(*s["edge"])
    # the dendrogram: one merge per split, every node a leaf, the first split the top merge
    merges = a.ev("gn['merges']")
    assert len(merges) == len(a.ev("gn['splits']")) == 33
    heights = a.ev("gn['heights']")
    assert heights == sorted(heights)
    # stepping, paced: edges vanish, Q is recorded, the removed edge's ends are outlined
    a.press("Remove edges, one by one")
    a.tick(15)
    k = a.ev("gn['step']")
    assert k >= 10 and a.ev("len([e for e in g.edges if not e.visible])") >= k - 1
    assert "Removed edge" in a.markdown() and a.ev("q_chart()") is not None
    # reading the tree: the best cut, and the slider
    a.tab("Read the tree")
    a.press("Best modularity")
    assert a.ev("groups_now()") == len(a.ev("gn['comp_at'][best_step()]"))
    assert abs(a.ev("gn['q_at'][best_step()]") - 0.385) < 0.02
    a.set("slider", "groups", 2)
    assert a.ev("groups_now()") == 2
    d = _dendrograms(a)
    assert d and len(d[-1]["leaves"]) == 34 and len(d[-1]["clusters"]) == 33 and len(d[-1]["dgroups"]) == 2
    # the planted network: the best cut finds its three groups
    a.set("dropdown", "Network", "Planted groups: 3 × 12 (block model)")
    best = a.ev("gn['comp_at'][best_step()]")
    assert len(best) == 3
    # simulate
    a.tab("Simulate")
    a.press("Simulate: planted groups")
    a.tick(12)
    rows = a.ev("gn['simrows']")
    assert len(rows) == 10 and max(r[1] for r in rows if r[0] == 6.0) == 1.0
    assert a.ev("sim_chart()") is not None


def test_hierarchical_clustering_merges_cuts_and_linkages():
    a = App("ch14-hierarchical-clustering")
    n = len(a.ev("hc['names']"))
    merges, heights = a.ev("hc['merges']"), a.ev("hc['heights']")
    assert len(merges) == n - 1 and heights == sorted(heights)          # one merge per step, heights never fall
    # merges refer only to clusters that exist, and every cluster is used exactly once
    used = [x for m in merges for x in m]
    assert len(used) == len(set(used)) == 2 * (n - 1) and max(used) < 2 * n - 2
    # the first merge is the most similar pair
    import numpy as np
    S = np.array(a.ev("hc['S'].tolist()"))
    np.fill_diagonal(S, -1)
    i, j = merges[0]
    assert abs(S[i, j] - S.max()) < 1e-12
    # step by step, paced; the merged group is outlined
    a.press("Merge, one pair at a time")
    a.tick(6)
    t = a.ev("hc['t']")
    assert t >= 4 and "Merge" in a.markdown() and a.ev("len(groups_after(hc['t']))") == n - t
    assert any(v.strokewidth > 0 for v in a.s.graph.nodes)
    assert _dendrograms(a)
    # the cut
    a.tab("Cut the tree")
    a.set("slider", "groups", 2)
    two = a.ev("cut(2)")
    assert len(two) == 2 and sum(len(x) for x in two) == n
    a.press("Best modularity")
    assert int(a.ev("kslider.value")) == a.ev("best_k()")
    # single linkage chains on karate: a 2-group cut leaves a huge group and a stray
    a.tab("Linkage and chaining")
    table = a.markdown()
    assert "| single | 33 + 1 |" in table and "| average | 18 + 16 |" in table
    a.set("dropdown", "Groups compared by", "complete linkage")
    assert a.ev("hc['link']") == "complete linkage"
    # simulate across mixing, all three linkages
    a.press("Simulate: planted groups")
    a.tick(12)
    rows = a.ev("hc['simrows']")
    assert all(len(v) == 10 for v in rows.values()) and a.ev("sim_chart()") is not None
    # the planted network: average linkage at the best cut finds the three groups exactly
    a.set("dropdown", "Groups compared by", "average linkage")
    a.set("dropdown", "Network", "Planted groups: 3 × 12 (block model)")
    k = a.ev("best_k()")
    assert k == 3 and abs(a.ev("nmi_of(hc['truth'], labels_of(cut(3)))") - 1.0) < 1e-9
