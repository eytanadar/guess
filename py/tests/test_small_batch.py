"""Gython conveniences: field creation by assignment, colours, `;`, compact
groups, where(), mismatch notes, scratch(), fast membership, louvain_class."""
from pathlib import Path

from guess import Session
from tests.test_gython import Recorder

SAMPLE = Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    rec.clear()
    return s


def ev(s, code):
    assert s.run(f"__r = {code}"), s.rec.of("error")
    return s.ns["__r"]


def test_assigning_to_Node_makes_a_field():
    s = _s()
    assert s.run("Node.score = 0\nNode.weight2 = 1.5\nNode.note = ''\nNode.flag = false"), s.rec.of("error")
    sch = s.graph.node_schema
    assert (sch["score"].type, sch["weight2"].type, sch["note"].type, sch["flag"].type) == \
        ("INTEGER", "DOUBLE", "VARCHAR", "BOOLEAN")
    assert ev(s, "v1.score") == 0 and s.run("v1.score = 4") and ev(s, "len(score > 0)") == 1
    assert not s.run("Node.score = 3")
    assert "already exists" in s.rec.of("error")[-1]["summary"]
    s2 = _s()
    assert s2.run("Node.flag = false") and "flag" in s2.graph.node_schema
    assert s2.run("undo()") and "flag" not in s2.graph.node_schema     # undoable like any change


def test_unknown_field_hints_and_keyword_fields():
    s = _s()
    assert not s.run("v1.colour = red")
    assert "did you mean 'color'" in s.rec.of("error")[-1]["summary"]
    assert "Node.colour" in s.rec.of("error")[-1]["summary"]
    s.run("addNodeField('class', VARCHAR, 'a')")
    assert ev(s, "v1.class_") == "a" and len(ev(s, "Node.class_ == 'a'")) == len(s.graph.nodes)
    assert s.run("v1.class_ = 'b'") and ev(s, "v1.class_") == "b"


def test_colours_compare_by_meaning_and_vary():
    s = _s()
    s.run("colorize(dept)\nv2.color = '255,0,0'")
    assert ev(s, "v2.color == red") is True
    assert ev(s, "len(color == red)") >= 1
    assert ev(s, "(red.alpha(80), red.lighter(0.5), red.darker(0.5), red.alpha(0.5))") == \
        ("255,0,0,80", "255,128,128", "128,0,0", "255,0,0,128")
    assert ev(s, "v2.color.lighter(0.5)") == "255,128,128"
    assert ev(s, "red == 'hello'") is False and ev(s, "red != blue") is True


def test_web_colour_names_work_and_2006_names_win():
    s = _s()
    assert s.run("v1.color = steelblue\nv2.color = 'Tomato'"), s.rec.of("error")
    assert ev(s, "v1.color == '70,130,180'") is True and ev(s, "v2.color == '255,99,71'") is True
    assert ev(s, "green == '0,255,0'") is True          # the 2006 green, not CSS's 0,128,0
    s.run("addNodeField('tan', INTEGER, 3)")
    assert s.is_protected("tan") == "field"              # a field outranks a colour name

def test_semicolon_hides_the_echo():
    s = _s()
    assert s.run("v1;") and not s.rec.of("out")
    assert s.run("v1") and len(s.rec.of("out")) == 1
    assert s.run("louvainClusters();") and len(s.rec.of("out")) == 1


def test_many_groups_print_compactly_and_stay_linked():
    s = _s()
    s.run("groupBy(dept)")
    g = s.rec.of("out")[-1]["segs"][0]["g"]
    assert g[0].startswith("21 groups (402 elements)")
    first = g[1]
    assert first["g"] == ["[dept0: 28]"] and len(first["x"]) == 28 and first["a"] == "dept == 'dept0'"


def test_where_returns_a_set():
    s = _s()
    w = ev(s, "g.edges.where(lambda e: e.node1.dept != e.node2.dept)")
    assert len(w) == len(ev(s, "interEdges(dept)")) and hasattr(w, "annotation")
    assert not s.run("g.nodes.where(3)")


def test_mismatched_query_notes_once():
    s = _s()
    assert ev(s, "len(dept == 3)") == 0
    notes = [m["text"] for m in s.rec.of("text") if "note:" in m["text"]]
    assert len(notes) == 1 and "holds text" in notes[0]
    ev(s, "len(dept == 4)")
    assert len([m for m in s.rec.of("text") if "note:" in m["text"]]) == 1
    assert ev(s, "len(degree == 'abc')") == 0
    assert any("holds numbers" in m["text"] for m in s.rec.of("text"))


def test_scratch_puts_the_graph_back():
    s = _s()
    assert s.run("with scratch():\n    remove(dept == 'dept1')\n    Node.tmp = 1\n    __n = len(g.nodes)"), \
        s.rec.of("error")
    assert s.ns["__n"] == 359 and len(s.graph.nodes) == 402 and len(s.graph.edges) == 725
    assert "tmp" not in s.graph.node_schema


def test_membership_is_fast_and_correct():
    s = _s()
    s.run("big = (degree >= 0)\nsmall = (dept == 'dept1')")
    assert ev(s, "sum(1 for n in g.nodes if n in big)") == 402
    assert ev(s, "sum(1 for n in g.nodes if n in small)") == 43
    s.run("big.append(addNode('zz'))")
    assert ev(s, "zz in big") is True


def test_louvain_field_and_plurals():
    s = _s()
    s.run("__c = louvainClusters()")
    assert "louvain_class" in s.graph.node_schema
    assert s.ns["__c"].annotation.endswith("communities")


def test_exports_in_a_loop_show_each_step_and_collect_into_a_zip():
    s = _s()
    s.rec.clear()
    assert s.run("startImages('frames')\n"
                 "for c in [red, blue]:\n"
                 "    v1.color = c\n"
                 "    exportPNG('step.png')\n"
                 "stopImages()"), s.rec.of("error")
    kinds = [m["type"] for m in s.rec.msgs if m["type"] in ("patch", "export", "images")]
    # each export comes after the change before it, between start and stop
    assert kinds[0] == "images" and kinds[-1] == "images"
    exports = [i for i, k in enumerate(kinds) if k == "export"]
    assert len(exports) == 2 and all(kinds[i - 1] == "patch" for i in exports)
    start = next(m for m in s.rec.msgs if m["type"] == "images")
    assert start == {"type": "images", "op": "start", "name": "frames.zip"}
    assert not s.run("stopImages()")
    assert "no images are being collected" in s.rec.of("error")[-1]["summary"]
    assert s.run("startImages()") and not s.run("startImages()")
    assert "already collecting" in s.rec.of("error")[-1]["summary"]
