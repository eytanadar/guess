"""Importers, generators, structural commands."""
import pytest

from guess import Session
from tests.test_gython import Recorder, ev, s  # noqa: F401

PAJEK = """*Vertices 3
1 "Alpha one" 0.1 0.2 0.5 box ic Red
2 "Beta" 0.3 0.4 0.5
3 Gamma
*Arcs
1 2 2.5 c Blue
*Edges
2 3
"""

GRAPHML = """<?xml version="1.0"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="kind" attr.type="string"><default>none</default></key>
  <key id="d1" for="edge" attr.name="w2" attr.type="double"/>
  <graph edgedefault="directed">
    <node id="a"><data key="d0">x</data></node>
    <node id="b"/>
    <edge source="a" target="b"><data key="d1">3.5</data></edge>
    <edge source="b" target="a" directed="false"/>
  </graph>
</graphml>
"""

DL = """dl n=3 format=edgelist1
labels:
ann,bo,cy
data:
1 2 4
2 3
"""


def session_with(tmp_path, name, text, cmd):
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    (tmp_path / name).write_text(text)
    assert s.run(f"{cmd}({str(tmp_path / name)!r})"), rec.of("error")
    return s


def test_pajek(tmp_path):
    s = session_with(tmp_path, "t.net", PAJEK, "makeFromPajek")
    assert ev(s, "pajek1.label") == "Alpha one"
    assert ev(s, "pajek1.style") == 1 and ev(s, "pajek1.color") == "Red"
    assert ev(s, "pajek1.x") == pytest.approx(100)
    e = ev(s, "pajek1->pajek2")
    assert e.weight == 2.5 and e.color == "Blue"
    assert repr(ev(s, "pajek2<->pajek3")) == "pajek2-pajek3"


def test_graphml_roundtrip(tmp_path):
    s = session_with(tmp_path, "t.graphml", GRAPHML, "makeFromGML")
    assert ev(s, "a.kind") == "x" and ev(s, "b.kind") == "none"
    assert ev(s, "(a->b).w2") == 3.5
    assert repr(ev(s, "a<->b")) == "b-a"
    from guess import formats
    text = formats.write_graphml(s.graph)
    s2 = session_with(tmp_path, "u.graphml", text, "makeFromGML")
    assert ev(s2, "(a->b).w2") == 3.5 and ev(s2, "a.kind") == "x"


def test_dl(tmp_path):
    s = session_with(tmp_path, "t.dl", DL, "makeFromDL")
    assert ev(s, "(ann->bo).weight") == 4
    assert repr(ev(s, "bo->cy")) == "bo->cy"


def test_remove_and_add_back(tmp_path):
    s = session_with(tmp_path, "t.dl", DL, "makeFromDL")
    s.run("removed = remove(bo)")
    # as in the original, the name still refers to the removed node
    assert s.ns["bo"]._name == "bo" and "bo" not in s.graph._nodes and len(s.graph.edges) == 0
    assert len(ev(s, "g.deleted")) == 3
    s.run("add(g.deleted)")
    assert repr(ev(s, "bo->cy")) == "bo->cy" and len(s.graph.edges) == 2
    s.run("removeComplete(cy)")
    assert len(ev(s, "g.deleted")) == 0


def test_generators_and_structure():
    pytest.importorskip("networkx")
    s = Session(Recorder())
    s.rec = s.emit
    for cmd, n in [("makeSimpleRandom(20, 30)", 20), ("makeSimpleDirectedRandom(10, 15)", 10),
                   ("makeErdosRenyiRandom(30, 0.1)", 30), ("makeBarabasiAlbertRandom(3, 2, 20)", 23),
                   ("makeKleinbergRandom(5, 2)", 25), ("makeLattice1DRandom(8, true)", 8),
                   ("makeLattice2DRandom(4, false)", 16), ("makeEppsteinRandom(30, 40, 50)", 30)]:
        assert s.run(cmd), (cmd, s.emit.of("error"))
        assert len(s.graph.nodes) == n, cmd
    s.run("makeLattice1DRandom(8, false)")  # a path: everything condenses away
    assert s.run("r = condenseGraph()")
    assert len(s.graph.nodes) == 0
    s.run("makeLattice2DRandom(3, false)")
    assert len(ev(s, "biComponentClusters()")) == 1
    assert len(ev(s, "ninverse((nd0, nd1))")) == 7
    assert ev(s, "distance(nd0, nd0)") == 0
    s.run("c = copyNode(nd0, 'twin', color=red)")
    assert ev(s, "twin.color") == "red" and ev(s, "twin.x") == ev(s, "nd0.x")


def test_gdf_applet_form_with_semicolons():
    """GDF embedded in GUESS applets ends each line with ';' (gdfs/adamic-glance.gdf)."""
    from guess import gdf
    from guess.model import Graph
    text = ("nodedef> name VARCHAR,leaning VARCHAR,style TINYINT,visible BOOLEAN;\n"
            "a,Liberal,2,true;\nb,Conservative,1,false;\n"
            "edgedef>node1 VARCHAR,node2 VARCHAR,directed BOOLEAN,weight DOUBLE;\n"
            "a,b,true,2.5;\n")
    for t in (text, text.replace("\n", "")):          # one row per line, or all on one line
        g = Graph()
        assert gdf.read(g, t) == (2, 1)
        assert g._nodes["a"].leaning == "Liberal" and g._nodes["b"].visible is False
        e = g._edges_list()[0]
        assert e._directed and e.weight == 2.5


def test_manual_shortest_path_methods_return_edges(s):
    """Manual §7.3/§8: (v291.unweightedShortestPath(v376)).color = blue; len(...) is the distance."""
    p = ev(s, "alice.unweightedShortestPath(jane)")
    assert [repr(e) for e in p] == ["alice-jane"]
    assert len(ev(s, "jane.unweightedShortestPath(bob)")) == 1        # jane->bob is directed
    assert len(ev(s, "alice.unweightedShortestPath(al_x)")) == 0      # no path
    assert s.run("alice.unweightedShortestPath(jane).color = red")
    assert len(ev(s, "bob.dijkstraShortestPath(jane)")) >= 1


def test_edge_betweenness_clusters_on_sample(tmp_path):
    from guess import Session
    from tests.test_gython import SAMPLE
    sess = Session(lambda m: None)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})")
    assert sess.run("cl = edgeBetweennessClusters(5)") and len(sess.ns["cl"]) >= 5
