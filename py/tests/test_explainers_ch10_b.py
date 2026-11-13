"""Batch 6 explainers: ch10-power-law-properties and ch10-centrality-clustering-mixing."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def test_power_law_moments_reveal_and_top_heaviness():
    a = App("ch10-power-law-properties")
    # the sample is drawn and placed first, then revealed in place
    assert a.ev("len(g.nodes)") == 300 and a.ev("len([n for n in g.nodes if n.visible])") == 0
    before = a.ev("{n.name: (n.x, n.y) for n in g.nodes}")
    a.press("Draw values one by one")
    a.tick(20)
    assert a.ev("smp['shown']") == 20 and a.ev("len([n for n in g.nodes if n.visible])") == 20
    assert a.ev("{n.name: (n.x, n.y) for n in g.nodes}") == before          # nobody moved
    a.press("All at once")
    tr = a.ev("smp['trace']")
    assert len(tr) == 300 and tr[-1][3] == max(a.ev("smp['vals']"))
    assert "mean square diverges" in a.markdown()                           # alpha = 2.5
    # 100,000 values: <x^2> keeps growing for alpha < 3 and settles near its limit for alpha = 3.5
    a.press("Simulate: 100,000 values")
    sim = a.ev("smp['sim']")
    grow = dict(sim["α = 2.2"])
    assert grow[100000] > 10 * grow[min(grow, key=lambda n: abs(n - 1000))]
    assert abs(sim["α = 3.5"][-1][1] - 5.0) < 1.5
    a.set("slider", "exponent", 3.5)
    assert a.ev("smp['shown']") == 0 and "both settle" in a.markdown()
    # top-heavy: the whole Internet's fitted exponent, and the top P% ringed in the graph
    a.s.dispatch(_tabs(a)._id, "change", "Top-heavy")
    md = a.markdown()
    assert "Internet (ASes 2006)" in md and "2.08" in md and "this sample of 300 ASes" in md
    a.set("slider", "top P", 5)
    assert a.ev("len([n for n in g.nodes if n.strokewidth == 3])") == 15
    assert a.ev("w_of_p(SEQ['Internet (ASes 2006)'], 0.05)") > 0.5            # 5% of ASes hold half the links


def test_cross_network_table_centralities_clustering_mixing():
    import networkx as nx
    a = App("ch10-centrality-clustering-mixing")
    assert "Working through the networks" in a.markdown()
    a.tick(12)                                                              # the background table fills in
    md = a.markdown()
    assert md.count("| Karate club | 34 |") == 1 and "Working through" not in md
    st = a.ev("stats_by_net")
    assert abs(st["Karate club"]["r"] - nx.degree_assortativity_coefficient(nx.karate_club_graph())) < 1e-9
    assert st["Yeast proteins"]["C"] > 3 * st["Yeast proteins"]["Cconf"]
    # centralities: the top five are ringed; the randomised comparison runs
    a.s.dispatch(_tabs(a)._id, "change", "Centralities")
    a.set("dropdown", "Measure", "betweenness")
    assert a.ev("len([n for n in g.nodes if n.strokewidth == 3])") == 5
    assert "Valjean" in [n for n in a.ev("[n.name for n in g.nodes if n.labelvisible]")]
    a.press("Simulate: random edges, same degrees")
    assert len(a.ev("cent['sim']")) == 2
    # clustering: a clicked node's triangles are green
    a.s.dispatch(_tabs(a)._id, "change", "Clustering")
    a.click("Valjean")
    G = a.ev("nx.Graph(toNetworkX(directed=False))")
    tri = nx.triangles(G, "Valjean")
    assert a.ev("len([e for e in g.edges if e.color.startswith('40,170,80')])") == tri
    assert "falls with degree" in a.markdown() and "**Valjean**: degree 36" in a.markdown()
    # mixing: the shuffles give 20 values of r for random edges with the same degrees
    a.s.dispatch(_tabs(a)._id, "change", "Mixing")
    a.press("Simulate: 20 shuffles keeping degrees")
    assert len(a.ev("mix['sim'][1]")) == 20 and "20 shuffles" in a.markdown()
    # a network in many pieces is packed; the centrality text copes with mostly-zero betweenness
    a.s.dispatch(_tabs(a)._id, "change", "Centralities")
    a.set("dropdown", "Network", "Visualisation papers")
    assert a.ev("len(g.nodes)") == 1044 and "score 0" in a.markdown()
