"""ch15-percolation-algorithms: the Newman-Ziff algorithm step by step, bond percolation,
bigger networks against theory, and real networks under failure and attack."""
import networkx as nx

from tests.test_explainers import App


def _dropdown(a, label):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "dropdown" and w._state.get("label") == label)


def _largest_present(a, k):
    """The largest connected piece among the first k nodes to come back (site), by networkx."""
    run, net = a.ev("run"), a.ev("net")
    present = set(run["seq"][:k])
    G = nx.Graph()
    G.add_nodes_from(present)
    G.add_edges_from((x, y) for x, y in net["edges"] if x in present and y in present)
    return max((len(c) for c in nx.connected_components(G)), default=0)


def test_union_find_replay_matches_components_and_nothing_moves():
    a = App("ch15-percolation-algorithms")
    assert not a.errors()
    assert a.ev("len([v for v in g.nodes if v.visible])") == 0          # nothing there at the start
    where = a.ev("{v.name: (v.x, v.y) for v in g.nodes}")
    for k in range(1, 61):
        a.press("One step")
        if k in (5, 20, 25, 30, 45, 60):
            assert a.ev("len([v for v in g.nodes if v.visible])") == k
            assert a.ev("run['events'][-1 + run['k']]['biggest']") == _largest_present(a, k)
            # every visible edge joins two present nodes
            assert a.ev("all(e.node1.visible and e.node2.visible for e in g.edges if e.visible)")
    assert a.ev("{v.name: (v.x, v.y) for v in g.nodes}") == where                # laid out once
    assert not a.errors()
    # the step text names the newcomer with a chip; the chart has this order and GUESS's average
    assert "(guess:n" in a.markdown()
    final = a.ev("run['events'][-1]['biggest']") / 60
    avg = a.ev("average_curve()")
    assert abs(avg[-1][1] - final) < 1e-5                                       # same network, everything present (it rounds)


def test_bond_mode_hubs_last_and_simulations():
    a = App("ch15-percolation-algorithms")
    a.s.dispatch(_dropdown(a, "What comes back")._id, "change", "Edges (bond percolation)")
    for _ in range(30):
        a.press("One step")
    assert a.ev("len([v for v in g.nodes if v.visible])") == 60
    assert a.ev("len([e for e in g.edges if e.visible])") == 30
    run, net = a.ev("run"), a.ev("net")
    G = nx.Graph()
    G.add_nodes_from(range(60))
    G.add_edges_from(net["edges"][j] for j in run["seq"][:30])
    assert run["events"][29]["biggest"] == max(len(c) for c in nx.connected_components(G))
    a.s.dispatch(_dropdown(a, "What comes back")._id, "change", "Nodes (site percolation)")
    a.s.dispatch(_dropdown(a, "Order")._id, "change", "Hubs last (an attack, reversed)")
    run, net = a.ev("run"), a.ev("net")
    deg = [len(x) for x in net["nbrs"]]
    assert deg[run["seq"][-1]] == max(deg)                                     # the biggest hub comes back last
    a.tab("Bigger networks")
    a.press("Simulate: bigger networks")
    a.tick(10)
    rows = a.ev("big['rows']")
    assert [n for n, _ in rows] == [100, 400, 1600, 6400]
    big_curve = rows[-1][1]
    at_half = min(big_curve, key=lambda q: abs(q[0] - 0.5))[1]
    th = dict(a.ev("theory(3.0, [0.5])"))[0.5]
    assert abs(at_half - th) < 0.04 and min(big_curve, key=lambda q: abs(q[0] - 0.2))[1] < 0.02
    a.tab("Real networks")
    a.press("Compare all the networks")
    a.tick(10)
    table = a.ev("real['table']")
    assert len(table) == 6 and all(at >= ra for _n, _k, ra, at in table.values())
    assert not a.errors()
