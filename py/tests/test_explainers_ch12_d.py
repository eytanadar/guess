"""Batch 8 explainers: other random graph models, and the small-world model."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_other_models_each_tab():
    a = App("ch12-other-models")
    # directed: the bow tie field matches networkx's strongly connected core
    G = a.ev("toNetworkX()")
    core = max(nx.strongly_connected_components(G), key=len)
    assert a.ev("len([v for v in g.nodes if v.bowtie == 'core'])") == len(core)
    assert "bow tie" in a.markdown()
    a.press("Simulate: bow tie against c")
    a.tick(15)
    rows = a.ev("st['sim']")
    assert len(rows) == 13 and rows[-1][1] > rows[0][1]          # the core grows with c
    # bipartite: edges only between people and groups; the projection is far more clustered than random
    _tab(a, "Bipartite")
    assert a.ev("all(e.node1.side != e.node2.side for e in g.edges)")
    a.press("Project onto the people")
    P = a.ev("st['P']")
    assert nx.transitivity(P) > 2 * a.ev("config_C([d for _v, d in st['P'].degree()])")
    a.press("Back to people and groups")
    # acyclic: no cycles, every edge to an earlier node
    _tab(a, "Acyclic")
    assert a.ev("all(int(e.node1.name[1:]) > int(e.node2.name[1:]) for e in g.edges)")
    assert "no cycles" in a.markdown()
    # clustered: C stays roughly flat while the configuration model's falls
    _tab(a, "Clustered")
    a.press("Simulate: C as n grows")
    a.tick(8)
    rows = a.ev("st['sim']")
    assert len(rows) == 6 and rows[-1][1] > 0.12 and rows[-1][2] < rows[0][2] / 5
    # communities: block field, Louvain agreement, the sweep
    _tab(a, "Communities")
    assert a.ev("sorted(set(v.block for v in g.nodes))") == [0, 1, 2]
    a.press("Find the communities")
    assert a.ev("st['found']['nmi']") > 0.6 and "Louvain" in a.markdown()
    a.set("slider", "neighbours outside it", 6)
    assert "below the limit" in a.markdown()
    a.press("Simulate: when can they be found?")
    a.tick(13)
    rows = sorted(a.ev("st['sim']"))
    assert rows[-1][1] > 0.9 and rows[0][1] < 0.3                  # clear groups found; near the limit, not
    a.press("Another random draw")


def test_small_world_shortcuts_collapse_distance_not_clustering():
    a = App("ch12-small-world-model")
    pos = {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}
    assert a.ev("len([e for e in g.edges if e.visible and e.kind == 'shortcut'])") == 0
    a.press("Rewire one by one")
    a.tick(10)
    assert a.ev("len(rewired())") == 10
    assert abs(a.ev("pslider.value") - __import__("math").log10(a.ev("st['p']"))) < 0.01   # the slider follows
    assert a.ev("len([e for e in g.edges if e.visible and e.kind == 'shortcut'])") == 10
    assert sum(1 for e in a.s.graph._edges_list() if e.visible and e.linestyle == "flow") == 1
    C, L = a.ev("measures()")
    C0, L0 = a.ev("C0"), a.ev("L0")
    assert L / L0 < 0.6 and C / C0 > 0.7 and L / L0 < C / C0 - 0.15   # distances fall much faster than clustering
    assert {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()} == pos   # nodes stay on the ring
    a.click("r0")
    assert a.ev("g.getNodeByName('r0').label") == "0" and a.ev("g.getNodeByName('r1').label") == "1"
    a.set("slider", "log₁₀ p", 0)
    assert a.ev("len(rewired())") > 100
    _tab(a, "Simulate")
    a.press("Simulate: C(p) and ℓ(p)")
    a.tick(45)
    cs, ls = a.ev("sim_points()")
    assert cs[-1][1] < 0.2 and ls[-1][1] < 0.35 and "small world" in a.markdown()
    _tab(a, "Dynamic networks")
    assert "Networks that change" in a.markdown()
