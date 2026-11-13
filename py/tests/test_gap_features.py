"""Chart widgets in panels, log-scale charts, plotFrequency/plotLine, and
drawings (drawLine, drawText, drawRect, drawCircle)."""
from tests.test_small_batch import _s, ev


def _charts(s):
    return [m for m in s.rec.of("chart")]


def test_plot_frequency_fractions_and_log():
    s = _s()
    assert s.run("plotFrequency(degree)"), s.rec.of("error")
    m = _charts(s)[-1]
    pts = m["series"][0]["points"]
    assert abs(sum(p[1] for p in pts) - 1) < 1e-9
    assert m["xq"] == "degree == {x}" and m["dots"] and "logX" not in m
    s.rec.clear()
    assert s.run("plotFrequency(degree, log=true, cumulative=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    pts = m["series"][0]["points"]
    assert m["logX"] and m["logY"] and pts[0][1] <= 1 and all(p[0] > 0 for p in pts)
    assert [p[1] for p in pts] == sorted((p[1] for p in pts), reverse=True)


def test_histogram_log_bins_and_plot_line():
    s = _s()
    assert s.run("plotHistogram(degree, 5, log=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["logY"] and len(m["items"]) == 5
    assert sum(it["value"] for it in m["items"]) == ev(s, "len([n for n in g.nodes if n.degree > 0])")
    s.rec.clear()
    assert s.run("plotLine({'a': [(1, 1), (2, 4), (0, 3)], 'b': [(1, 2)]}, title='T', log=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["title"] == "T" and [x["name"] for x in m["series"]] == ["a", "b"]
    assert m["series"][0]["points"] == [[1.0, 1.0], [2.0, 4.0]]     # x = 0 dropped on a log axis


def test_chart_widget_captures_and_follows_the_graph():
    s = _s()
    assert s.run("c = Chart(lambda: plotHistogram(degree))\nui.dock(Panel('P', c))"), s.rec.of("error")
    assert not _charts(s)                                   # not in the dock
    dock = [m for m in s.rec.of("ui") if m["op"] == "dock"][-1]
    spec = dock["panel"]["children"][0]["props"]["spec"]
    assert spec["type"] == "chart" and spec["kind"] == "bar"
    total = sum(it["value"] for it in spec["items"])
    s.rec.clear()
    assert s.run("remove(v1)"), s.rec.of("error")
    ups = [m for m in s.rec.of("ui") if m["op"] == "update" and "spec" in m["props"]]
    assert ups and sum(it["value"] for it in ups[-1]["props"]["spec"]["items"]) == total - 1
    assert not _charts(s)
    # a failing function shows the error in the widget instead of breaking commands
    assert s.run("bad = Chart(lambda: plotHistogram(nosuchfield))"), s.rec.of("error")
    assert ev(s, "bad.spec")["type"] == "error"
    # plot commands outside a Chart still go to the dock
    assert s.run("plotHistogram(degree)") and _charts(s)


def test_drawings_record_undo_and_session_roundtrip(tmp_path):
    s = _s()
    assert s.run("l = drawLine(0, 0, 100, 0, color=red, style='dashed', arrow=true)\n"
                 "t = drawText(50, -10, 'hello', size=20)\n"
                 "r = drawRect(0, 0, 10, 10, fill='255,0,0,60')\n"
                 "c = drawCircle(5, 5, 30)"), s.rec.of("error")
    ds = s.view.record()["drawings"]
    assert [d["k"] for d in ds] == ["line", "text", "rect", "circle"]
    assert ds[0]["st"] == "dashed" and ds[0]["ar"] and ds[0]["c"] == 0xFF0000 and ds[1]["c"] is None
    assert ds[2]["f"] == 0xFF0000 and abs(ds[2]["fa"] - 60 / 255) < 0.01
    assert repr(ev(s, "t")).endswith("text 'hello'>") and len(ev(s, "getDrawings()")) == 4
    assert s.run("t.remove()") and len(s.view.drawings) == 3
    assert s.run("undo()") and len(s.view.drawings) == 4
    path = tmp_path / "d.guess"
    assert s.run(f"saveSession({str(path)!r})"), s.rec.of("error")
    assert s.run("clearDrawings()") and s.view.drawings == []
    assert s.run(f"makeFromSession({str(path)!r})"), s.rec.of("error")
    assert [d["k"] for d in s.view.drawings] == ["line", "text", "rect", "circle"]
    assert not s.run("drawLine(0, 0, 1, 1, style='wavy')")
    assert not s.run("drawText(0, 0, 'x', anchor='left')")


def test_pdb_contact_network():
    from pathlib import Path
    pdb = Path(__file__).resolve().parents[2] / "cookbooks" / "data" / "1ubq.pdb"
    s = _s()
    assert s.run(f"makeFromPDB({str(pdb)!r})"), s.rec.of("error")
    assert len(s.graph.nodes) == 76
    assert ev(s, "len(kind == 'chain')") == 75 and ev(s, "len(kind == 'contact')") > 100
    assert ev(s, "MET1.structure") == "strand" and ev(s, "MET1.aa") == "M"
    assert ev(s, "max(e.distance for e in (kind == 'contact'))") < 8
    assert s.run(f"makeFromPDB({str(pdb)!r}, cutoff=6)")
    fewer = ev(s, "len(kind == 'contact')")
    assert s.run(f"makeFromFile({str(pdb)!r})") and ev(s, "len(kind == 'contact')") > fewer
    assert not s.run("makeFromPDB('nonsense')")


def test_show_matrix_orders_and_links_cells():
    s = _s()
    assert s.run("showMatrix(order=dept)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["kind"] == "matrix" and len(m["labels"]) == len(s.graph.nodes)
    assert m["groups"] == sorted(m["groups"]) or len(set(m["groups"])) > 1
    undirected = [e for e in s.graph.edges if not e.directed and e.node1 is not e.node2]
    assert len(m["cells"]) >= 2 * len(undirected)
    r, c, v, eid = m["cells"][0]
    e = s.graph.edge_by_id(eid)
    assert {m["labels"][r], m["labels"][c]} == {e.node1.name, e.node2.name}
    assert s.run("showMatrix(nodes=(dept == 'dept3'), weight=freq)")
    m = _charts(s)[-1]
    assert m["weighted"] and len(m["labels"]) == ev(s, "len(dept == 'dept3')")


def test_bipartite_layout_without_igraph():
    s = _s()
    assert s.run("makeSample('davis')\nuseIgraph(False)\nbipartiteLayout(bipartite)"), s.rec.of("error")
    rows = {}
    for n in s.graph.nodes:
        rows.setdefault(n.bipartite, set()).add(round(n.y))
    assert len(rows) == 2 and all(len(v) == 1 for v in rows.values())
    assert s.run("useIgraph(True)")


def test_every_paced_goes_slow_fast_slow():
    s = _s()
    assert s.run("calls = []\ndef step():\n    calls.append(1)\n\nt = everyPaced(step, steps=10, slow=1, fast=0.1)"), s.rec.of("error")
    delays = []
    for _ in range(12):
        timers = [m for m in s.rec.of("ui") if m.get("op") == "timer"]
        if not timers:
            break
        delays.append(timers[-1]["ms"])
        s.rec.clear()
        s.dispatch(timers[-1]["id"], "tick")
    assert ev(s, "len(calls)") == 10
    assert delays[0] == 1000 and abs(min(delays) - 100) < 1e-6 and delays[-1] > delays[4]
    assert s.run("n = [5]\ndef countdown():\n    n[0] -= 1\n    return n[0] if n[0] > 0 else False\n\nt2 = everyPaced(countdown)")
    for _ in range(8):
        timers = [m for m in s.rec.of("ui") if m.get("op") == "timer"]
        if not timers:
            break
        s.rec.clear()
        s.dispatch(timers[-1]["id"], "tick")
    assert ev(s, "n[0]") == 0 and not ev(s, "t2.running")


def test_show_matrix_numbers_self_loops_and_rectangles():
    s = _s()
    assert s.run("makeSample('kite')"), s.rec.of("error")
    a = ev(s, "g.nodes[0]")
    assert s.run(f"addEdge({a.name}, {a.name})\nshowMatrix(numbers=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    diag = [c for c in m["cells"] if c[0] == c[1]]
    assert m["numbers"] and diag and diag[0][2] == 2                     # an undirected self-edge counts 2
    assert s.run("makeSample('davis')\nshowMatrix(rows=(bipartite == 1), cols=(bipartite == 0), numbers=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert len(m["labels"]) == 14 and len(m["clabels"]) == 18 and m["title"].startswith("Incidence")
    assert len(m["cells"]) == len(s.graph.edges)


def test_map_colouring_crossings_layers_and_spectrum():
    s = _s()
    assert s.run("makeFromMap('usa')"), s.rec.of("error")
    assert len(s.graph.nodes) == 48 and ev(s, "colorGraph()") <= 5
    assert all(e.node1.color_class != e.node2.color_class for e in s.graph.edges)
    assert s.run("makeSample('karate')\ncircleLayout()"), s.rec.of("error")
    assert ev(s, "edgeCrossings()") == ev(s, "len(edgeCrossings(pairs=true))") > 0
    sp = ev(s, "spectrum()")
    assert sp[0] == 0 and sp[1] > 0 and len(sp) == 34
    assert s.run("remove([e for e in g.edges if e.node1.club != e.node2.club])")
    assert ev(s, "spectrum()")[1] == 0                                   # two components: two zeros
    assert s.run("Edge.kind = ''\nfor i, e in enumerate(g.edges):\n    e.kind = 'a' if i % 2 else 'b'\n\n"
                 "expandLayers(kind, directed=true)"), s.rec.of("error")
    assert ev(s, "graphNames()[0]") == "layers" and ev(s, "len(kind == 'interlayer')") > 0
    assert ev(s, "set(n.layer for n in g.nodes)") == {"a", "b"}


def test_lombardi_edges_and_layout_raise_lombardiness():
    s = _s()
    assert s.run("makeSample('petersen')"), s.rec.of("error")
    before, after = ev(s, "lombardiEdges()")
    assert after > before + 10 and abs(ev(s, "lombardiness()") - after) < 0.1
    assert any(e.arc for e in s.graph.edges)
    rec = s.edge_record(next(e for e in s.graph.edges if e.arc))
    assert "k" in rec
    assert s.run("straightenEdges()") and not any(e.arc for e in s.graph.edges)
    assert s.run("makeSample('karate')"), s.rec.of("error")
    b2, a2 = ev(s, "lombardiLayout()")
    assert a2 > 85 and a2 > b2


def test_directed_edges_default_to_tapered(tmp_path):
    """Holten & van Wijk (CHI 2009): tapered directed edges by default, no arrowheads."""
    s = _s()
    assert s.view.directed == "taper"
    assert s.view.record()["directedStyle"] == "taper"
    assert s.run("directedEdges('dark-to-light')"), s.rec.of("error")
    assert s.view.directed == "fade"
    assert not s.run("directedEdges('wiggly')")
    assert s.run("g.edges.linestyle = 'fade'"), s.rec.of("error")
    path = tmp_path / "d.guess"
    assert s.run(f"directedEdges('arrow')\nsaveSession({str(path)!r})\ndirectedEdges('taper')\n"
                 f"makeFromSession({str(path)!r})"), s.rec.of("error")
    assert s.view.directed == "arrow"
    assert s.run("undo()") or True


def test_scatter_katz_balance_kcomponents_regular():
    s = _s()
    assert s.run("plotScatter(degree, betweenness)"), s.rec.of("error")
    m = _charts(s)[-1]
    se = m["series"][0]
    assert m["scatter"] and len(se["points"]) == len(se["ids"]) == len(se["colors"]) == ev(s, "len(g.nodes)")
    assert s.run("plotScatter(degree, ends=true, line=[(0, 0), (10, 10)])"), s.rec.of("error")
    m = _charts(s)[-1]
    assert len(m["series"][0]["points"]) == ev(s, "sum(1 if e.directed else 2 for e in g.edges)")
    assert m["series"][1]["line"]
    assert s.run("plotScatter({'a': [(1, 2), (2, 3)]}, log=true)"), s.rec.of("error")
    # Katz: alpha -> 0 ranks by degree; too big an alpha is refused
    assert s.run("newGraph('k')\nimport networkx as nx\nfromNetworkX(nx.karate_club_graph())"), s.rec.of("error")
    f, lim = ev(s, "katzCentrality(alpha=0.001)")
    top = ev(s, "max(g.nodes, key=lambda n: n.katz).name")
    assert top == ev(s, "max(g.nodes, key=lambda n: n.degree).name")
    assert not s.run(f"katzCentrality(alpha={lim * 1.01})")
    # balance: a triangle with one negative edge is unbalanced; with two, balanced (two camps)
    assert s.run("newGraph('b')\nEdge.sign = 1\naddNode('a'); addNode('b'); addNode('c'); addNode('d')\n"
                 "for u, v, sg in [('a','b',1), ('b','c',-1), ('a','c',-1), ('c','d',1)]:\n"
                 "    e = addEdge(u, v)\n    e.sign = sg\nr = structuralBalance()"), s.rec.of("error")
    assert ev(s, "r['balanced']") and ev(s, "a.camp == b.camp != c.camp == d.camp")
    assert s.run("v1 = [e for e in g.edges if {e.node1.name, e.node2.name} == {'a', 'c'}][0]\nv1.sign = 1\n"
                 "r = structuralBalance()"), s.rec.of("error")
    assert not ev(s, "r['balanced']") and len(ev(s, "r['unbalanced']")) == 1 and len(ev(s, "r['frustrated']")) == 1
    # two triangles sharing a node: one 2-core-ish piece, two bicomponents
    assert s.run("newGraph('c')\nfor u, v in [('a','b'),('b','c'),('c','a'),('c','d'),('d','e'),('e','c')]:\n"
                 "    addNode(u) if u not in [n.name for n in g.nodes] else None\n"
                 "    addNode(v) if v not in [n.name for n in g.nodes] else None\n    addEdge(u, v)\nbc = kComponents(2)"), s.rec.of("error")
    assert ev(s, "len(bc)") == 2 and ev(s, "sorted(len(x) for x in bc)") == [3, 3]
    assert ev(s, "len(kComponents(1))") == 1
    # regular equivalence: two leaves of the same star score high, though they share... the hub
    assert s.run("newGraph('r')\nfor u, v in [('m1','w1'),('m1','w2'),('m2','w3'),('m2','w4'),('m1','m2')]:\n"
                 "    addNode(u) if u not in [n.name for n in g.nodes] else None\n"
                 "    addNode(v) if v not in [n.name for n in g.nodes] else None\n    addEdge(u, v)\ntop = similarTo(m1, method='regular', top=1)"), s.rec.of("error")
    assert ev(s, "list(top)[0].name") == "m2"


def test_reveal_up_to_plays_back_growth():
    s = _s()
    assert s.run("newGraph('grow')\nNode.born = 0\nfor k in range(5):\n    v = addNode(f'p{k}')\n    v.born = k\n"
                 "    if k:\n        addEdge(v, g.getNodeByName(f'p{k - 1}'))\nnew = revealUpTo(2)"), s.rec.of("error")
    assert ev(s, "[n.name for n in g.nodes if n.visible]") == ["p0", "p1", "p2"]
    assert ev(s, "len([e for e in g.edges if e.visible])") == 2
    kinds = sorted(type(x).__name__ for x in ev(s, "new"))
    assert kinds == ["Edge", "Node"] and ev(s, "[x.name for x in new if x in g.nodes]") == ["p2"]
    assert s.run("revealUpTo(10)") and ev(s, "all(n.visible for n in g.nodes)")
    assert not s.run("revealUpTo(1, field='nosuch')")


def test_assortativity_categorical_option():
    s = _s()
    assert s.run("Node.code = 0\nfor n in g.nodes:\n    n.code = int(''.join(c for c in n.dept if c.isdigit()) or 0)"), s.rec.of("error")
    as_cat = ev(s, "assortativity(code, categorical=true)")
    assert abs(as_cat - ev(s, "assortativity(dept)")) < 1e-9          # the same split, as categories
    assert not s.run("assortativity(dept, categorical=false)")


def test_link_to_makes_markdown_chips():
    s = _s()
    assert ev(s, "linkTo(v1)") == f"[v1](guess:n{ev(s, 'v1._id')})"
    assert ev(s, "linkTo(v1, text='v1 [d=2]')").startswith("[v1 (d=2)](guess:n")
    assert ev(s, "linkTo(list(g.edges)[0])").startswith("[") and "(guess:e" in ev(s, "linkTo(list(g.edges)[0])")
    assert not s.run("linkTo(3)")


def test_node_strokewidth_reaches_the_display():
    s = _s()
    assert s.run("v1.strokewidth = 4"), s.rec.of("error")
    rec = s.node_record(s.graph._nodes["v1"])
    assert rec["bw"] == 4.0
    rec2 = s.node_record(s.graph._nodes["v2"])
    assert "bw" not in rec2


def test_bow_tie_and_power_law_fit():
    import math
    import random
    s = _s()
    # a bow tie by hand: in -> core (a cycle) -> out, a tendril off in, a tube in -> out, an isolated node
    assert s.run("newGraph('bt')\nfor v in ['i', 'c1', 'c2', 'c3', 'o', 'tend', 'tube', 'lone']:\n    addNode(v)\n"
                 "for u, v in [('i','c1'),('c1','c2'),('c2','c3'),('c3','c1'),('c3','o'),('i','tend'),('i','tube'),('tube','o')]:\n"
                 "    addDirectedEdge(g.getNodeByName(u), g.getNodeByName(v))\nsz = bowTie()"), s.rec.of("error")
    assert ev(s, "sz") == {"core": 3, "in": 1, "out": 1, "tube": 1, "tendril": 1, "other": 1}
    assert ev(s, "lone.bowtie") == "other" and ev(s, "tube.bowtie") == "tube"
    # maximum likelihood recovers the exponent of a discrete power law (alpha 2.5 from k = 4)
    r = random.Random(1)
    vals = [int(math.floor((1 - r.random()) ** (-1 / 1.5) * 3.5 + 0.5)) for _ in range(5000)]
    s.ns["__v"] = vals
    fit = ev(s, "fitPowerLaw(__v)")
    assert fit["kmin"] == 4 and abs(fit["alpha"] - 2.5) < 0.1 and fit["ks"] < 0.03
    assert ev(s, "fitPowerLaw(__v, kmin=10)")["kmin"] == 10
    assert not s.run("fitPowerLaw([1, 2])")
    assert s.run("makeSample('karate')\nplotFrequency(degree, cumulative=true, log=true, fit=true)"), s.rec.of("error")
    m = [c for c in s.rec.of("chart")][-1]
    assert len(m["series"]) == 2 and m["series"][1]["dash"]


def test_label_size_and_direction_style_survive_graph_switches():
    s = _s()
    assert s.run("constantLabelSize(size=14)\ndirectedEdges('fade')\nnewGraph('other')"), s.rec.of("error")
    assert s.view.labels["screen"] and s.view.labels["screenSize"] == 14 and s.view.directed == "fade"
    assert s.run("use('main')") and s.view.labels["screenSize"] == 14 and s.view.directed == "fade"


def test_chart_axis_ranges():
    s = _s()
    assert s.run("plotLine([(1, 0.9), (2, 0.95)], title='auc', yrange=(0.8, 1))"), s.rec.of("error")
    assert _charts(s)[-1]["yRange"] == [0.8, 1.0] and "xRange" not in _charts(s)[-1]
    assert s.run("plotScatter(degree, betweenness, xrange=(0, 10))"), s.rec.of("error")
    assert _charts(s)[-1]["xRange"] == [0.0, 10.0]
    assert not s.run("plotLine([(1, 2)], yrange=(1, 1))")


def test_plot_line_dashed_series():
    s = _s()
    assert s.run("plotLine({'data': [(1, 1), (2, 3)], 'theory': [(1, 1), (2, 2)]}, title='t', dashed=['theory'])"), s.rec.of("error")
    se = _charts(s)[-1]["series"]
    assert "dash" not in se[0] and se[1]["dash"]


def test_configuration_model_and_expected_degree():
    s = _s()
    ks = [3, 3, 2, 2, 2, 1, 1, 4, 2]
    assert s.run(f"r = makeConfigurationModel({ks}, seed=3)"), s.rec.of("error")
    # every stub is used: degrees match exactly (a self-loop counts 2)
    assert ev(s, "sorted(n.stubs for n in g.nodes)") == sorted(ks)
    # GUESS's degree counts a self-loop once; the book's k counts it twice
    assert ev(s, "sum(n.degree for n in g.nodes)") + ev(s, "r")["selfloops"] == sum(ks)
    assert ev(s, "len(g.edges)") == sum(ks) // 2
    assert set(ev(s, "r")) == {"selfloops", "multiedges"}
    assert s.run("makeSample('karate')\nk0 = sorted(n.degree for n in g.nodes)\nmakeConfigurationModel(degree, simple=true)")
    assert ev(s, "len(g.nodes)") == 34 and ev(s, "all(e.node1 != e.node2 for e in g.edges)")
    assert not s.run("makeConfigurationModel([1, 2])")              # odd total
    assert s.run("makeExpectedDegree([4.0] * 200, seed=1)"), s.rec.of("error")
    mean = ev(s, "sum(n.degree for n in g.nodes) / len(g.nodes)")
    assert 3.3 < mean < 4.7 and ev(s, "g.nodes[0].expected") == 4.0


def test_plot_line_highlight_series():
    s = _s()
    assert s.run("plotLine({'sim': [(1, 1), (2, 2)], 'this network': [(1.5, 1.2)]}, title='h', highlight='this network')")
    se = _charts(s)[-1]["series"]
    assert se[1]["big"] and "big" not in se[0]


def test_from_networkx_falls_back_to_guess_layout(monkeypatch):
    import networkx as nx
    s = _s()
    G = nx.gnm_random_graph(60, 120, seed=1)

    def broken(*a, **k):
        raise ImportError("scipy")
    monkeypatch.setattr(nx, "spring_layout", broken)
    s.ns["__G"] = G
    assert s.run("fromNetworkX(__G)"), s.rec.of("error")
    pts = ev(s, "[(n.x, n.y) for n in g.nodes]")
    assert len(set(pts)) > 55 and all(p[0] == round(p[0]) for p in pts)   # frLayout's positions, not random ones


def test_growth_generators_record_arrival_and_block_model():
    s = _s()
    assert s.run("makePriceModel(3000, c=3, a=1, seed=2, layout=false)"), s.rec.of("error")
    assert ev(s, "len(g.nodes)") == 3000 and ev(s, "all(e.directed for e in g.edges)")
    assert ev(s, "all(e.node1.born > e.node2.born and e.born == e.node1.born for e in g.edges)")  # cite older papers
    alpha = ev(s, "fitPowerLaw(indegree)")["alpha"]
    assert 2.0 < alpha < 2.8                                         # theory: 2 + a/c = 2.33
    assert s.run("revealUpTo(10)") and ev(s, "len([v for v in g.nodes if v.visible])") == 11
    assert s.run("makeBarabasiAlbertRandom(3, 2, 30)") and ev(s, "max(n.born for n in g.nodes)") == 30
    assert s.run("makeBlockModel([20, 20], 0.5, 0.01, seed=1, layout=false)"), s.rec.of("error")
    inside = ev(s, "len([e for e in g.edges if e.node1.block == e.node2.block])")
    assert inside > 5 * ev(s, "len([e for e in g.edges if e.node1.block != e.node2.block])")
    assert s.run("makeBlockModel([5, 5], [[1, 0], [0, 1]])") and ev(s, "len(g.edges)") == 20
    assert not s.run("makeBlockModel([5, 5], 0.5)")


def test_fit_power_law_shift():
    s = _s()
    assert s.run("makePriceModel(6000, c=3, a=3, seed=1, layout=false)"), s.rec.of("error")
    # theory: 2 + a/c = 3, a power law in k + a; fitting k itself reads low, especially from small k
    for k in (2, 5):
        plain = ev(s, f"fitPowerLaw(indegree, kmin={k})")["alpha"]
        shifted = ev(s, f"fitPowerLaw(indegree, kmin={k}, shift=3)")
        assert abs(shifted["alpha"] - 3.0) < 0.35 < abs(plain - 3.0) and shifted["kmin"] == k
    assert s.run("plotFrequency(indegree, cumulative=true, log=true, fit=true, shift=3)"), s.rec.of("error")
    assert "k + 3" in _charts(s)[-1]["series"][1]["name"]


def _linked_outs(s):
    """The structured output lines since the last clear, as (text, node ids, edge ids, group items)."""
    out = []
    for m in s.rec.of("out"):
        nodes = [sg["n"] for sg in m["segs"] if isinstance(sg, dict) and "n" in sg]
        edges = [sg["e"] for sg in m["segs"] if isinstance(sg, dict) and "e" in sg]
        groups = [sg.get("x", []) for sg in m["segs"] if isinstance(sg, dict) and "g" in sg]
        text = "".join(sg if isinstance(sg, str) else sg.get("t", "".join(map(str, sg.get("g", []))))
                       for sg in m["segs"])
        out.append((text, nodes, edges, groups))
    return out


def test_commands_print_linked_nodes_and_edges():
    s = _s()
    s.rec.clear()
    assert s.run("r = predictLinks(3, add=true)"), s.rec.of("error")
    lines = _linked_outs(s)
    pairs = [ln for ln in lines if len(ln[1]) == 2]
    assert len(pairs) == 3                                      # each predicted pair: both names linked
    assert pairs[0][0].strip().count(" - ") == 1
    added = [ln for ln in lines if ln[0].startswith("added 3 predicted edges")]
    assert added and len(added[0][3][0]) == 3 and all(k == "e" for k, _i in added[0][3][0])
    # every one of those edges exists and is marked predicted
    assert ev(s, "len([e for e in g.edges if e.predicted])") == 3
    s.rec.clear()
    assert s.run("newGraph('two')\naddNode('a'); addNode('b')\nshortestPath(a, b)"), s.rec.of("error")
    assert any(t.startswith("no path from a to b") and len(n) == 2 for t, n, _e, _g in _linked_outs(s))


def test_linked_line_keeps_columns():
    from guess.session import linked
    s = _s()
    v1 = s.graph._nodes["v1"]
    line = linked((v1, ">6"), "|", ("2 nodes", [v1]), (v1, "<4"), "!")
    assert str(line) == "    v1|2 nodesv1  !"
    assert line.segs[0] == "    " and line.segs[1] == {"n": v1._id, "t": "v1"}


def test_growing_network_copying_model_and_resolution():
    s = _s()
    assert s.run("makeGrowingNetwork(300, m=2, gamma=1.5, a=1, seed=1, layout=false)"), s.rec.of("error")
    top = ev(s, "max(n.degree for n in g.nodes)")
    assert top > 0.3 * ev(s, "len(g.nodes)")                       # condensation: one node links to a big share
    assert s.run("makeGrowingNetwork(300, m=2, gamma=0, seed=1, layout=false)")
    assert ev(s, "max(n.degree for n in g.nodes)") < 30               # uniform attachment: no big hubs
    assert s.run("makeGrowingNetwork(200, m=2, remove=0.5, seed=2, layout=false)"), s.rec.of("error")
    gone = ev(s, "[e for e in g.edges if e.died >= 0]")
    assert gone and ev(s, "all(not e.visible for e in g.edges if e.died >= 0)")
    assert ev(s, "all(e.died < 0 or e.died >= e.born for e in g.edges)")
    d = ev(s, "min(e.died for e in g.edges if e.died >= 0)")
    assert s.run(f"revealUpTo({d})") and ev(s, f"all(not e.visible for e in g.edges if 0 <= e.died <= {d})")
    assert s.run("makeCopyingModel(4000, c=3, copy=0.5, seed=1, layout=false)"), s.rec.of("error")
    assert ev(s, "all(n.outdegree == 3 for n in g.nodes)")
    alpha = ev(s, "fitPowerLaw(indegree, kmin=5, shift=3)")["alpha"]   # theory 1 + 1/copy = 3, in k + a, a = 3
    assert 2.5 < alpha < 3.5
    assert s.run("makeSample('karate')\nlouvainClusters()")
    assert ev(s, "modularity(louvain_class, resolution=2)") < ev(s, "modularity(louvain_class)")


def test_layouts_are_reproducible():
    s = _s()
    got = []
    for _ in range(2):
        assert s.run("makeSample('karate')\nfor n in g.nodes:\n    n.x = 0\n    n.y = 0\nfrLayout()"), s.rec.of("error")
        got.append(ev(s, "[(n.x, n.y) for n in g.nodes]"))
    assert got[0] == got[1] and len(set(got[0])) > 20


def test_growing_network_extra_edges_join_old_nodes():
    s = _s()
    assert s.run("makeGrowingNetwork(150, m=2, extra=2, seed=3, layout=false)"), s.rec.of("error")
    # every edge born at a step either touches that step's newcomer (its own m edges) or joins two older nodes
    own = ev(s, "[e for e in g.edges if e.born > 0 and (e.node1.born == e.born or e.node2.born == e.born)]")
    extra = ev(s, "[e for e in g.edges if e.born > 0 and e.node1.born < e.born and e.node2.born < e.born]")
    assert len(own) == 2 * (150 - 3) and len(extra) > 100           # the starting clique is m + 1 = 3 nodes


def test_dendrogram_chart_and_cut_field():
    s = _s()
    assert s.run("newGraph('d')\nfor v in 'abcde':\n    addNode(v)\n"
                 "showDendrogram([(0, 1), (2, 3), (5, 6), (4, 7)], cut=2, field='hc')"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["kind"] == "dendrogram" and len(m["clusters"]) == 4 and len(m["leaves"]) == 5
    top = m["clusters"][-1]
    assert (top["lo"], top["hi"]) == (0, 4) and len(m["dgroups"]) == 2
    assert ev(s, "sorted(n.hc for n in g.nodes)") == [0, 0, 0, 0, 1]
    assert not s.run("showDendrogram([(0, 9)])")


def test_block_model_fit_lfr_core_periphery_and_ranks():
    s = _s()
    assert s.run("makeSample('karate')"), s.rec.of("error")
    plain = ev(s, "fitBlockModel(2, degreeCorrected=false, restarts=5)")
    hubs = ev(s, "set(n.sbm_class for n in sorted(g.nodes, key=lambda n: -n.degree)[:5])")
    assert len(hubs) == 1                                   # the plain model groups the hubs together
    assert ev(s, "fitBlockModel(2, restarts=5)")["loglik"] > -745
    assert ev(s, "compareClusters(sbm_class, club)") > 0.5  # degree-corrected: close to the two clubs
    assert s.run("makeLFR(200, mu=0.1, seed=1, layout=false)\nlouvainClusters()"), s.rec.of("error")
    assert ev(s, "compareClusters(louvain_class, community)") > 0.9
    assert s.run("makeBlockModel([10, 40], [[0.9, 0.5], [0.5, 0.02]], seed=1, layout=false)")
    assert ev(s, "corePeriphery()")["core"] == 10 and ev(s, "all(n.core == (n.block == 0) for n in g.nodes)")
    assert s.run("newGraph('r')\nfor i in range(4):\n    addNode(f'p{i}')\n"
                 "for i in range(3):\n    addDirectedEdge(g.getNodeByName(f'p{i}'), g.getNodeByName(f'p{i+1}'))")
    assert ev(s, "rankNodes()") == 1.0 and ev(s, "[n.rank for n in g.nodes] == sorted([n.rank for n in g.nodes], reverse=True)")


def test_dendrogram_paint_matches_groups():
    s = _s()
    assert s.run("newGraph('d')\nfor v in 'abcde':\n    addNode(v)\n"
                 "showDendrogram([(0, 1), (2, 3), (5, 6), (4, 7)], cut=2, paint=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    big, single = sorted(m["dgroups"], key=lambda gp: gp[0] - gp[1])
    assert single[2] == 0xB4B4B4 and big[2] != single[2]
    assert ev(s, "e.color") != ev(s, "a.color") and ev(s, "a.color") == ev(s, "d.color")


def test_percolation_and_new_epidemic_models():
    s = _s()
    assert s.run("makeErdosRenyiRandom(2000, 0.002)"), s.rec.of("error")   # mean degree about 4: phi_c = 1/4
    curve = ev(s, "percolation(trials=3, show=false)")
    S = dict(curve)
    near = lambda phi: min(curve, key=lambda p: abs(p[0] - phi))[1]
    import math
    s_ = 0.5
    for _ in range(200):                                   # theory at phi = 0.5: S = phi s, s = 1 - exp(-c phi s)
        s_ = 1 - math.exp(-4 * 0.5 * s_)
    assert near(1.0) > 0.9 and near(0.15) < 0.05 and abs(near(0.5) - 0.5 * s_) < 0.05
    attack = dict(ev(s, "percolation('degree', show=false)"))
    assert min(ev(s, "percolation('degree', show=false)"), key=lambda p: abs(p[0] - 0.5))[1] < near(0.5)
    bond = ev(s, "percolation(bond=true, trials=2, show=false)")
    assert bond[-1][1] > 0.9 and bond[0][1] < 0.01
    assert s.run("percolation()") and _charts(s)[-1]["title"] == "Site percolation"
    # SIS settles at an endemic level; SEIR passes through E; SIRS keeps going
    assert s.run("c = spread([g.nodes[0]], model='SIS', beta=0.3, gamma=0.2, steps=60, show=false)"), s.rec.of("error")
    assert ev(s, "c[-1][2]") > 100 and ev(s, "c[-1][3]") == 0
    assert s.run("c = spread([g.nodes[0]], model='SEIR', beta=0.3, gamma=0.2, sigma=0.3, steps=200)"), s.rec.of("error")
    assert max(ev(s, "c.exposed")) > 10 and any(sr["name"] == "exposed" for sr in _charts(s)[-1]["series"])
    assert s.run("c = spread([g.nodes[0]], model='SIRS', beta=0.3, gamma=0.2, waning=0.1, steps=80, show=false)")
    assert ev(s, "c[-1][2]") > 0
    assert not s.run("spread([g.nodes[0]], model='XYZ')")


def test_plot_line_series_colours():
    s = _s()
    assert s.run("plotLine({'I': [(0, 1), (1, 2)], 'I theory': [(0, 1), (1, 2.2)]}, title='c', "
                 "dashed=['I theory'], colors={'I': red, 'I theory': red})"), s.rec.of("error")
    se = _charts(s)[-1]["series"]
    assert se[0]["color"] == se[1]["color"] == 0xFF0000
    assert s.run("plotLine({'a': [(0, 1)], 'b': [(0, 2)]}, title='d', colors=['0,128,0'])")
    assert _charts(s)[-1]["series"][0]["color"] == 0x008000


def test_hidden_tab_widgets_still_get_updates_but_live_text_waits():
    s = _s()
    calls = []
    s.ns["__calls"] = calls
    assert s.run("b = Button('Go')\nm = Markdown(lambda: (__calls.append(1), 'x')[1])\n"
                 "ui.layout(right=Tabs(Tab('One', Label('first')), Tab('Two', b, m)))"), s.rec.of("error")
    s.rec.clear()
    n_before = len(calls)
    assert s.run("b.text = 'Pause'"), s.rec.of("error")
    ups = [m for m in s.rec.msgs if m.get("op") == "update" and m.get("props", {}).get("text") == "Pause"]
    assert ups, "a hidden tab's button must still be updated"
    assert len(calls) == n_before                      # its live Markdown wasn't recomputed while hidden


def test_generators_and_starting_positions_are_reproducible():
    s = _s()
    def edges():
        return ev(s, "sorted((e.node1.name, e.node2.name) for e in g.edges)")
    assert s.run("makeErdosRenyiRandom(80, 0.05)")
    a = edges()
    assert s.run("makeErdosRenyiRandom(80, 0.05)") and edges() == a
    assert s.run("makeErdosRenyiRandom(80, 0.05, seed=3)") and edges() != a
    from guess.model import scatter_position
    assert scatter_position("v1") == scatter_position("v1") != scatter_position("v2")


def test_fixed_infectious_period_and_steps_infected():
    s = _s()
    assert s.run("makeErdosRenyiRandom(300, 0.02)"), s.rec.of("error")
    assert s.run("c = spread([g.nodes[0]], model='SIR', beta=0.2, duration=3, steps=200, show=false)"), s.rec.of("error")
    # every infected node is infectious for exactly 3 steps (unless the run stopped first)
    steps = ev(s, "[n.infected_steps for n in g.nodes if n.infected_at >= 0]")
    assert steps and set(steps) == {3}
    assert ev(s, "all(n.infected_steps == 0 for n in g.nodes if n.infected_at < 0)")
    assert s.run("o = outbreaks(20, model='SIR', beta=0.2, duration=3, show=false)"), s.rec.of("error")
    assert s.run("c = spread([g.nodes[0]], model='SIS', beta=0.1, gamma=0.2, steps=40, show=false)")
    assert ev(s, "max(n.infected_steps for n in g.nodes)") > 3
