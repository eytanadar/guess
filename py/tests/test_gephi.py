"""Gephi-inspired features: statistics, communities, filters, path tools,
palettes, rankings, GEXF/CSV, ForceAtlas2/Noverlap and label settings."""
import networkx as nx
import numpy as np
import pytest

from guess import Session
from guess import analysis, colors
from guess.layouts import _close_pairs, _Snapshot
from tests.test_gython import SAMPLE, Recorder, ev, s  # noqa: F401  (fixture)
from tests.test_persist import roundtrip


@pytest.fixture
def big():
    rec = Recorder()
    sess = Session(rec)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    sess.rec = rec
    return sess


def _graph_from(sess, G):
    g = sess.graph
    g.clear()
    rng = np.random.default_rng(0)
    for v in G:
        n = g.addNode(f"n{v}")
        n.x, n.y = rng.random(2) * 1000
    for a, b in G.edges:
        g.addEdge(f"n{a}", f"n{b}")
    return [g._nodes[f"n{v}"] for v in G]


def edge(sess, a, b):
    """The (first) edge from node a to node b, by name."""
    return next(e for e in sess.graph._edges_list() if (e._n1._name, e._n2._name) == (a, b))


def _close(mine, ref, nodes, G, tol):
    assert max(abs(mine[n] - ref[v]) for v, n in zip(G, nodes)) <= tol


# ---- statistics -------------------------------------------------------------

def test_centralities_match_networkx(s):
    G = nx.gnm_random_graph(50, 110, seed=4)
    G.add_edge(50, 51)  # a second component
    nodes = _graph_from(s, G)
    g = s.graph
    _close(analysis._closeness(g), nx.closeness_centrality(G), nodes, G, 1e-12)
    _close(analysis._harmonic(g), nx.harmonic_centrality(G), nodes, G, 1e-9)
    _close(analysis._eigenvector(g), nx.eigenvector_centrality(G, max_iter=1000), nodes, G, 1e-4)
    _close(analysis._clustering(g), nx.clustering(G), nodes, G, 1e-12)
    ecc = {}
    for c in nx.connected_components(G):
        ecc.update(nx.eccentricity(G.subgraph(c)))
    _close(analysis._eccentricity(g)[0], ecc, nodes, G, 0)
    pr = analysis._pagerank(g)
    assert abs(sum(pr.values()) - 1) < 1e-9
    hub, auth = analysis._hits(g)
    assert max(abs(hub[n] - auth[n]) for n in nodes) < 1e-6  # undirected: hubs == authorities


def test_lazy_statistic_fields_and_recompute(s):
    assert ev(s, "bob.pagerank") > 0
    assert ev(s, "bob.coreness") == 2 and isinstance(ev(s, "bob.coreness"), int)
    assert ev(s, "al_x.component") == 1 and ev(s, "bob.component") == 0
    assert ev(s, "bob.strength") == 3.0
    assert ev(s, "jane.triangles") == 1
    s.run("addEdge(al_x, bob)")
    assert ev(s, "al_x.component") == 0          # recomputed on read after the change
    assert s.run("recompute(component)")
    assert ev(s, "al_x.component") == 0
    assert s.run("recompute()")
    assert not s.run("recompute(dept)")


def test_bare_statistic_names_compute_on_use(s):
    assert "closeness" not in s.ns
    assert s.run("sizeBy(closeness, 5, 20)"), s.rec.of("error")
    assert ev(s, "(closeness > 0)") and "closeness" in s.graph.node_schema
    assert s.run("colorBy(betweenness, white, red)")   # node field wins over the edge one


def test_graph_level_statistics(big):
    assert ev(big, "diameter()") == 13
    assert 5 < ev(big, "averagePathLength()") < 7
    assert ev(big, "radius()") >= 1
    big.rec.clear()
    assert big.run("graphStats()")
    text = "".join(m["text"] for m in big.rec.of("text"))
    assert "diameter         13" in text and "components       28" in text


def test_louvain_modularity(big):
    big.rec.clear()
    assert big.run("cl = louvainClusters()")
    cl = big.ns["cl"]
    assert len(cl) > 10 and len(cl[0]) >= len(cl[-1])
    assert ev(big, "cl[0][0].louvain_class") == 0
    q = ev(big, "modularity(louvain_class)")
    assert 0.8 < q < 1
    assert ev(big, "len(louvainClusters(resolution=3))") > len(cl)
    assert not big.run("modularity(freq)")


# ---- filters and paths ----------------------------------------------------------

def test_structural_filters(s):
    assert sorted(n._name for n in ev(s, "kCore(2)")) == ["alice", "bob", "jane"]
    assert sorted(n._name for n in ev(s, "egoNetwork(alice, 1)")) == ["alice", "bob", "jane"]
    assert len(ev(s, "giantComponent()")) == 3
    assert len(ev(s, "intraEdges(dept)")) == 1 and len(ev(s, "interEdges(dept)")) == 3
    assert len(ev(s, "mutualEdges()")) == 2
    assert [n._name for n in ev(s, "groupsOfSize(dept, 2)")] == ["bob", "alice", "jane", "al_x"]
    assert s.run("showOnly(kCore(2))")
    assert not ev(s, "al_x.visible") and ev(s, "bob.visible")
    assert all(e.visible for e in ev(s, "g.edges"))
    assert s.run("showOnly(bob-alice)")
    assert not ev(s, "jane.visible") and ev(s, "alice.visible")
    assert s.run("showAll()") and ev(s, "al_x.visible")


def test_shortest_path_heat_map_paint(s):
    p = ev(s, "shortestPath(alice, jane)")
    assert [x._name if hasattr(x, "_name") else repr(x) for x in p] == ["alice", "alice-jane", "jane"]
    # direction is followed: jane -> bob exists, so the path is one hop
    assert len(ev(s, "shortestPath(jane, bob)")) == 3
    assert len(ev(s, "shortestPath(alice, al_x)")) == 0
    assert s.run("shortestPath(alice, jane).color = red")
    assert ev(s, "jane.color") == "red"
    assert s.run("heatMap(bob)")
    assert ev(s, "bob.hops") == 0 and ev(s, "jane.hops") == 1 and ev(s, "al_x.hops") == -1
    assert ev(s, "bob.color") == "215,25,28,255"              # red at the centre
    assert ev(s, "al_x.color") == "#bdbdbd"                   # grey: unreachable
    assert s.run("heatMap(bob, near=red, far=blue, middle=None)") and ev(s, "bob.color") == "255,0,0,255"
    assert s.run("paint(al_x, blue)") and ev(s, "al_x.color") == "blue"
    assert s.run("paint(bob, green, 1)") and ev(s, "jane.color") == "green"


# ---- appearance --------------------------------------------------------------

def test_distinct_palette():
    pal = colors.distinctColors(12)
    assert len(set(pal)) == 12
    rgb = np.array([[int(v) for v in c.split(",")] for c in pal], float)
    d = np.linalg.norm(rgb[:, None] - rgb[None], axis=2) + np.eye(12) * 1e9
    assert d.min() > 25
    assert colors.distinctColors(3) == colors.distinctColors(3)


def test_colorize_uses_distinct_colours(big):
    big.run("colorize(dept)")
    groups = ev(big, "groupBy(dept)")
    biggest = max(groups, key=len)
    assert biggest[0].color == colors.distinctColors(len(groups))[0]
    assert len({grp[0].color for grp in groups}) == len(groups)


def test_size_and_colour_by_value(s):
    assert s.run("sizeBy(freq, 1, 31)")
    assert edge(s, "bob", "jane").width == 31 and edge(s, "jane", "bob").width == 1
    assert edge(s, "bob", "alice").width == pytest.approx(1 + 30 * 8 / 28)
    assert s.run("sizeBy(freq, 1, 31, 'log')")
    mid = edge(s, "bob", "alice").width
    assert 1 + 30 * 8 / 28 < mid < 31   # log spreads the low end
    assert s.run("colorBy(freq, white, black, 'rank')")
    assert edge(s, "jane", "bob").color == "255,255,255,255"
    assert not s.run("sizeBy(dept, 1, 2)")
    assert not s.run("sizeBy(freq, 1, 2, 'cubic')")


def test_label_settings_roundtrip(s):
    s.run("labelOutlines(); hideOverlappingLabels()")
    s.flush()
    assert s.rec.of("overlay")[-1]["labels"] == {"outline": True, "cull": True, "along": False, "placement": "candidates", "screen": False}
    assert roundtrip(s).view.labels == {"outline": True, "cull": True, "along": False, "placement": "candidates", "screen": False}


def test_raise_changed_setting(s):
    assert s.view.raise_changed is True       # on by default
    assert s.run("raiseChanged(false)")
    s.flush()
    assert s.rec.of("overlay")[-1]["raiseChanged"] is False
    assert roundtrip(s).view.raise_changed is False
    assert s.run("undo()")
    assert s.view.raise_changed is True


def test_hover_fields(s):
    assert s.view.hover_fields == {"n": [], "e": []}      # label only by default
    assert s.run("hoverFields(dept)")
    assert s.view.hover_fields["n"] == ["dept"]
    assert s.run('hoverFields(nodes=["degree"], edges=["color"])')
    assert s.view.hover_fields == {"n": ["degree"], "e": ["color"]}
    assert not s.run('hoverFields("dpet")')                   # a clear error, nothing changed
    assert s.view.hover_fields["n"] == ["degree"]
    s.flush()
    assert s.rec.of("overlay")[-1]["hoverFields"] == {"n": ["degree"], "e": ["color"]}
    assert roundtrip(s).view.hover_fields == {"n": ["degree"], "e": ["color"]}
    assert s.run("hoverFields()")
    assert s.view.hover_fields == {"n": [], "e": []}
    assert s.run("undo()")
    assert s.view.hover_fields == {"n": ["degree"], "e": ["color"]}


# ---- formats -----------------------------------------------------------------

def test_gexf_roundtrip(s, tmp_path):
    assert s.run("bob.color = red; bob.x = 12; bob.y = 34; bob.size = 20")
    edge(s, "bob", "alice").weight = 2.5
    f = tmp_path / "t.gexf"
    assert s.run(f"exportGEXF({str(f)!r})")
    assert s.run(f"makeFromGEXF({str(f)!r})")
    assert ev(s, "bob.color") == "255,0,0"
    assert ev(s, "(bob.x, bob.y, bob.width)") == (12, 34, 20)
    assert ev(s, "bob.dept") == "IT" and edge(s, "bob", "alice").weight == 2.5
    assert edge(s, "bob", "jane").freq == 30
    assert ev(s, "len(g.edges)") == 4 and edge(s, "jane", "bob").directed


def test_gexf_from_gephi(s, tmp_path):
    f = tmp_path / "g.gexf"
    f.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<gexf xmlns="http://www.gexf.net/1.2draft" xmlns:viz="http://www.gexf.net/1.2draft/viz" version="1.2">
  <graph defaultedgetype="directed">
    <attributes class="node"><attribute id="0" title="Modularity Class" type="integer"/>
      <attribute id="1" title="color" type="string"/></attributes>
    <nodes>
      <node id="1" label="Myriel"><attvalues><attvalue for="0" value="3"/><attvalue for="1" value="x"/></attvalues>
        <viz:size value="28.6"/><viz:position x="-10.0" y="20.5" z="0"/><viz:color r="245" g="91" b="91" a="0.5"/></node>
      <node id="2" label="Napoleon"/>
    </nodes>
    <edges><edge id="0" source="2" target="1" weight="2.0"/><edge id="1" source="1" target="2" type="undirected"/></edges>
  </graph>
</gexf>""")
    assert s.run(f"makeFromGEXF({str(f)!r})"), s.rec.of("error")
    n = s.graph._nodes["1"]
    assert n.label == "Myriel" and n.Modularity_Class == 3 and n.color_ == "x"
    assert n.color == "245,91,91,128" and n.y == pytest.approx(-20.5 - 14.3) and n.width == pytest.approx(28.6)
    e0, e1 = s.graph._edges_list()
    assert e0._directed and e0.weight == 2.0 and not e1._directed


def test_csv_tables(s, tmp_path):
    (tmp_path / "e.csv").write_text("Source;Target;Type;Weight;kind\na;b;Directed;2;x\nb;c;;3.5;y\n")
    assert s.run(f"makeFromCSV({str(tmp_path / 'e.csv')!r})"), s.rec.of("error")
    assert ev(s, "len(g.edges)") == 2 and edge(s, "a", "b").weight == 2 and edge(s, "a", "b").directed
    assert edge(s, "b", "c").kind == "y" and not edge(s, "b", "c").directed
    (tmp_path / "n.csv").write_text("Id,Label,score,color\na,Alpha,3,red\nz,Zed,1,blue\n")
    assert s.run(f"makeFromCSV({str(tmp_path / 'n.csv')!r})")
    assert ev(s, "(a.label, a.score, a.color, z.label)") == ("Alpha", 3, "red", "Zed")
    (tmp_path / "m.csv").write_text(",a,b,c\na,0,1,0\nb,1,0,2\nc,0,2,0\n")
    assert s.run(f"makeFromCSV({str(tmp_path / 'm.csv')!r})")
    assert ev(s, "[e.weight for e in g.edges]") == [1.0, 2.0]
    (tmp_path / "l.csv").write_text("a,b,c\nb,c\nd\n")
    assert s.run(f"makeFromCSV({str(tmp_path / 'l.csv')!r}, directed=true)")
    assert ev(s, "len(g.edges)") == 3 and ev(s, "len(g.nodes)") == 4 and edge(s, "a", "b").directed


def test_csv_export_roundtrip(big, tmp_path):
    e, n = tmp_path / "e.csv", tmp_path / "n.csv"
    big.run("colorize(dept)")
    color = ev(big, "v1.color")
    assert big.run(f"exportCSV({str(e)!r}); exportCSV({str(n)!r}, 'nodes')")
    assert big.run(f"makeFromCSV({str(e)!r}, {str(n)!r})"), big.rec.of("error")
    assert ev(big, "(len(g.nodes), len(g.edges))") == (402, 725)
    assert ev(big, "v1.color") == color and ev(big, "v1.dept") == "dept0"


# ---- layouts -------------------------------------------------------------------

def _separation(sess, G, blocks):
    lab = {v: i for i, bl in enumerate(blocks) for v in bl}
    X = np.array([(sess.graph._nodes[f"n{v}"].x, sess.graph._nodes[f"n{v}"].y) for v in G])
    L = np.array([lab[v] for v in G])
    D = np.linalg.norm(X[:, None] - X[None], axis=2)
    same = L[:, None] == L[None]
    return D[same].mean() / D[~same].mean()


@pytest.mark.parametrize("opts", ["", "linLog=true", "strongGravity=true, dissuadeHubs=true"])
def test_force_atlas2_separates_communities(s, opts):
    G = nx.stochastic_block_model([40] * 4, [[0.2 if i == j else 0.005 for j in range(4)] for i in range(4)], seed=1)
    _graph_from(s, G)
    assert s.run(f"forceAtlas2Layout({opts})"), s.rec.of("error")
    blocks = [range(40 * i, 40 * i + 40) for i in range(4)]
    assert _separation(s, G, blocks) < 0.4


def test_force_atlas2_keeps_fixed_nodes_and_options(s):
    s.run("bob.fixed = true; bob.x = 7; bob.y = 9")
    assert s.run("forceAtlas2Layout(iterations=50, preventOverlap=true, edgeWeightInfluence=0)")
    assert ev(s, "(bob.x, bob.y)") == (7, 9)
    assert not s.run("forceAtlas2Layout(iterations=-1)")


def test_noverlap_rotate_mirror(s):
    G = nx.gnm_random_graph(200, 300, seed=2)
    _graph_from(s, G)
    for n in s.graph._nodes_list():
        n.x = n.y = 500.0
    assert s.run("noverlapLayout()")
    snap = _Snapshot(s.graph)
    reach = 1.2 * snap.size.max(1) / 2 + 2.4
    assert len(_close_pairs(snap.pos + snap.size / 2, reach)[0]) == 0
    s.run("makeSimpleRandom(3, 0)")
    s.run("nd0.x = 0; nd0.y = 0; nd1.x = 100; nd1.y = 0; nd2.x = 50; nd2.y = 50")
    s.run("rotateLayout(90)")
    assert [round(v) for v in ev(s, "(nd0.x, nd0.y, nd1.x, nd1.y)")] == [75, -25, 75, 75]
    s.run("mirrorLayout(false)")
    assert [round(v) for v in ev(s, "(nd0.y, nd1.y)")] == [75, -25]


def test_select_binds_sel_and_tells_the_display(s):
    assert ev(s, "len(sel)") == 0
    assert s.run("select(dept == 'IT')")
    assert s.rec.of("select")[-1]["nodes"] == [ev(s, "bob")._id, ev(s, "alice")._id]
    assert [n._name for n in ev(s, "sel")] == ["bob", "alice"]
    s.run("select(jane->bob)")            # edges select their endpoints
    assert {n._name for n in ev(s, "sel")} == {"jane", "bob"}
    assert s.set_selection([ev(s, "al_x")._id, 999]) == 1   # from a box/lasso; unknown ids dropped
    assert s.run("sel.color = red") and ev(s, "al_x.color") == "red"
    s.run("select()")
    assert s.rec.of("select")[-1]["nodes"] == [] and ev(s, "len(sel)") == 0


def test_api_reference_is_up_to_date(tmp_path, monkeypatch):
    """docs/API.md must match the docstrings: run py/tools/gen_api_docs.py."""
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("gen_api_docs", root / "py" / "tools" / "gen_api_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT", tmp_path / "API.md")
    mod.main()
    assert (tmp_path / "API.md").read_text() == (root / "docs" / "API.md").read_text(), \
        "docs/API.md is stale: cd py && .venv/bin/python tools/gen_api_docs.py"
