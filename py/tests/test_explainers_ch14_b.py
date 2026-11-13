"""Batch 9: the Louvain algorithm stepped, and the resolution limit on a ring of cliques."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_louvain_steps_levels_and_resolution_limit():
    a = App("ch14-louvain-resolution")
    assert "Every node starts alone" in a.markdown()
    a.press("One node")
    assert a.ev("lv['visits']") == 1 and a.ev("lv['last']['gain']") >= 0
    # phase 1 to the end of the level, then phase 2: fewer super-nodes, Q up, and the merge keeps every node
    a.press("Finish this level")
    assert a.ev("lv['level']") == 1 and a.ev("lv['H'].number_of_nodes()") < 48
    assert a.ev("sum(len(m) for m in lv['members'].values())") == 48
    # aggregation preserves total weight (inside edges become self-loops)
    assert abs(a.ev("lv['H'].size(weight='weight')") - a.ev("G0.number_of_edges()")) < 1e-9
    # Q never falls as Louvain runs; it ends near the planted groups' Q
    a.press("Run Louvain")
    a.tick(400)
    qs = [q for _v, q in a.ev("lv['qhist']")]
    assert a.ev("lv['done']") and all(q2 >= q1 - 1e-12 for q1, q2 in zip(qs, qs[1:]))
    assert a.ev("current_q()") >= a.ev("PLANTED_Q") - 0.02
    cols = a.ev("list(lv['color'].values())")
    assert len(cols) == len(set(cols))                          # every community its own colour
    # the merged network: one node per community
    a.press("Show the merged network")
    assert a.ev("graphNames()[0]") == "collapsed" and a.ev("len(g.nodes)") == a.ev("lv['H'].number_of_nodes()")
    # the run button, pressed while looking at the merged network of a finished run, goes back without restarting
    a.press("Run Louvain again")
    assert a.ev("graphNames()[0]") == "louvain" and a.ev("lv['done']") and a.ev("lv['level']") >= 1
    a.press("Show the merged network")
    a.press("Back to the nodes")
    assert a.ev("graphNames()[0]") == "louvain"
    # resolution limit: 24 cliques of 5 is past n* = 22, so pairing beats one community per clique
    a.tab("Resolution limit")
    assert a.ev("graphNames()[0]") == "ring"
    G = a.ev("ring['G']")
    q1 = nx.community.modularity(G, a.ev("ring_parts(ring['G'], 24, 5, False)"))
    q2 = nx.community.modularity(G, a.ev("ring_parts(ring['G'], 24, 5, True)"))
    assert q2 > q1 and "Pairing neighbouring cliques scores higher" in a.markdown()
    # below the limit, separate cliques win; a higher resolution moves the limit up
    a.set("slider", "cliques in the ring", 12)
    assert "Keeping every clique on its own scores higher" in a.markdown()
    a.set("slider", "cliques in the ring", 24)
    a.set("slider", "resolution", 1.5)
    assert "Keeping every clique on its own scores higher" in a.markdown()
    a.set("slider", "resolution", 1)
    a.press("Simulate: rings of 4 to 49 cliques")
    a.tick(30)
    rows = a.ev("ring['rows']")
    assert rows and all(r == 1.0 for n, r in rows if n < 22) and all(r > 1.0 for n, r in rows if n > 30)
    a.tab("Louvain")
    assert a.ev("graphNames()[0]") == "louvain" and not a.errors()
