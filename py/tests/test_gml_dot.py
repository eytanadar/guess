"""GML and Graphviz DOT import (and GML export)."""
import networkx as nx

from tests.test_gython import Recorder
from guess import Session


def load(tmp_path, name, text, cmd):
    rec = Recorder()
    s = Session(rec)
    p = tmp_path / name
    p.write_text(text)
    assert s.run(f"{cmd}({str(p)!r})"), rec.of("error")
    s.rec = rec
    return s


def test_gml_from_networkx(tmp_path):
    G = nx.karate_club_graph()
    for n in G:
        G.nodes[n]["score"] = n * 0.5
    text = "\n".join(nx.generate_gml(G))
    s = load(tmp_path, "karate.gml", text, "makeFromGML")
    g = s.graph
    assert len(g.nodes) == 34 and len(g.edges) == 78
    # networkx writes label = the node key; names are those labels ("0".."33")
    n0 = g.getNodeByName("0")
    assert n0.club == "Mr. Hi" and n0.score == 0.0 and g.getNodeByName("3").score == 1.5
    assert {round(e.weight) for e in g.edges} - {1} and not any(e._directed for e in g.edges)


def test_gml_graphics_ids_and_odd_input(tmp_path):
    text = """Creator "yEd" # a comment
    graph [
      directed 1
      node [ id 10 graphics [ x 100. y -20 w 30 h 30 fill "#FF0000" type "rectangle" ] kind "a" ]
      node [ id 11 graphics [ x 0 y 0 ] kind "b" value 2 ]
      node [ id 12 ]
      edge [ source 10 target 11 label "x &amp; y" value 1.5 graphics [ fill "#0000ff" width 3 ] ]
      edge [ source 10 target 11 ]
      edge [ source 11 target 99 ]
    ]"""
    s = load(tmp_path, "y.gml", text, "makeFromGML")
    g = s.graph
    a, b = g.getNodeByName("n10"), g.getNodeByName("n11")            # no labels: n<id>
    assert (a.x, a.y, a.width, a.style) == (100.0, -20.0, 30.0, 1) and a.color.lower() in ("#ff0000", "255,0,0", "red")
    assert a.kind == "a" and b.value == 2
    es = sorted(g.edges, key=lambda e: e.width, reverse=True)
    assert len(es) == 2 and es[0]._directed and es[0].label == "x & y" and es[0].value == 1.5 and es[0].width == 3.0


def test_gml_roundtrip_and_graphml_compat(tmp_path):
    s = load(tmp_path, "y.gml", 'graph [ node [ id 1 label "p" w 2 ] node [ id 2 label "q" w 5 ] edge [ source 1 target 2 weight 4 ] ]', "makeFromGML")
    out = tmp_path / "out.gml"
    assert s.run(f"exportGML({str(out)!r})")
    t = load(tmp_path, "back.gml", out.read_text(), "makeFromGML")
    assert sorted(n._name for n in t.graph.nodes) == ["p", "q"] and t.graph.getNodeByName("q").w == 5
    assert [e.weight for e in t.graph.edges] == [4.0]
    assert nx.parse_gml(out.read_text()).number_of_edges() == 1      # networkx reads what we write
    # GUESS 2006 called GraphML "GML": makeFromGML still opens GraphML
    xml = '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"><graph edgedefault="undirected"><node id="a"/><node id="b"/><edge source="a" target="b"/></graph></graphml>'
    u = load(tmp_path, "old.xml", xml, "makeFromGML")
    assert len(u.graph.nodes) == 2 and len(u.graph.edges) == 1


def test_dot(tmp_path):
    text = r'''/* example */ strict digraph "G" {
      graph [rankdir=LR]; node [shape=box, color="0.000 1.000 1.000"];
      a [pos="72,144", width=1, rank=3];
      a -> b -> c [color=blue, penwidth=2.5, weight=4, kind=link];
      {a; b} -> d   // two edges
      e:p1:ne -> f
      subgraph cluster_left { label="Left"; g [label=<<b>Gee</b>>, fillcolor="#00ff0080", style=filled]; h }
      "multi" + "part" [fixed=1]
      # preprocessor line
    }'''
    s = load(tmp_path, "g.dot", text, "makeFromDOT")
    g = s.graph
    names = sorted(n._name for n in g.nodes)
    assert names == ["a", "b", "c", "d", "e", "f", "g", "h", "multipart"]
    a = g.getNodeByName("a")
    assert (a.x, a.y) == (72.0, -144.0) and a.style == 1 and a.rank == 3 and a.width == 24.0
    assert g.getNodeByName("g").label == "Gee" and g.getNodeByName("g").cluster == "left"
    assert g.getNodeByName("h").cluster == "left" and g.getNodeByName("c").cluster in ("", None)
    assert g.getNodeByName("multipart").dot_fixed == 1
    assert len(g.edges) == 5 and all(e._directed for e in g.edges)
    ab = [e for e in g.edges if e._n1._name == "a" and e._n2._name == "b"][0]
    assert ab.width == 2.5 and ab.weight == 4.0 and ab.kind == "link"


def test_dot_undirected_and_errors(tmp_path):
    s = load(tmp_path, "u.gv", "graph { x -- y -- z; z -- x }", "makeFromDOT")
    assert len(s.graph.edges) == 3 and not any(e._directed for e in s.graph.edges)
    rec = Recorder()
    t = Session(rec)
    p = tmp_path / "bad.dot"
    p.write_text("digraph { a -> }")
    assert not t.run(f"makeFromDOT({str(p)!r})")
