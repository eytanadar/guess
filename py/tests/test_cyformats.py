"""Cytoscape formats: SIF, NNF, Cytoscape.js JSON, CX/CX2, XGMML, .cys sessions."""
import io
import json
import pathlib
import zipfile

import pytest

from tests.test_gython import ev, s  # noqa: F401  (fixture)

BRCA1 = pathlib.Path("/Users/eadar/Documents/GitHub/guess/sub-structure-cyto-layout/demo/data/BRCA1.cyjs")


def rgb(s, expr):
    from guess import colors
    return colors.parse(str(ev(s, expr)))[:3]


def printed(s):
    out = [m.get("text", "") for m in s.rec.of("text")]
    for m in s.rec.of("out"):
        out += [x if isinstance(x, str) else x.get("t", "") for x in m.get("segs", [])]
    return "".join(out)


def counts(s):
    return len(s.graph._nodes), len(s.graph._edges)


def load(s, tmp_path, name, content, cmd):
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content)
    s.rec.clear()
    ok = s.run(f"{cmd}({str(p)!r})")
    assert ok, s.rec.of("error")
    s.loaded_text = printed(s)          # ev() clears the record: keep what loading printed
    return p


# ---- SIF ------------------------------------------------------------------------

def test_sif_spaces(s, tmp_path):
    load(s, tmp_path, "a.sif", "A pp B C\nB pd D\nA pp B\nE\nD pp D\n", "makeFromSIF")
    assert counts(s) == (5, 5)                        # duplicate A-B and the self-loop D-D kept
    assert ev(s, "sorted(e.interaction for e in g.edges)") == ["pd", "pp", "pp", "pp", "pp"]
    assert ev(s, "E.degree") == 0
    assert not any(e._directed for e in s.graph._edges_list())


def test_sif_tabs_allow_spaces_in_names(s, tmp_path):
    load(s, tmp_path, "b.sif", "protein one\tbinds\tprotein two\tthree\nlonely node\n", "makeFromSIF")
    assert set(s.graph._nodes) == {"protein one", "protein two", "three", "lonely node"}
    assert s.run(f"makeFromSIF({str(tmp_path / 'b.sif')!r}, directed=true)")
    assert all(e._directed for e in s.graph._edges_list())


def test_sif_errors(s, tmp_path):
    p = tmp_path / "bad.sif"
    p.write_text("A pp B\nC D\n")
    assert not s.run(f"makeFromSIF({str(p)!r})")
    assert "line 2" in s.rec.of("error")[-1]["text"]


# ---- NNF ------------------------------------------------------------------------

NNF = """# a nested network
root M1
root M2
root M1 pp M2
M1 a pp b
M1 b pp c
M2 c pp d
M2 e
"""


def test_nnf(s, tmp_path):
    load(s, tmp_path, "n.nnf", NNF, "makeFromNNF")
    assert counts(s) == (7, 4)
    assert ev(s, "M1.nested") == "M1" and ev(s, "M1.network") == "root"
    assert ev(s, "c.network") == "M1; M2"                        # in both nested networks
    assert ev(s, "sorted(x.name for x in (network == 'M2'))") == ["d", "e"]     # c is in two
    assert ev(s, "sorted(x.name for x in g.nodes if 'M2' in x.network)") == ["c", "d", "e"]
    assert ev(s, "[e.network for e in g.edges if {str(e.node1), str(e.node2)} == {'M1', 'M2'}][0]") == "root"
    assert "nested networks: M1, M2" in s.loaded_text
    p = tmp_path / "bad.nnf"
    p.write_text("net a b\n")
    assert not s.run(f"makeFromNNF({str(p)!r})")


# ---- Cytoscape.js JSON ----------------------------------------------------------

CYJS = {
    "format_version": "1.0", "generated_by": "cytoscape-3.10", "data": {"name": "test"},
    "elements": {
        "nodes": [
            {"data": {"id": "1", "name": "BRCA1", "SUID": 1, "selected": False, "shared_name": "BRCA1",
                      "score": 0.5, "kind": "protein", "aliases": ["a", "b"], "parent": "9"},
                      "position": {"x": 10.0, "y": 20.0}},
            {"data": {"id": "2", "name": "BRCA1", "score": 1, "kind": "protein"}, "position": {"x": 30, "y": 40}},
            {"data": {"id": "3", "label": "TP53", "color": "#ff0000"}, "position": {"x": 0, "y": 0}},
            {"data": {"id": "9", "name": "complex", "isParent": True}},
        ],
        "edges": [
            {"data": {"id": "e1", "source": "1", "target": "3", "interaction": "binds", "shared_interaction": "binds",
                      "weight": 2.5, "SUID": 5}},
            {"data": {"id": "e2", "source": "2", "target": "3", "interaction": "binds"}},
        ],
    },
}


def test_cyjs_wrapped(s, tmp_path):
    load(s, tmp_path, "x.cyjs", json.dumps(CYJS), "makeFromCYJS")
    assert counts(s) == (3, 2)                                      # the group box (9) has no edges: dropped
    names = sorted(s.graph._nodes)
    assert names == ["BRCA1_1", "BRCA1_2", "TP53"]                  # a shared name gets the id
    assert ev(s, "BRCA1_1.label") == "BRCA1" and ev(s, "BRCA1_1.parent") == "complex"
    assert ev(s, "(BRCA1_1.x, BRCA1_1.y)") == (10.0, 20.0)
    assert ev(s, "BRCA1_1.aliases") == "a; b"
    assert s.graph.node_schema["score"].type == "DOUBLE"
    assert "SUID" not in s.graph.node_schema and "shared_name" not in s.graph.node_schema
    assert rgb(s, "TP53.color") == (255, 0, 0)
    e = next(x for x in s.graph._edges_list() if x._n1._name == "BRCA1_1")
    assert e.interaction == "binds" and float(e.weight) == 2.5
    assert "shared_interaction" not in s.graph.edge_schema


def test_cyjs_flat_array(s, tmp_path):
    flat = [{"group": "nodes", "data": {"id": "a"}}, {"group": "nodes", "data": {"id": "b"}},
            {"group": "edges", "data": {"id": "ab", "source": "a", "target": "b"}},
            {"data": {"id": "c"}}, {"data": {"id": "bc", "source": "b", "target": "c"}}]
    load(s, tmp_path, "f.json", json.dumps(flat), "makeFromCYJS")
    assert counts(s) == (3, 2)


def test_cyjs_round_trip(s, tmp_path):
    assert s.run("bob.color = red\nbob.width = 22\nbob.style = 12\naddNodeField('team', VARCHAR, '')\nbob.team = 'x'")
    before = {n._name: (float(n.x), float(n.y)) for n in s.graph._nodes_list()}
    ne = len(s.graph._edges)
    p = tmp_path / "out.cyjs"
    assert s.run(f"exportCYJS({str(p)!r})")
    doc = json.loads(p.read_text())
    assert doc["elements"]["nodes"][0]["position"] and s.rec.of("download")[-1]["name"] == "out.cyjs"
    assert s.run(f"makeFromCYJS({str(p)!r})"), s.rec.of("error")
    assert {n._name: (float(n.x), float(n.y)) for n in s.graph._nodes_list()} == before
    assert len(s.graph._edges) == ne
    assert ev(s, "bob.team") == "x" and ev(s, "bob.width") == 22 and ev(s, "bob.style") == 12
    assert rgb(s, "bob.color") == (255, 0, 0)


@pytest.mark.skipif(not BRCA1.exists(), reason="LUMINA demo data missing")
def test_cyjs_real_file(s):
    assert s.run(f"makeFromCYJS({str(BRCA1)!r})"), s.rec.of("error")
    assert len(s.graph._nodes) == 1228
    assert "IntAct_MI_Score" in s.graph.edge_schema


# ---- CX and CX2 -----------------------------------------------------------------

CX2 = [{"CXVersion": "2.0", "hasFragments": False},
       {"metaData": [{"name": "nodes", "elementCount": 2}]},
       {"attributeDeclarations": [{"nodes": {"name": {"d": "string"}, "score": {"d": "double", "a": "s"},
                                             "kind": {"d": "string", "v": "gene"}},
                                   "edges": {"interaction": {"d": "string"}}}]},
       {"networkAttributes": [{"name": "my net"}]},
       {"nodes": [{"id": 1, "v": {"name": "TP53", "s": 2}, "x": 5, "y": 6}, {"id": 2, "v": {"name": "MDM2"}}]},
       {"edges": [{"id": 3, "s": 1, "t": 2, "v": {"interaction": "binds"}}]},
       {"visualProperties": [{"default": {"node": {"NODE_BACKGROUND_COLOR": "#00FF00", "NODE_WIDTH": 30,
                                                   "NODE_HEIGHT": 30, "NODE_SHAPE": "round-rectangle"},
                                          "edge": {"EDGE_WIDTH": 3}}}]},
       {"nodeBypasses": [{"id": 2, "v": {"NODE_BACKGROUND_COLOR": "#0000FF"}}]},
       {"status": [{"success": True}]}]

CX1 = [{"numberVerification": [{"longNumber": 281474976710655}]},
       {"metaData": [{"name": "nodes"}]},
       {"nodes": [{"@id": 10, "n": "A", "r": "uniprot:P1"}, {"@id": 11, "n": "B"}, {"@id": 12, "n": "A"}]},
       {"edges": [{"@id": 20, "s": 10, "t": 11, "i": "pp"}, {"@id": 21, "s": 11, "t": 12, "i": "pd"}]},
       {"nodeAttributes": [{"po": 10, "n": "score", "v": "1.5", "d": "double"},
                           {"po": [11, 12], "n": "kind", "v": "gene"}]},
       {"edgeAttributes": [{"po": 20, "n": "weight", "v": "4", "d": "double"}]},
       {"networkAttributes": [{"n": "name", "v": "cx one"}]},
       {"cartesianLayout": [{"node": 10, "x": 1.0, "y": 2.0}, {"node": 11, "x": 3.0, "y": 4.0}]},
       {"cyVisualProperties": [{"properties_of": "nodes:default", "properties": {"NODE_FILL_COLOR": "#FF0000", "NODE_SIZE": "40.0"}},
                               {"properties_of": "nodes", "applies_to": 11, "properties": {"NODE_FILL_COLOR": "#00FF00"}}]},
       {"status": [{"error": "", "success": True}]}]


def test_cx2(s, tmp_path):
    load(s, tmp_path, "n.cx2", json.dumps(CX2), "makeFromCX")
    assert counts(s) == (2, 1)
    assert ev(s, "(TP53.score, TP53.kind, MDM2.kind)") == (2.0, "gene", "gene")
    assert ev(s, "(TP53.x, TP53.y)") == (5.0, 6.0)
    assert rgb(s, "TP53.color") == (0, 255, 0) and rgb(s, "MDM2.color") == (0, 0, 255)
    assert ev(s, "TP53.width") == 30 and ev(s, "TP53.style") == 3
    assert ev(s, "g.edges[0].interaction") == "binds" and ev(s, "g.edges[0].width") == 3
    assert "my net" in s.loaded_text


def test_cx1(s, tmp_path):
    load(s, tmp_path, "n.cx", json.dumps(CX1), "makeFromCX")
    assert counts(s) == (3, 2)
    assert sorted(s.graph._nodes) == ["A_10", "A_12", "B"]
    assert ev(s, "(A_10.score, A_10.represents, B.kind, A_12.kind)") == (1.5, "uniprot:P1", "gene", "gene")
    assert ev(s, "(A_10.x, A_10.y)") == (1.0, 2.0)
    assert rgb(s, "A_10.color") == (255, 0, 0) and rgb(s, "B.color") == (0, 255, 0)
    assert ev(s, "A_10.width") == 40
    assert ev(s, "sorted(e.interaction for e in g.edges)") == ["pd", "pp"]
    assert ev(s, "[e.weight for e in g.edges if e.interaction == 'pp'][0]") == 4.0
    assert all(e._directed for e in s.graph._edges_list())
    assert s.run(f"makeFromCX({str(tmp_path / 'n.cx')!r}, directed=false)")
    assert not any(e._directed for e in s.graph._edges_list())


# ---- XGMML ----------------------------------------------------------------------

XGMML = """<?xml version="1.0" encoding="UTF-8"?>
<graph id="1" label="Sales & Support" directed="1" xmlns="http://www.cs.rpi.edu/XGMML"
       xmlns:cy="http://www.cytoscape.org" xmlns:xlink="http://www.w3.org/1999/xlink">
  <att name="shared name" value="net" type="string"/>
  <node id="10" label="Alice">
    <att name="name" value="Alice" type="string"/>
    <att name="age" value="34" type="integer"/>
    <att name="score" value="0.5" type="real"/>
    <att name="boss" value="1" type="boolean"/>
    <att name="tags" type="list"><att value="a" type="string"/><att value="b" type="string"/></att>
    <graphics type="DIAMOND" h="20.0" w="30.0" x="100.0" y="-50.0" fill="#FF0000" outline="#000000"/>
  </node>
  <node id="11" label="Bob">
    <att name="name" value="Bob" type="string"/>
    <graphics type="ELLIPSE" x="0" y="0" fill="#00ff00"/>
  </node>
  <edge id="20" label="Alice (knows) Bob" source="10" target="11" cy:directed="0">
    <att name="interaction" value="knows" type="string"/>
    <att name="weight" value="3" type="real"/>
    <graphics width="4.0" fill="#0000FF"/>
  </edge>
</graph>
"""


def test_xgmml(s, tmp_path):
    load(s, tmp_path, "x.xgmml", XGMML, "makeFromXGMML")          # the bare '&' is repaired
    assert counts(s) == (2, 1)
    assert ev(s, "(Alice.age, Alice.score, Alice.boss, Alice.tags)") == (34, 0.5, True, "a; b")
    assert ev(s, "(Alice.x, Alice.y, Alice.width, Alice.height, Alice.style)") == (100.0, -50.0, 30.0, 20.0, 12)
    assert rgb(s, "Alice.color") == (255, 0, 0) and rgb(s, "Bob.color") == (0, 255, 0)
    e = s.graph._edges_list()[0]
    assert not e._directed and e.interaction == "knows" and float(e.weight) == 3 and float(e.width) == 4
    assert rgb(s, "g.edges[0].color") == (0, 0, 255)
    p = tmp_path / "bad.xgmml"
    p.write_text("<graph><node id='1'></graph>")
    assert not s.run(f"makeFromXGMML({str(p)!r})")
    assert "line" in s.rec.of("error")[-1]["text"]


# ---- .cys sessions --------------------------------------------------------------

def _cys():
    net = """<?xml version="1.0"?>
<graph id="52" label="collection" directed="1" xmlns="http://www.cs.rpi.edu/XGMML"
  xmlns:cy="http://www.cytoscape.org" xmlns:xlink="http://www.w3.org/1999/xlink" cy:documentVersion="3.0">
  <node id="101" label="101"/>
  <node id="102" label="102"/>
  <node id="103" label="103"/>
  <edge id="201" label="201" source="101" target="102"/>
  <edge id="202" label="202" source="102" target="103"/>
  <att><graph id="60" label="first" cy:registered="1">
    <att name="name" value="First network" type="string"/>
    <node xlink:href="#101"/><node xlink:href="#102"/><edge xlink:href="#201"/>
  </graph></att>
  <att><graph id="61" label="second" cy:registered="1">
    <node xlink:href="#101"/><node xlink:href="#102"/><node xlink:href="#103"/>
    <edge xlink:href="#201"/><edge xlink:href="#202"/>
  </graph></att>
</graph>"""
    view = """<?xml version="1.0"?>
<graph id="70" label="view" cy:view="1" cy:networkId="60" xmlns="http://www.cs.rpi.edu/XGMML"
  xmlns:cy="http://www.cytoscape.org">
  <node id="701" label="TP53" cy:nodeId="101"><graphics x="5" y="7" w="40" h="40" fill="#FF0000" type="TRIANGLE"/></node>
  <node id="702" label="MDM2" cy:nodeId="102"><graphics x="50" y="70" fill="#00FF00"/></node>
</graph>"""
    nodes = 'SUID,shared name,name,selected,score\nLong,String,String,Boolean,Double\n101,TP53,TP53,false,2.5\n102,MDM2,MDM2,false,1.0\n103,ATM,ATM,false,\n'
    edges = 'SUID,shared interaction,interaction,shared name,name\nLong,String,String,String,String\n201,binds,binds,a,a\n202,pp,pp,b,b\n'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CytoscapeSession-2026/networks/52-collection.xgmml", net)
        z.writestr("CytoscapeSession-2026/views/60-70-first.xgmml", view)
        z.writestr("CytoscapeSession-2026/tables/52-collection/SHARED_ATTRS-org.cytoscape.model.CyNode-1.cytable", nodes)
        z.writestr("CytoscapeSession-2026/tables/52-collection/SHARED_ATTRS-org.cytoscape.model.CyEdge-1.cytable", edges)
    return buf.getvalue()


def test_cys_session(s, tmp_path):
    p = load(s, tmp_path, "s.cys", _cys(), "makeFromCYS")
    assert counts(s) == (2, 1)                                   # the first network
    assert sorted(s.graph._nodes) == ["MDM2", "TP53"]
    assert ev(s, "(TP53.x, TP53.y, TP53.width, TP53.style, TP53.score)") == (5.0, 7.0, 40.0, 11, 2.5)
    assert rgb(s, "TP53.color") == (255, 0, 0)
    assert ev(s, "g.edges[0].interaction") == "binds"
    text = s.loaded_text
    assert "First network" in text and "1: second" in text
    assert s.run(f"makeFromCYS({str(p)!r}, 'second')") and counts(s) == (3, 2)
    assert s.run(f"makeFromCYS({str(p)!r}, 1)") and counts(s) == (3, 2)
    assert not s.run(f"makeFromCYS({str(p)!r}, 'nope')")
    assert s.run(f"makeFromCYS({str(p)!r}, 'all')"), s.rec.of("error")
    assert ev(s, "graphNames()") == ["First network", "second"] and counts(s) == (2, 1)
    assert s.run("use('second')") and counts(s) == (3, 2)
    bad = tmp_path / "bad.cys"
    bad.write_bytes(b"not a zip")
    assert not s.run(f"makeFromCYS({str(bad)!r})")


def test_make_from_url_recognises_cytoscape_formats(s, tmp_path, monkeypatch):
    from guess import connectors
    pages = {"https://e.org/a": json.dumps(CX2), "https://e.org/b": XGMML, "https://e.org/c": json.dumps(CYJS),
             "https://e.org/d.sif": "A pp B\n"}
    monkeypatch.setattr(connectors, "http", lambda url, **k: pages[url])
    monkeypatch.chdir(tmp_path)
    assert s.run("makeFromURL('https://e.org/a')") and counts(s) == (2, 1)
    assert s.run("makeFromURL('https://e.org/b')") and counts(s) == (2, 1)
    assert s.run("makeFromURL('https://e.org/c')") and counts(s) == (3, 2)
    assert s.run("makeFromURL('https://e.org/d.sif')") and counts(s) == (2, 1)
