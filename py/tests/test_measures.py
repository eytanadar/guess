"""measures.py: Katz, prestige, bridging, weighted clustering, cliques, MDS,
geographic vectors, k-brace, field tools, generators and link prediction."""
import math

import networkx as nx
import pytest

from guess import Session
from tests.test_gython import Recorder, ev


@pytest.fixture
def s():
    rec = Recorder()
    sess = Session(rec)
    sess.rec = rec
    return sess


def run(s, code):
    """Run code; returns what it printed."""
    s.rec.clear()
    assert s.run(code), s.rec.of("error")
    return printed(s)


def fails(s, code):
    s.rec.clear()
    assert not s.run(code)
    return " ".join(m.get("summary") or m.get("text", "") for m in s.rec.of("error"))


def printed(s):
    out = []
    for m in s.rec.of("out"):
        out.extend(x if isinstance(x, str) else x.get("t", "") for x in m["segs"])
    for m in s.rec.of("text"):
        out.append(m["text"])
    return "".join(out)


def karate(s):
    run(s, "makeSample('karate')")
    return nx.karate_club_graph()


def directed(s):
    """a -> b -> c, a -> c, d -> c, e isolated."""
    run(s, "for k in 'abcde': addNode(k)\n"
           "addDirectedEdge(a, b)\naddDirectedEdge(b, c)\naddDirectedEdge(a, c)\naddDirectedEdge(d, c)")


# ---- Katz and prestige ---------------------------------------------------------

def test_katz_matches_networkx(s):
    G = karate(s)
    want = nx.katz_centrality(G, alpha=0.1, beta=1.0, max_iter=5000, tol=1e-12)
    for i in (0, 5, 33):
        assert ev(s, f"n{i}.katz") == pytest.approx(want[i], rel=1e-6)


def test_katz_lowers_alpha_when_it_would_diverge(s):
    run(s, "makeSample('lesmis')")
    vals = ev(s, "[n.katz for n in g.nodes]")
    assert all(math.isfinite(v) and v > 0 for v in vals)


def test_prestige_on_a_directed_graph(s):
    directed(s)
    # c is reached by a, b, d (3 of 4 others); a by nobody
    assert ev(s, "c.domain_prestige") == pytest.approx(3 / 4)
    assert ev(s, "a.domain_prestige") == 0.0 and ev(s, "e.domain_prestige") == 0.0
    # Lin: (|I|/(n-1)) / mean distance; distances to c: a 1, b 1, d 1
    assert ev(s, "c.proximity_prestige") == pytest.approx(0.75 / 1.0)
    # b: reached by a only (distance 1)
    assert ev(s, "b.proximity_prestige") == pytest.approx(0.25)
    # rank prestige: c is pointed at by more, and more prestigious, nodes
    assert ev(s, "c.rank_prestige") == 1.0
    assert ev(s, "a.rank_prestige") == 0.0
    assert 0 < ev(s, "b.rank_prestige") < 1


def test_prestige_recomputes_after_a_change(s):
    directed(s)
    assert ev(s, "c.domain_prestige") == pytest.approx(0.75)
    run(s, "addDirectedEdge(e, c)")
    assert ev(s, "c.domain_prestige") == pytest.approx(1.0)


# ---- bridging and weighted clustering ----------------------------------------------

def test_bridging_coefficient_and_centrality(s):
    G = karate(s)
    deg = dict(G.degree())
    bc = {v: (1 / deg[v]) / sum(1 / deg[u] for u in G[v]) for v in G}
    btw = nx.betweenness_centrality(G, normalized=False)
    for i in (0, 2, 31):
        assert ev(s, f"n{i}.bridging_coef") == pytest.approx(bc[i])
        assert ev(s, f"n{i}.bridging") == pytest.approx(bc[i] * btw[i])


def test_weighted_bridging_uses_inverse_weights(s):
    G = karate(s)
    said = run(s, "weightedBridging()")
    H = nx.Graph()
    for a, b, d in G.edges(data=True):
        H.add_edge(a, b, dist=1 / d["weight"])
    btw = nx.betweenness_centrality(H, weight="dist", normalized=False)
    assert ev(s, "n0.wbetweenness") == pytest.approx(btw[0])
    assert ev(s, "n0.wbridging") == pytest.approx(btw[0] * ev(s, "n0.bridging_coef"))
    assert "highest weighted bridging" in said
    run(s, "undo()")
    assert "wbridging" not in s.graph.node_schema


def test_weighted_clustering_matches_networkx(s):
    G = karate(s)
    want = nx.clustering(G, weight="weight")
    for i in (0, 1, 8):
        assert ev(s, f"n{i}.wclustering") == pytest.approx(want[i])


# ---- cliques, MDS ----------------------------------------------------------------

def test_cliques_are_maximal_and_largest_first(s):
    G = karate(s)
    got = ev(s, "cliques(3)")
    want = [c for c in nx.find_cliques(G) if len(c) >= 3]
    assert len(got) == len(want)
    sizes = [len(c) for c in got]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] == 5
    assert ev(s, "len(cliques(5))") == 2
    assert ev(s, "len(cliques(3, limit=4))") == 4


def test_mds_recovers_a_path(s):
    run(s, "for k in range(6): addNode('p%d' % k)\nfor k in range(5): addEdge('p%d' % k, 'p%d' % (k + 1))")
    said = run(s, "mds(2)")
    xs = ev(s, "[n.mds1 for n in sortBy(g.nodes, name)]")
    gaps = [abs(b - a) for a, b in zip(xs, xs[1:])]
    assert gaps == pytest.approx([1.0] * 5, abs=1e-6)          # a path is one-dimensional
    assert ev(s, "max(abs(n.mds2) for n in g.nodes)") == pytest.approx(0, abs=1e-6)
    assert "100%" in said
    assert "dims between 1 and 10" in fails(s, "mds(0)")


def test_mds_with_a_disconnected_graph_and_weights(s):
    karate(s)
    run(s, "addNode('lonely')\nmds(3, weight=weight, name='m')")
    assert {"m1", "m2", "m3"} <= set(s.graph.node_schema)
    assert all(math.isfinite(v) for v in ev(s, "[n.m3 for n in g.nodes]"))


# ---- geography -----------------------------------------------------------------

def test_geo_vectors(s):
    run(s, "addNodeField('lat', DOUBLE, 0)\naddNodeField('lon', DOUBLE, 0)\n"
           "addNode('o', lat=0, lon=0)\naddNode('n', lat=1, lon=0)\naddNode('e', lat=0, lon=1)\n"
           "addEdge(o, n)\naddEdge(o, e)")
    out = ev(s, "geoVectors()")
    assert ev(s, "[round(x.bearing) for x in g.edges]") == [0, 90]
    assert out["edges"] == 2 and out["mean_km"] == pytest.approx(111.19, abs=0.1)
    assert out["sd_km"] == pytest.approx(0, abs=0.1)
    assert out["resultant_km"] == pytest.approx(math.hypot(111.19, 111.19), rel=1e-3)
    assert out["resultant_bearing"] == pytest.approx(45, abs=0.1)
    one = ev(s, "geoVectors([g.edges[0]])")
    assert one["edges"] == 1 and one["resultant_bearing"] == pytest.approx(0, abs=1e-6)


def test_geo_vectors_needs_coordinates(s):
    karate(s)
    assert "latitude field" in fails(s, "geoVectors()")


# ---- k-brace -------------------------------------------------------------------

def test_kbrace_equals_the_truss(s):
    G = karate(s)
    for k in (1, 2, 3):
        got = ev(s, f"sorted((min(int(e.node1.name[1:]), int(e.node2.name[1:])), max(int(e.node1.name[1:]), int(e.node2.name[1:]))) for e in kBrace({k}))")
        want = sorted((min(a, b), max(a, b)) for a, b in nx.k_truss(G, k + 2).edges())
        assert got == want
    assert ev(s, "len(kBrace(0))") == 78
    run(s, "showOnly(kBrace(2))")
    assert ev(s, "len([e for e in g.edges if e.visible])") == nx.k_truss(G, 4).number_of_edges()


# ---- field tools ---------------------------------------------------------------

def test_cast_field_converts_and_undoes(s):
    run(s, "addNode('a')\naddNode('b')\naddNode('c')\naddNodeField('score', VARCHAR, None)\n"
           "a.score = '12'\nb.score = '3.7'\nc.score = 'many'")
    said = run(s, "castField(score, INTEGER)")
    assert s.graph.node_schema["score"].type == "INTEGER"
    assert ev(s, "(a.score, b.score, c.score)") == (12, 3, None)
    assert "1 value couldn't be converted" in said
    assert ev(s, "len(score > 5)") == 1
    run(s, "undo()")
    assert s.graph.node_schema["score"].type == "VARCHAR"
    assert ev(s, "(a.score, b.score, c.score)") == ("12", "3.7", "many")
    run(s, "redo()")
    assert ev(s, "a.score") == 12
    run(s, "castField(score, DOUBLE)\ncastField('score', 'VARCHAR')")
    assert ev(s, "a.score") == "12.0"
    run(s, "addNodeField('flag', VARCHAR, None)\na.flag = 'yes'\nb.flag = 'no'\ncastField(flag, BOOLEAN)")
    assert ev(s, "(a.flag, b.flag)") == (True, False)
    assert "built in" in fails(s, "castField(degree, DOUBLE)")
    assert "needs a type" in fails(s, "castField(score, 'blob')")


def test_read_names(s, tmp_path):
    karate(s)
    f = tmp_path / "keep.txt"
    f.write_text("n0\nn1, n2;n3\tn4\nn5 n6\nnobody\n")
    said = run(s, f"got = readNames({str(f)!r})")
    assert sorted(n.name for n in s.ns["got"]) == [f"n{i}" for i in range(7)]
    assert "1 listed name matched no node" in said
    run(s, f"showOnly(readNames({str(f)!r}))")
    assert ev(s, "len([n for n in g.nodes if n.visible])") == 7
    f2 = tmp_path / "clubs.txt"
    f2.write_text("Officer\n")
    assert ev(s, f"len(readNames({str(f2)!r}, club))") == 17
    assert "can't read" in fails(s, "readNames('/nope/none.txt')")


def test_copy_colors_from_another_graph(s):
    karate(s)
    run(s, "n0.color = red\nn1.color = blue\nsubgraph([n0, n1, n2], 'part')")
    run(s, "n0.color = green\nn1.color = green\nn2.color = green")
    run(s, "use('main')\nn0.color = gray\nn1.color = gray\nuse('part')")
    said = run(s, "copyColors('main')")
    assert ev(s, "(n0.color, n1.color)") == ("128,128,128", "128,128,128")
    assert "coloured 3 of 3" in said
    run(s, "undo()")
    assert ev(s, "n0.color") != "128,128,128"
    assert "no graph 'nope'" in fails(s, "copyColors('nope')")
    assert "graph you're in" in fails(s, "copyColors('part')")


# ---- generators ----------------------------------------------------------------

def test_generators(s):
    run(s, "makeWattsStrogatz(30, 4, 0)")
    assert len(s.graph._nodes) == 30 and len(s.graph._edges) == 60
    assert ev(s, "set(n.degree for n in g.nodes)") == {4}
    run(s, "makeBarabasiAlbertAging(60, 2, aging=1.5, seed=1)")
    assert len(s.graph._nodes) == 60 and len(s.graph._edges) == 3 + 2 * 57
    run(s, "makeBarabasiAlbertAging(60, 2, aging=0, seed=1)")
    assert len(s.graph._edges) == 3 + 2 * 57
    run(s, "makeGeometricRandom(50, 0.3, seed=2)")
    assert len(s.graph._nodes) == 50
    assert all(50 <= x <= 950 for x in ev(s, "[n.x for n in g.nodes]"))
    run(s, "makePowerlawCluster(50, 2, 0.5, seed=3)")
    assert len(s.graph._nodes) == 50 and ev(s, "averageClustering()") > 0
    assert "smaller than n" in fails(s, "makeWattsStrogatz(5, 5, 0.1)")
    assert "between 0 and 1" in fails(s, "makePowerlawCluster(10, 2, 2)")


# ---- link prediction -----------------------------------------------------------

def test_predict_links_can_add_them(s):
    karate(s)
    pairs = ev(s, "predictLinks(5, show=false)")
    run(s, "predictLinks(5, add=true, show=false)")
    assert len(s.graph._edges) == 78 + 5
    added = ev(s, "[(e.node1.name, e.node2.name) for e in g.edges if e.predicted == 'adamic_adar']")
    assert sorted(map(sorted, added)) == sorted(sorted((a.name, b.name)) for a, b, _ in pairs)
    run(s, "undo()")
    assert len(s.graph._edges) == 78


def test_evaluate_links(s):
    karate(s)
    r = ev(s, "evaluateLinks(hide=0.2, seed=1)")
    assert 0 <= r["precision"] <= 1 and 0.5 < r["auc"] <= 1     # better than chance on karate
    assert len(s.graph._edges) == 78                           # untouched
    allr = ev(s, "evaluateLinks('all', show=false)")
    assert set(allr) == {"adamic_adar", "jaccard", "common", "resource"}
    assert "between 0 and 1" in fails(s, "evaluateLinks(hide=2)")
    assert "method should be" in fails(s, "evaluateLinks('magic')")
