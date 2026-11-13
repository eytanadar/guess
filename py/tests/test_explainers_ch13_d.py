"""Batch 9 explainers: node copying, and networks designed by optimisation."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (round(v.x + v.width / 2, 6), round(v.y + v.height / 2, 6)) for v in a.s.graph._nodes_list()}


def test_node_copying_grows_in_place_and_matches_price():
    a = App("ch13-node-copying")
    assert len(a.s.graph._nodes_list()) == 200
    assert a.ev("len([v for v in g.nodes if v.visible])") == 4          # the c + 1 starting nodes
    before = {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}
    a.press("Grow it, node by node")
    a.tick(6)
    k = a.ev("st['k']")
    assert 1 <= k <= 6 and a.ev("len([v for v in g.nodes if v.visible])") == 4 + k
    last = a.ev("st['last']")
    src, new = last["src"], last["new"]
    assert len(last["copied"]) + len(last["random"]) == a.ev("len(st['outs'][st['last']['new']])")
    # the copied links really are in the copied node's list, and they are drawn purple; random ones orange
    assert set(last["copied"]) <= set(a.ev(f"st['outs'][{src}]"))
    assert a.ev(f"all(e.color == ('170,90,230' if int(e.node2.name[2:]) in st['outs'][{src}] else '245,150,40') "
                f"for e in g.edges if e.visible and e.node1.name == 'nd{new}')")
    assert a.node(f"nd{src}").strokewidth == 4 and a.node(f"nd{new}").color == "255,215,80"
    md = a.markdown()
    assert "copies the list of" in md and "(guess:n" in md and "gene duplication" in md
    a.press("All nodes at once")
    assert a.ev("all(v.visible for v in g.nodes)")
    assert {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()} == before          # nobody moved
    assert a.ev("st['indeg']") == a.ev("[v.indegree for v in sorted(g.nodes, key=lambda v: int(v.name[2:]))]")
    # theory: equivalent to Price's model with a = c(1 - copy)/copy
    assert abs(a.ev("shift_a(3, 0.5)") - 3.0) < 1e-12
    assert abs(a.ev("exact_ccdf(0, 3, 3.0)") - 1) < 1e-9
    a.tab("Distribution")
    a.press("Simulate: 20,000 nodes")
    a.tick(8)
    assert a.ev("sim['n']") == 20000
    import re
    m = re.search(r"\*\*20,000 nodes\*\* grown off screen: \*\*α = ([0-9.]+)", a.markdown())
    assert m and 2.5 < float(m.group(1)) < 3.2                         # theory 1 + 1/0.5 = 3
    a.tab("Vary copying")
    a.press("Simulate: sweep γ")
    a.tick(10)
    rows = a.ev("sweep['rows']")
    assert len(rows) == 6
    assert rows[0][1] > rows[-1][1]                                    # more copying, smaller exponent
    for gm, al, _s, alp, _sp, _mx, _mxp in rows:
        assert abs(al - alp) < 0.25                                    # copying and Price agree
    assert not a.errors(), a.errors()


def test_optimization_models_star_and_hubs():
    a = App("ch13-optimization-models")
    assert len(a.s.graph._nodes_list()) == 25
    pos = _positions(a)
    a.press("Optimise: hill climb")
    a.tick(80)
    assert a.ev("net.tried") > 300
    # at the default lambda (10^-1.5, above 2/(n^2+2)) the climber reaches the star: 24 edges, one hub
    assert a.ev("len(g.edges)") == 24 and a.ev("max(v.degree for v in g.nodes)") == 24
    assert "local minimum" in a.markdown() and "the star" in a.markdown()
    assert _positions(a) == pos                                        # only edges change
    # drawn edges always match the matrix
    assert a.ev("int(net.A.sum()) // 2") == a.ev("len(g.edges)")
    # quality(): the star's E matches the formula
    assert abs(a.ev("quality(net.A, net.W, net.lam)[0]") - a.ev("net.lam * 24 + (1 - net.lam) * (2 - 2 / 25)")) < 1e-9
    a.press("Simulate: sweep λ")
    a.tick(12)
    rows = a.ev("sweep_h['rows']")
    assert len(rows) == 9
    assert rows[0][1] > 250                                                             # tiny lambda: (nearly) complete
    assert any(hub == 24 and m == 24 for _l, m, _e, hub in rows)                        # a star somewhere
    assert rows[-1][3] < 24 and rows[-1][1] <= 26                                       # large lambda: a stuck tree
    a.tab("Roads or airlines")
    assert len(a.s.graph._nodes_list()) == 30 and a.ev("len(g.edges)") == 29            # starts from the shortest tree
    a.press("Airlines (δ = 1)")
    a.press("Finish now")
    hub_air = a.ev("max(v.degree for v in g.nodes)")
    a.press("Roads (δ = 0)")
    pos = _positions(a)
    a.press("Finish now")
    hub_road = a.ev("max(v.degree for v in g.nodes)")
    assert hub_air > 2 * hub_road                                      # airlines: hubs; roads: none
    assert _positions(a) == pos
    assert "road map" in a.markdown()
    a.press("Simulate: sweep δ")
    a.tick(10)
    rows = a.ev("sweep_m['rows']")
    assert len(rows) == 6 and rows[-1][2] > rows[0][2]
    assert not a.errors(), a.errors()
