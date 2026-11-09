"""igraph engine: same numbers as the networkx/numpy code, and the commands
only igraph provides."""
import pathlib

import networkx as nx
import pytest

from guess import Session, algorithms, analysis, igr
from tests.test_gython import Recorder, ev

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


@pytest.fixture
def s():
    rec = Recorder()
    sess = Session(rec)
    sess.rec = rec
    yield sess
    igr.ENABLED[0] = True


def run(s, code):
    s.rec.clear()
    assert s.run(code), s.rec.of("error")


def text(s):
    return "".join(m.get("text", "") for m in s.rec.msgs if m.get("type") == "text")


STATS = {
    "betweenness": algorithms._betweenness_nodes,
    "edge betweenness": algorithms._betweenness_edges,
    "clustering": analysis._clustering,
    "triangles": analysis._triangles,
    "coreness": analysis._coreness,
    "component": lambda g: analysis._components(g),
    "strongcomponent": lambda g: analysis._components(g, True),
    "closeness": analysis._closeness,
    "harmonic": analysis._harmonic,
    "eccentricity": analysis._eccentricity,
}


@pytest.mark.parametrize("graph", [
    f"makeFromGDF({str(SAMPLE)!r})",
    "makeSample('karate')\naddEdge(n2, n2)",
    "makeSimpleDirectedRandom(60, 150)",
])
def test_igraph_engine_matches_networkx_numpy(s, graph):
    run(s, graph)
    for name, fn in STATS.items():
        igr.ENABLED[0] = True
        a = fn(s.graph)
        igr.ENABLED[0] = False
        b = fn(s.graph)
        a = a[0] if isinstance(a, tuple) else a
        b = b[0] if isinstance(b, tuple) else b
        for k in set(a) | set(b):
            assert float(a.get(k, 0)) == pytest.approx(float(b.get(k, 0)), abs=1e-9), (name, k)
    igr.ENABLED[0] = True


def test_parallel_edges_share_edge_betweenness(s):
    # the networkx version gave the value to only one of two parallel edges
    run(s, "makeSample('karate')\ne2 = addEdge(n0, n1)")
    vals = ev(s, "[e.betweenness for e in g.edges if {e.node1.name, e.node2.name} == {'n0', 'n1'}]")
    assert len(vals) == 2 and vals[0] == vals[1] > 0


def test_community_commands_write_fields(s):
    run(s, f"makeFromGDF({str(SAMPLE)!r})")
    for cmd, field in [("leidenClusters()", "leiden_class"), ("infomapClusters()", "infomap_class"),
                       ("walktrapClusters()", "walktrap_class"), ("fastGreedyClusters()", "fastgreedy_class"),
                       ("labelPropagationClusters()", "lpa_class"), ("eigenvectorClusters()", "eigen_class"),
                       ("voronoiClusters()", "voronoi_class")]:
        run(s, cmd)
        assert f"communities in {field}" in text(s), cmd
        sizes = ev(s, f"[len({field} == k) for k in range({field}.max + 1)]")
        assert sum(sizes) == 402 and sizes == sorted(sizes, reverse=True), cmd
    # leiden beats a random split and is reproducible with a seed
    q1 = ev(s, "modularity(leiden_class)")
    run(s, "leidenClusters(seed=0)")
    assert ev(s, "modularity(leiden_class)") == pytest.approx(q1) and q1 > 0.8


def test_dendrogram_cuts_and_components(s):
    run(s, f"makeFromGDF({str(SAMPLE)!r})\nwalktrapClusters()\ncutDendrogram(80)")
    assert ev(s, "walktrap_class.max") == 79
    run(s, "cutDendrogram(3)")                            # 28 components: can't go lower
    assert "separate parts" in text(s)
    assert ev(s, "walktrap_class.max") + 1 == len(set(ev(s, "[n.component for n in g.nodes]")))


def test_semi_supervised_label_propagation_keeps_seeds(s):
    run(s, "makeSample('karate')\naddNodeField('side', VARCHAR, None)\nn0.side = 'hi'\nn33.side = 'officer'\n"
           "labelPropagationClusters(side)")
    assert ev(s, "n0.lpa_class") != ev(s, "n33.lpa_class") and ev(s, "lpa_class.max") == 1


def test_small_graph_methods(s):
    run(s, "makeSample('karate')\noptimalClusters()")
    assert "modularity 0.4449: 4 communities" in text(s)            # the known optimum
    run(s, "spinglassClusters()")
    run(s, "cohesiveBlocks()")
    assert ev(s, "cohesion.max") == 4
    run(s, "fluidClusters(2)")
    assert ev(s, "fluid_class.max") == 1


def test_layouts_place_every_node(s):
    run(s, "makeSample('karate')")
    for cmd in ["drlLayout()", "lglLayout()", "umapLayout()", "dhLayout()"]:
        run(s, "for n in g.nodes: n.x = 0; n.y = 0")
        run(s, cmd)
        xs = ev(s, "[(n.x, n.y) for n in g.nodes]")
        assert len(set(xs)) > 30, cmd
        assert all(0 <= x <= 1000 and 0 <= y <= 1000 for x, y in xs), cmd
    run(s, "makeSample('davis')\nbipartiteLayout(bipartite)")
    rows = ev(s, "sorted({round(n.y) for n in g.nodes})")
    assert len(rows) == 2


def test_similarity_prediction_patterns(s):
    run(s, "makeSample('karate')")
    G = nx.karate_club_graph()
    top = ev(s, "similarTo(n0, top=3)")
    jac = {v: len(set(G[0]) & set(G[v])) / len(set(G[0]) | set(G[v])) for v in G if v != 0}
    best = max(jac.values())
    assert ev(s, f"{top[0]._name}.similarity") == pytest.approx(best)
    pairs = ev(s, "predictLinks(5, show=False)")
    aa = sorted(nx.adamic_adar_index(G), key=lambda t: -t[2])[0][2]
    assert len(pairs) == 5 and pairs[0][2] == pytest.approx(aa, abs=1e-3)
    tris = ev(s, "findPattern([('a','b'),('b','c'),('c','a')], limit=1000)")
    assert len(tris) == sum(nx.triangles(G).values()) // 3
    run(s, "import networkx as nx\nsq = findPattern(nx.cycle_graph(4), induced=True, limit=1000)")
    squares = ev(s, "len(sq)")
    assert squares > 0 and all(len(m) == 4 for m in ev(s, "sq"))


def test_cuts_flows_pagerank_dominators(s):
    run(s, "makeSample('karate')")
    G = nx.karate_club_graph()
    cut = ev(s, "minCut(n0, n33)")
    assert len(cut) == nx.edge_connectivity(G, 0, 33)
    assert ev(s, "maxFlow(n0, n33, None)") == pytest.approx(nx.edge_connectivity(G, 0, 33))
    assert ev(s, "len([e for e in g.edges if e.flow > 0])") > 0
    run(s, "personalizedPagerank(n0)")
    assert ev(s, "sortBy(ppr)[-1].name") == "n0"
    run(s, "makeSimpleDirectedRandom(40, 100)")
    D = nx.DiGraph((e._n1._name, e._n2._name) for e in s.graph._edges_list())
    reached = ev(s, "dominatorTree(nd0)")
    idom = nx.immediate_dominators(D, "nd0")
    assert {n._name for n in reached} == set(idom) - {"nd0"}
    for n in reached:
        assert n.idom == idom[n._name]


def test_cliques_matching_knn(s):
    run(s, "makeSample('karate')")
    G = nx.karate_club_graph()
    cl = ev(s, "largestCliques()")
    assert {len(c) for c in cl} == {max(len(c) for c in nx.find_cliques(G))}
    assert len(ev(s, "maxMatching()")) == len(nx.max_weight_matching(G, maxcardinality=True, weight=None))
    knn = nx.average_neighbor_degree(G)
    assert ev(s, "n0.knn") == pytest.approx(knn[0])
    run(s, "makeSample('davis')")
    assert len(ev(s, "maxMatching(bipartite)")) == 14


def test_simplify_and_rewire(s):
    run(s, "makeSample('karate')\nw = (n0 - n1).weight\naddEdge(n0, n1)\naddEdge(n2, n2)\nsimplify()")
    assert len(s.graph._edges) == 78 and ev(s, "(n0 - n1).weight") == ev(s, "w") + 1     # summed
    degrees = sorted(ev(s, "[n.totaldegree for n in g.nodes]"))
    tri = ev(s, "transitivity()")
    run(s, "rewire()")
    assert ev(s, "graphNames()")[0] == "rewired"
    assert sorted(ev(s, "[n.totaldegree for n in g.nodes]")) == degrees
    assert ev(s, "transitivity()") < tri                      # karate is far more clustered than chance


def test_engine_switch_and_messages(s):
    run(s, "makeSample('karate')\nuseIgraph(false)")
    assert "networkx/numpy" in text(s)
    assert not s.run("leidenClusters()")
    assert "useIgraph(true)" in s.rec.of("error")[-1]["text"]
    run(s, "print(betweenness.max)")                          # the fallback still works
    run(s, "useIgraph()")
    assert "engine: igraph" in text(s)
