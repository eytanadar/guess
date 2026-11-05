"""Groups, several graphs, glyphs, tree/label layouts, timeline, slides,
connectors (with a fake network), workspace, watched-cell quiet runs."""
import json

import numpy as np
import pytest

from guess import connectors
from guess.layouts import _close_pairs, _label_boxes, _Snapshot
from tests.test_gython import SAMPLE, Recorder, ev, s  # noqa: F401  (fixture)
from tests.test_persist import roundtrip
from guess import Session


@pytest.fixture
def big():
    rec = Recorder()
    sess = Session(rec)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    sess.rec = rec
    return sess


def counts(sess):
    return len(sess.graph._nodes), len(sess.graph._edges)


def test_collapse_expand_nested_and_undo(big):
    assert counts(big) == (402, 725)
    assert big.run("m = collapse(dept == 'dept3', 'three')")
    m = big.ns["m"]
    assert m.members == 9 and m.label == "three (9)" and big.node_record(m)["m"] == 1
    assert big.run("collapseBy(dept)")
    assert counts(big)[0] == 21
    assert big.run("expandAll()") and counts(big) == (402, 725)
    big.run("undo()")
    assert counts(big)[0] == 21
    big.run("undo(); undo()")
    assert counts(big) == (402, 725)
    assert not big.run("expand(v1)")


def test_groups_survive_save_and_load(s):
    s.run("collapse(dept == 'IT', 'it')")
    t = roundtrip(s)
    assert t.run("expand(it)") and sorted(t.graph._nodes) == ["al_x", "alice", "bob", "jane"]


def test_several_graphs(big):
    big.run("colorize(dept)")
    color = ev(big, "v4.color")
    assert big.run("subgraph(dept == 'dept3', 'three')")
    assert counts(big) == (9, 12) and ev(big, "v4.color") == color and ev(big, "graphNames()") == ["three", "main"]
    assert big.run("use('main')") and counts(big) == (402, 725)
    assert big.run("newGraph('empty')") and counts(big) == (0, 0)
    t = roundtrip(big)
    assert t.workspaces["current"] == "empty" and set(t.workspaces["stored"]) == {"three", "main"}
    assert t.run("use('three')") and counts(t) == (9, 12)
    assert not big.run("closeGraph('empty')")
    assert big.run("use('main'); closeGraph('empty')") and "empty" not in ev(big, "graphNames()")


def test_pie_border_bundle(big):
    assert big.run("pieNeighbors(dept)")
    p = big.node_record(ev(big, "v4"))["p"]
    assert sum(p) == len([e for e in ev(big, "v4")._inc.values() if e.opposite(ev(big, "v4")) is not ev(big, "v4")])
    assert big.view.record()["pie"] and big.view.legends
    assert big.run("pieChart([indegree, outdegree])") and big.node_record(ev(big, "v4"))["p"] == [12.0, 12.0]
    assert big.run("pieOff()") and "p" not in big.node_record(ev(big, "v4"))
    assert big.run("borderBy(dept)") and big.view.border_width == 2.5 and ev(big, "v4.strokecolor")
    assert big.run("louvainClusters(); bundleEdges(modularity_class)")
    assert len(big.graph.bends) > 20
    assert big.run("unbundleEdges()") and not big.graph.bends


def test_tree_and_label_adjust(big):
    assert big.run("treeLayout(v128)")
    v = ev(big, "v128")
    kids = [e.opposite(v) for e in v._inc.values()]
    assert all(k.y > v.y for k in kids if k is not v)
    assert big.run("treeLayout(horizontal=true)")
    big.run("g.nodes.labelvisible = true")
    assert big.run("labelAdjustLayout()")
    sn = _Snapshot(big.graph)
    half, off = _label_boxes(sn)
    B = sn.pos + sn.size / 2 + off
    ii, jj = _close_pairs(B, np.hypot(*half.T))
    d = B[ii] - B[jj]
    over = ((half[ii, 0] + half[jj, 0] - abs(d[:, 0])) > 0.5) & ((half[ii, 1] + half[jj, 1] - abs(d[:, 1])) > 0.5)
    assert not over.any()


def test_timeline(s):
    s.run("addRange(bob, '1-3'); addRange(alice, '2-5'); addRange(bob-alice, '2-3')")
    info = s.panel_data("timeline", "")
    assert info["min"] == 1 and info["max"] == 5 and info["steps"] == [1, 2, 3, 4, 5] and info["counts"][1] == 3
    assert s.run("showTime(4)")
    assert not ev(s, "bob.visible") and ev(s, "alice.visible") and ev(s, "jane.visible")
    s.run("addNodeField('year', INT, 0); bob.year = 2000; alice.year = 2005; jane.year = 2010; al_x.year = 2010")
    assert s.panel_data("timeline", "year")["counts"][-1] == 4
    assert s.run("showTime(2006, year)")
    assert ev(s, "(bob.visible, alice.visible, jane.visible)") == (True, True, False)
    assert s.run("showTime(2006, year, window=3)")
    assert ev(s, "(bob.visible, alice.visible)") == (False, True)


def test_slides(s):
    s.rec.clear()
    assert s.run("addSlide('first', camera=[1, 2, 3])")
    s.run("bob.color = red")
    assert s.run("addSlide('second')")
    assert s.rec.of("slides")[-1]["slides"] == [{"note": "first"}, {"note": "second"}]
    s.rec.clear()
    assert s.run("showSlide(0, 0)")
    assert s.rec.of("camera")[-1]["camera"] == [1, 2, 3]
    assert ev(s, "bob.color") == "cornflowerblue"
    assert ev(s, "slides()") == ["first", "second"]
    assert roundtrip(s).view.slides[1]["note"] == "second"
    assert s.run("removeSlide(0)") and ev(s, "slides()") == ["second"]


def test_connectors_with_fake_network(s, monkeypatch, tmp_path):
    pages = {
        "https://x.org/g.gexf": open(tmp_path / "x", "w").close() or """<gexf><graph><nodes><node id="a"/><node id="b"/></nodes><edges><edge source="a" target="b"/></edges></graph></gexf>""",
    }
    sparql_json = {"results": {"bindings": [
        {"source": {"type": "uri", "value": "http://www.wikidata.org/entity/Q1"}, "sourceLabel": {"type": "literal", "value": "Kant"},
         "target": {"type": "uri", "value": "http://www.wikidata.org/entity/Q2"}, "targetLabel": {"type": "literal", "value": "Hume"},
         "year": {"type": "literal", "value": "1781", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}]}}
    cx2 = [{"attributeDeclarations": [{"nodes": {"type": {"d": "string"}}}]},
           {"nodes": [{"id": 1, "v": {"name": "TP53", "type": "gene"}, "x": 10, "y": 20}, {"id": 2, "v": {"name": "MDM2"}}]},
           {"edges": [{"id": 5, "s": 1, "t": 2, "v": {"interaction": "binds"}}]},
           {"networkAttributes": [{"name": "p53 net"}]}]
    neo = {"results": [{"data": [{"graph": {"nodes": [{"id": "1", "labels": ["Person"], "properties": {"name": "Ann", "age": 30}},
                                                       {"id": "2", "labels": ["Person"], "properties": {"name": "Bo"}}],
                                             "relationships": [{"id": "9", "type": "KNOWS", "startNode": "1", "endNode": "2", "properties": {"since": 2001}}]}}]}],
           "errors": []}

    def fake(url, method="GET", body=None, headers=None):
        if url in pages:
            return pages[url]
        if "sparql" in url:
            return json.dumps(sparql_json)
        if "ndexbio" in url:
            return json.dumps(cx2)
        if "tx/commit" in url:
            assert method == "POST" and headers["Authorization"].startswith("Basic ")
            return json.dumps(neo)
        raise AssertionError(url)

    monkeypatch.setattr(connectors, "http", fake)
    monkeypatch.chdir(tmp_path)
    assert s.run("makeFromURL('https://x.org/g.gexf')") and counts(s) == (2, 1)
    assert s.run("makeFromSPARQL('SELECT ...')"), s.rec.of("error")
    assert ev(s, "Q1.label") == "Kant" and ev(s, "g.edges[0].year") == "1781"
    assert s.run("makeFromNDEx('abc')")
    assert ev(s, "n1.label") == "TP53" and ev(s, "n1.type") == "gene" and ev(s, "(n1.x, n1.y)") == (10, 20)
    assert s.run("makeFromCypher('MATCH p=()-->() RETURN p', 'http://h:7474', 'neo4j', 'pw')")
    assert ev(s, "(n1.label, n1.kind, n1.age)") == ("Ann", "Person", 30) and ev(s, "g.edges[0].type") == "KNOWS"
    s.rec.clear()
    assert s.run("installPackage('tqdm')") and s.rec.of("install")[-1]["name"] == "tqdm"


def test_workspace_and_quiet_runs(s):
    s.run("hubs = (dept == 'IT')\nn_count = 4")
    ws = s.workspace()
    names = {v["name"]: v for v in ws["vars"]}
    assert names["hubs"]["value"] == "2 nodes" and names["hubs"]["items"][0][0] == "n"
    assert names["n_count"]["value"] == "4" and "VARCHAR" not in names
    before = len(s.executed), len(s.undo_stack)
    s.quiet_next = True
    assert s.run("bob.color = red")
    assert (len(s.executed), len(s.undo_stack)) == before


def test_charts_update_in_place(s):
    s.rec.clear()
    s.run("plotSizes(dept)")
    s.run("plotSizes(dept)")
    ids = [m["id"] for m in s.rec.of("chart")]
    assert len(ids) == 2 and ids[0] == ids[1]


def test_hive_layout(big):
    import math
    assert big.run("hiveLayout(dept, pagerank, axes=4)")
    guides = big.view.guides
    assert len(guides) == 4 and guides[-1]["label"].startswith("other")
    assert "pagerank" in big.view.guides_note
    # every node lies on one of the axis rays from the centre
    angles = [math.atan2(g["y2"] - 500, g["x2"] - 500) for g in guides]
    for n in big.graph._nodes_list():
        cx, cy = n.x + n.width / 2 - 500, n.y + n.height / 2 - 500
        a = math.atan2(cy, cx)
        assert min(abs((a - b + math.pi) % (2 * math.pi) - math.pi) for b in angles) < 1e-6
    assert len(big.graph.bends) > 500
    from tests.test_persist import roundtrip
    assert len(roundtrip(big).view.guides) == 4
    # the sample graph is undirected: leaves / connectors / hubs by degree
    assert big.run("hiveLayout()")
    assert [g["label"].split(" (")[0] for g in big.view.guides] == ["leaves", "connectors", "hubs"]
    big.run("makeSimpleDirectedRandom(30, 60)")
    assert big.run("hiveLayout()")
    assert [g["label"].split(" (")[0] for g in big.view.guides] == ["sources", "hubs", "sinks"]
    assert big.run("gemLayout()") and big.view.guides == [] and not big.graph.bends
    assert not big.run("hiveLayout(dept, scale='cubic')")


def test_new_graph_drops_old_overlays(big, tmp_path):
    assert big.run("hiveLayout(dept); colorize(dept); legendFor(dept); createConvexHull(dept == 'dept1'); pieNeighbors(dept)")
    assert big.view.guides and big.view.legends and big.view.hulls and big.view.pie
    big.run("curvedEdges(); select(dept == 'dept1')")
    assert big.run(f"makeFromGDF({str(SAMPLE)!r})")
    v = big.view
    assert v.guides == [] and v.guides_note == "" and v.legends == {} and v.hulls == {} and v.pie is None
    assert v.drag == {} and len(ev(big, "sel")) == 0
    assert v.curvature > 0                       # display preferences stay
    big.run("undo()")                            # undoing the load brings them back
    assert big.view.guides and big.view.legends and big.view.hulls
    # a saved session restores its own legends after the clear
    f = tmp_path / "s.guess"
    assert big.run(f"saveSession({str(f)!r})")
    assert big.run("makeSimpleRandom(5, 4)") and not big.view.legends
    assert big.run(f"makeFromSession({str(f)!r})") and big.view.legends and big.view.guides


def test_set_nodes_and_edges(s):
    heavy = ev(s, "(freq > 9).nodes")             # bob-alice (10), bob->jane (30)
    assert sorted(n._name for n in heavy) == ["alice", "bob", "jane"]
    assert len(ev(s, "(dept == 'IT').edges")) == 4    # every edge touching bob or alice
    assert [n._name for n in ev(s, "(dept == 'IT').nodes")] == ["bob", "alice"]
    assert s.run("(freq > 9).nodes.color = red") and ev(s, "jane.color") == "red"
    s.run("setEdgeColorMode('mixed')")
    s.rec.clear()
    s.run("(freq > 9).color = blue")
    assert "setEdgeColorMode" in "".join(m["text"] for m in s.rec.of("text"))
