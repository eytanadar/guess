"""Batch 5 explainer: maximum flow by augmenting paths."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401  (the fixture runs in the data folder)


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def _maxflow(caps, src, snk):
    D = nx.DiGraph()
    for (u, v), c in caps.items():
        D.add_edge(u, v, capacity=c)
    return nx.maximum_flow_value(D, src, snk)


def test_augmenting_paths_reach_the_min_cut():
    a = App("ch08-maxflow")
    assert "flow / capacity" in a.markdown()
    a.press("Step")                                   # find the first path
    assert "Augmenting path 1" in a.markdown() and "(guess:n" in a.markdown()
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())
    a.press("Step")                                   # push it
    assert "Pushed" in a.markdown() and a.ev("NETS['flow']['value']") > 0
    a.press("Run")
    a.tick(60)
    net = a.ev("NETS['flow']")
    assert net["phase"] == "done"
    assert net["value"] == _maxflow(net["caps"], "S", "T") == 28
    assert "max-flow = min-cut" in a.markdown() and "= **28**" in a.markdown()
    cut = a.ev("cut_edges(NETS['flow'])")
    assert sum(net["caps"][c] for c in cut) == 28
    assert a.ev("flow_chart()") is not None
    # the residual view: forward edges show room left, backward edges the flow that could be sent back
    a.set("dropdown", "Show", "Residual network (room left, each way)")
    back = [e for e in a.s.graph._edges_list() if e.role == "back" and e.visible]
    assert back and all(int(e.label) > 0 for e in back)
    assert all(e.arc == 14 for e in back)


def test_bad_first_path_gets_cancelled():
    a = App("ch08-maxflow")
    a.set("dropdown", "Network", "Flow that has to be cancelled")
    assert "straight through the middle" in a.markdown()
    a.press("Step")
    a.press("Step")                                   # 5 units along S-A-B-T
    assert a.ev("NETS['flow']['flow'][('A', 'B')]") == 5
    a.press("Step")                                   # the next path goes backwards from B to A
    assert "goes **backwards** from B to A" in a.markdown()
    a.press("Step")
    assert a.ev("NETS['flow']['flow'][('A', 'B')]") == 0 and "**cancelled** 5" in a.markdown()
    a.press("Run")
    a.tick(20)
    assert a.ev("NETS['flow']['value']") == 10


def test_simulate_shortest_against_any():
    a = App("ch08-maxflow")
    _tab(a, "Which path?")
    a.press("Simulate: shortest paths against any paths")
    rows = a.ev("sim['rows']")
    assert len(rows) == 4 and all(b <= d for _, b, d in rows)
    assert a.ev("sim_chart()") is not None and "paths when taking the shortest" in a.markdown()


def test_node_independent_paths_by_splitting():
    a = App("ch08-maxflow")
    _tab(a, "Node-independent paths")
    assert a.ev("graphNames()[0]") == "split" and len(a.s.graph._nodes_list()) == 20
    a.press("All at once")
    base = a.ev("BASE")
    k = nx.node_connectivity(base, "v0", "v9")
    assert a.ev("NETS['split']['value']") == k
    md = a.markdown()
    assert f"**{k} node-independent paths**" in md and "node connectivity agrees" in md
    # choose new ends by clicking: v2 then v8
    a.click("v2i")
    a.click("v8o")
    assert a.ev("ends['a']") == "v2" and a.ev("ends['b']") == "v8"
    a.press("Next step")
    assert "Augmenting path 1" in a.markdown()
    a.press("Play")
    a.tick(80)
    assert a.ev("NETS['split']['value']") == nx.node_connectivity(base, "v2", "v8")
    _tab(a, "The algorithm")
    assert a.ev("graphNames()[0]") == "network"


def test_adjacent_ends_count_the_direct_link_once():
    a = App("ch08-maxflow")
    _tab(a, "Node-independent paths")
    a.click("v0o")
    a.click("v1i")                                    # neighbours
    a.press("All at once")
    base = a.ev("BASE")
    H = base.copy()
    H.remove_edge("v0", "v1")
    expect = 1 + nx.node_connectivity(H, "v0", "v1")
    assert a.ev("NETS['split']['value']") == expect
    assert "They are neighbours" in a.markdown()
