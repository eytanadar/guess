"""networkx bridge, sample graphs, structural commands, DOT writer."""
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
    s.rec.clear()
    assert s.run(code), s.rec.of("error")


def test_make_sample_and_to_networkx(s):
    run(s, "makeSample('karate')")
    assert len(s.graph._nodes) == 34 and len(s.graph._edges) == 78
    assert ev(s, "n0.club") == "Mr. Hi" and ev(s, "n0.label") == "n0" and ev(s, "n0.nxkey") == "0"
    G = ev(s, "toNetworkX()")
    assert isinstance(G, nx.Graph) and not G.is_directed() and G.number_of_edges() == 78
    assert G.nodes["n0"]["club"] == "Mr. Hi" and len(G.nodes["n0"]["pos"]) == 2
    assert "name" not in G.nodes["n0"] and "totaldegree" not in G.nodes["n0"]
    with pytest.raises(AssertionError):
        run(s, "makeSample('nope')")


def test_set_field_from_dicts_and_communities(s):
    run(s, "makeSample('karate')")
    run(s, "import networkx as nx\nG = toNetworkX()\n"
           "setField(nx.degree_centrality(G), 'dc')\n"
           "setField(nx.community.label_propagation_communities(G), 'lpa')\n"
           "setField(nx.edge_betweenness_centrality(G), 'eb')")
    assert ev(s, "type(n0.dc).__name__") == "float" and ev(s, "sortBy(dc)[-1].name") in ("n33", "n0")
    sizes = ev(s, "[len(lpa == k) for k in range(lpa.max + 1)]")
    assert sizes == sorted(sizes, reverse=True)          # 0 = largest community
    assert ev(s, "len([e for e in g.edges if e.eb > 0])") == 78
    run(s, "setField({n0: 'a', 'n1': 'b'}, 'tag')")
    assert ev(s, "(n0.tag, n1.tag, n2.tag)") == ("a", "b", None)
    with pytest.raises(AssertionError):
        run(s, "setField({n0: 1}, 'totaldegree')")


def test_from_networkx_keeps_attributes_direction_and_tabs(s):
    D = nx.DiGraph()
    D.add_node("a", kind="x", pos=(1.0, 2.0))
    D.add_node("b", kind="y", pos=(3.0, 4.0))
    D.add_edge("a", "b", weight=2.5, rel="cites")
    s.ns["D"] = D
    run(s, "fromNetworkX(D, 'cites')")
    assert ev(s, "graphNames()")[0] == "cites"
    assert ev(s, "(a.kind, a.x, a.y, b.label)") == ("x", 1.0, 2.0, "b")
    assert ev(s, "[(e.weight, e.rel, e.directed) for e in g.edges]") == [(2.5, "cites", True)]
    # and back: a mixed graph becomes directed with undirected edges both ways
    run(s, "cc = addNode('c')\naddEdge(a, cc)")
    G = ev(s, "toNetworkX()")
    assert G.is_directed() and G.has_edge("a", "c") and G.has_edge("c", "a") and G.graph.get("mixed")


def test_bridges_cut_nodes_spanning_tree(s):
    run(s, "makeSample('karate')")
    assert [e.node2.name for e in ev(s, "bridges()")] == ["n11"]
    assert sorted(n.name for n in ev(s, "cutNodes()")) == ["n0"]
    assert len(ev(s, "spanningTree()")) == 33 and len(ev(s, "spanningTree(maximum=True)")) == 33
    # parallel edges are never bridges
    run(s, "addEdge(n0, n11)")
    assert len(ev(s, "bridges()")) == 0


def test_directed_structure(s):
    run(s, "makeSimpleDirectedRandom(40, 90)")
    fb = ev(s, "feedbackEdges()")
    run(s, "remove(feedbackEdges())")
    assert ev(s, "len(feedbackEdges())") == 0 and len(fb) > 0
    red = ev(s, "transitiveReduction()")
    assert all(e.redundant for e in red) and ev(s, "len(redundant == true)") == len(red)
    G = nx.DiGraph([(e._n1, e._n2) for e in s.graph._edges_list()])
    G.add_nodes_from(s.graph._nodes_list())
    n = s.graph._nodes_list()[0]
    assert set(ev(s, f"descendants({n._name})")) == nx.descendants(G, n)
    assert set(ev(s, f"ancestors({n._name})")) == nx.ancestors(G, n)
    gen = ev(s, "dict((m.name, m.generation) for m in g.nodes)")
    for a, b in G.edges:
        assert gen[a._name] < gen[b._name]
    # a cycle makes transitiveReduction refuse
    run(s, "makeSimpleDirectedRandom(3, 0)\naddDirectedEdge(nd0, nd1)\naddDirectedEdge(nd1, nd2)\naddDirectedEdge(nd2, nd0)")
    assert not s.run("transitiveReduction()")
    assert ev(s, "generation.max") == 0          # one strongly connected group


def test_mixing_and_summaries(s):
    run(s, "makeSample('karate')")
    assert ev(s, "assortativity()") == pytest.approx(nx.degree_assortativity_coefficient(nx.karate_club_graph()))
    assert ev(s, "assortativity(club)") > 0.5          # the two factions mostly link inside
    m = ev(s, "mixingMatrix(club, False)")
    assert m["Mr. Hi"]["Officer"] == m["Officer"]["Mr. Hi"] and sum(m["Mr. Hi"].values()) > 0
    assert ev(s, "transitivity()") == pytest.approx(nx.transitivity(nx.karate_club_graph()))
    census = ev(s, "triadCensus(False)")
    assert sum(census.values()) == math.comb(34, 3) and census["300"] == 45      # 45 triangles
    assert not s.run("reciprocity()")                    # no directed edges
    run(s, "graphStats()")
    text = " ".join(m.get("text", "") for m in s.rec.msgs)
    assert "transitivity" in text and "degree assort." in text


def test_structural_holes_fields(s):
    run(s, "makeSample('kite')")
    G = nx.krackhardt_kite_graph()
    c = nx.constraint(G)
    assert ev(s, "n7.constraint") == pytest.approx(c[7])
    assert ev(s, "sortBy(effsize)[-1].name") == "n" + str(max(nx.effective_size(G).items(), key=lambda kv: kv[1])[0])


def test_compare_clusters(s):
    run(s, "makeSample('karate')")
    assert ev(s, "compareClusters(club, club)") == pytest.approx(1.0)
    assert ev(s, "compareClusters(club, club, 'ari')") == pytest.approx(1.0)
    assert ev(s, "compareClusters(club, club, 'vi')") == pytest.approx(0.0)
    run(s, "louvainClusters()")
    nmi = ev(s, "compareClusters(louvain_class, club)")
    ari = ev(s, "compareClusters(louvain_class, club, 'ari')")
    assert 0.3 < nmi < 1 and 0 < ari < 1
    with pytest.raises(AssertionError):
        run(s, "compareClusters(club, club, 'nope')")


def test_export_dot_round_trip(s, tmp_path):
    run(s, "makeSample('karate')\nlouvainClusters()\nn0.fixed = true\nn3.visible = false\n"
           "addNodeField('pin', DOUBLE, 0)\nn1.pin = 2.5\n(n0 - n1).weight = 1.5")
    out = tmp_path / "k.dot"
    run(s, f"exportDOT({str(out)!r}, clusters='louvain_class')")
    text = out.read_text()
    assert text.startswith("graph {") and "subgraph \"cluster_0\"" in text and "guess_pin" in text
    rec = Recorder()
    t = Session(rec)
    t.rec = rec
    assert t.run(f"makeFromDOT({str(out)!r})")
    assert len(t.graph._nodes) == 34 and len(t.graph._edges) == 78
    assert ev(t, "(n0.fixed, n3.visible, n1.pin, n0.club)") == (True, False, 2.5, "Mr. Hi")
    assert ev(t, "(n0 - n1).weight") == 1.5
    assert ev(t, "(n0.x, n0.y)") == pytest.approx(ev(s, "(n0.x, n0.y)"), abs=1e-3)
    assert ev(t, "n0.cluster") == ev(s, "n0.louvain_class")


def test_loading_a_graph_drops_the_old_fields_and_undo_brings_them_back(s, tmp_path):
    run(s, "makeSample('karate')\nlouvainClusters()\nprint(pagerank.max)")
    old = list(s.graph.node_schema)
    assert {"club", "louvain_class", "pagerank"} <= set(old)
    run(s, "makeSample('florentine')")
    extra = [k for k, f in s.graph.node_schema.items() if not f.builtin]
    assert extra == ["pagerank"] and "club" not in s.ns and "louvain_class" not in s.ns
    # a computed field in use is computed again for the new graph, not left stale
    assert ev(s, "sum(n.pagerank for n in g.nodes)") == pytest.approx(1.0, rel=1e-6)
    assert ev(s, "sortBy(pagerank)[-1].name") == "Medici"
    run(s, "graphStats()")
    assert "modularity" not in " ".join(m.get("text", "") for m in s.rec.msgs)
    run(s, "undo()")
    assert list(s.graph.node_schema) == old and ev(s, "n0.club") == "Mr. Hi"
    # tabs: a new graph starts with no fields of its own; switching back restores them
    run(s, "newGraph('empty')")
    assert [k for k, f in s.graph.node_schema.items() if not f.builtin] == []
    run(s, "use('main')")
    assert "club" in s.graph.node_schema


def test_blockmodel_finds_structural_equivalence():
    from tests.test_gython import Recorder
    from guess import Session
    rec = Recorder()
    s = Session(rec)
    # two "teachers" both tied to the same four "students", who aren't tied to each other:
    # the teachers are equivalent (same ties) though not tied to each other
    for t in ("t1", "t2"):
        for st in ("s1", "s2", "s3", "s4"):
            s.run(f"addEdge(addNode({t!r}), addNode({st!r}))")
    rec.clear()
    assert s.run("__r = blockmodel(2)"), rec.of("error")
    groups = sorted(sorted(n.name for n in p) for p in s.ns["__r"])
    assert groups == [["s1", "s2", "s3", "s4"], ["t1", "t2"]]
    assert s.graph.getNodeByName("s1").position == 0          # largest position first
    printed = "".join(m.get("text", "") for m in rec.msgs)
    assert "1.00" in printed and "0.00" in printed           # students -> teachers dense, within empty
    rec.clear()
    assert not s.run("blockmodel(99)")
    assert "1 <= k" in rec.of("error")[0]["text"]
