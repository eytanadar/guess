"""The 2006 manual's examples (docs/MANUAL_COMPARISON.md), compatibility layer."""
import pytest

from guess import Session, analysis
from tests.test_gython import SAMPLE, Recorder, ev, s  # noqa: F401  (fixture)

RANGES = """nodedef> name, range VARCHAR(32)
v0,"1-2,6-9"
v1,"1-3,8-15"
v2,"1-1"
v3,"5-12"
v4,"20-20"
edgedef> node1,node2,directed
v0,v1,true
v3,v4,true
"""


@pytest.fixture
def big():
    rec = Recorder()
    sess = Session(rec)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})")
    sess.rec = rec
    return sess


def names(seq):
    return sorted(x._name for x in seq)


def test_graph_methods_and_aliases(big):
    for code in ("g.gemLayout()", "g.circleLayout()", "g.radialLayout(v5)", "g.colorize(Node.betweenness, red, blue)",
                 "random()", "random(800, 600)", "biComponentCluster()", "readjustEdges()", "setSynchronous(true)",
                 "g.circleLayout(freq, v5)", "infowindow()", "InfoWindow.details('v1')"):
        assert big.run(code), (code, big.rec.of("error"))
    assert 0 <= ev(big, "random.random()") < 1                  # still Python's random module
    assert ev(big, "random.choice([7])") == 7
    assert big.run("import random\nk1 = random.randint(1, 1)") and big.ns["k1"] == 1   # rebinding is allowed


def test_types_morpher_and_fields(big):
    assert big.run("addNodeField('shortest', Types.INTEGER, Integer(0))")
    assert big.graph.node_schema["shortest"].type == "INTEGER"
    assert big.run("Morpher.setNodeDisappearBy(.2)") and big.morph_timing["nodeDisappearBy"] == 0.2
    assert 0 < ev(big, "v1.degrank") < 1
    assert abs(sum(ev(big, "[n.degrank for n in g.nodes]")) - 1) < 1e-9
    assert ev(big, "v1.hits") == pytest.approx(ev(big, "v1.authority"))
    assert ev(big, "v128.rwbetweenness") > ev(big, "v1.rwbetweenness") > 0


def test_find_nodes_edges_and_deleted_state(big):
    x = ev(big, "(v1, v1?v19)")
    assert names(ev(big, "findNodes((v1, v1?v19))")) == ["v1"] and len(ev(big, "findEdges((v1, v1?v19))")) == 1
    assert x is not None
    big.run("remove(freq > 150)")
    assert len(ev(big, "freq['_deleted'] > 150")) > 0
    assert len(ev(big, "freq > 150")) == 0


def test_remove_then_add_node_by_variable(s):
    assert s.run("addNode('vx')\nvx.color = red\nremoveNode(vx)")
    assert "vx" in s.ns
    assert s.run("addNode(vx)") and ev(s, "vx.color") == "red" and "vx" in s.graph._nodes
    s.run(f"makeFromGDF({str(SAMPLE)!r})")                    # a new graph drops old names
    assert "vx" not in s.ns


def test_range_field_queries(tmp_path):
    p = tmp_path / "r.gdf"
    p.write_text(RANGES)
    sess = Session(lambda m: None)
    assert sess.run(f"makeFromGDF({str(p)!r})")
    ev_ = lambda e: (sess.run(f"__r = ({e})", interactive=False), sess.ns["__r"])[1]  # noqa: E731
    # the original treats ranges as closed intervals (IntervalNode.overlaps), so v3 (5-12) overlaps (2,5);
    # the manual's text says v0 and v1 only
    assert names(ev_("Node roverlaps (2,5)")) == ["v0", "v1", "v3"]
    assert names(ev_("Node rcontains 5")) == ["v3"]
    assert names(ev_("Node rcontained (19,21)")) == ["v4"]
    assert names(ev_("Node rexact (5,12)")) == ["v3"]
    assert sess.run("addNodeField('span', VARCHAR, None)\nv2.span = '30-40'\nNode.setRangeField(span)\nNode.rebuildRangeIndex()")
    assert names(ev_("Node rcontains 35")) == ["v2"]


def test_visibility_rules(s):
    """§5: hiding a node hides its edges; showing a node shows its edges to
    visible nodes; showing an edge shows its endpoints; hiding an edge leaves them."""
    bob, jane = ev(s, "bob"), ev(s, "jane")
    s.run("bob.visible = 0")
    assert not any(e.visible for e in bob._inc.values())
    s.run("bob.visible = 1")
    assert all(e.visible for e in bob._inc.values())
    s.run("jane.visible = 0")
    aj = next(e for e in jane._inc.values() if e.opposite(jane)._name == "alice")
    assert not aj.visible
    s.run(f"g.edge_by_id({aj._id}).visible = 1")
    assert jane.visible and aj.visible
    s.run(f"g.edge_by_id({aj._id}).visible = 0")
    assert jane.visible and ev(s, "alice.visible")
    s.run("undo()")                                   # the cascade is part of the same undo step
    assert aj.visible


def test_source_destination_and_gradient_ticks(s):
    assert ev(s, "(bob->jane)").source._name == "bob"
    assert ev(s, "(bob->jane)").destination._name == "jane"
    assert ev(s, "(bob-alice)").source is None
    assert s.run("GradientLegend(red, yellow, freq.min, freq.max, 10)")
    lg = s.view.legends[max(s.view.legends)]
    assert lg.record()["ramp"]["ticks"] == 10


def test_display_object_popups_and_exports(s):
    s.rec.clear()
    assert s.run("v.repaint()\nv.setBackgroundImage('https://example.org/m.png', 5, 6)\nprint(v.getLastClickedPosition())")
    s.last_click = (12.5, 3)
    assert ev(s, "v.getLastClickedPosition().getX()") == 12.5
    assert s.run("item = NodeEditorPopup.addItem('Say name')\nseen = []\nitem.menuEvent = lambda n: seen.append(n.name)")
    menu = [m for m in s.rec.of("ui") if m["op"] == "menu"][-1]
    assert menu["items"] == [{"id": menu["items"][0]["id"], "label": "Say name", "scope": "n"}]
    assert s.dispatch(menu["items"][0]["id"], "menuEvent", [["n", ev(s, "bob")._id]])
    assert s.ns["seen"] == ["bob"]
    for fmt in ("PDF", "GIF", "PS", "EPS"):
        s.rec.clear()
        assert s.run(f"export{fmt}('x.{fmt.lower()}')")
        assert s.rec.of("export")[-1]["format"] == fmt.lower()
    assert not s.run("exportSWF('x.swf')")
    assert s.run("getAppletContext().showDocument('https://example.org')")
    assert s.run("vf.defaultEdgeHighlights(false)\nvf.defaultEdgeZooming(false)")
    ui = [m for m in s.rec.of("ui") if m["op"] == "events"][-1]
    assert ui["defaults"]["edgeHighlight"] is False and ui["defaults"]["edgeZoom"] is False


def test_shortest_path_example_from_manual(big):
    assert big.run("addNodeField('shortest', Types.INTEGER, Integer(0))\n"
                   "for n in g.nodes:\n    n.shortest = len(v4.unweightedShortestPath(n))\n"
                   "colorize(shortest, pink, black)")
    assert ev(big, "v4.shortest") == 0 and ev(big, "max(shortest.values())") > 3
