"""Label position and size fields, label commands, and the new shapes."""
import pytest

from guess import Session
from guess.textwidth import text_size
from tests.test_gython import Recorder, ev


@pytest.fixture
def s():
    rec = Recorder()
    sess = Session(rec)
    sess.rec = rec
    assert sess.run("makeSample('florentine')"), rec.of("error")
    return sess


def run(s, code):
    s.rec.clear()
    assert s.run(code), s.rec.of("error")


def test_labelpos_values_and_records(s):
    assert ev(s, "Medici.labelpos") == "right" and ev(s, "Medici.labelsize") == 1.0
    for pos in ("left", "above", "below", "inside", "outside", "Right"):
        run(s, f"Medici.labelpos = {pos!r}")
        assert ev(s, "Medici.labelpos") == pos.lower()
    assert not s.run("Medici.labelpos = 'middle'")
    assert "labelpos should be one of" in s.rec.of("error")[-1]["text"]
    assert not s.run("Medici.labelsize = 0")
    run(s, "Medici.labelpos = 'inside'\nMedici.labelsize = 1.5")
    rec = s.node_record(s.graph.getNodeByName("Medici"))
    assert rec["lp"] == "inside" and rec["ls"] == 1.5
    assert "lp" not in s.node_record(s.graph.getNodeByName("Pazzi"))      # defaults aren't sent
    e = s.graph._edges_list()[0]
    run(s, "for e in g.edges: e.labelsize = 0.7")
    assert s.edge_record(e)["ls"] == 0.7


def test_label_size_by_and_edge_labels_along(s):
    run(s, "labelSizeBy(totaldegree, 0.8, 2)")
    sizes = ev(s, "[(n.totaldegree, n.labelsize) for n in g.nodes]")
    lo, hi = min(d for d, _ in sizes), max(d for d, _ in sizes)
    for d, ls in sizes:
        assert ls == pytest.approx(0.8 + 1.2 * (d - lo) / (hi - lo))
    run(s, "edgeLabelsAlong()")
    assert s.rec.of("overlay")[-1]["labels"]["along"] is True
    run(s, "undo()")
    assert s.view.labels["along"] is False


def test_fit_nodes_to_labels(s):
    run(s, "Medici.label = 'House of Medici'\nAcciaiuoli.label = 'Acciaiuoli\\nbankers'\nfitNodesToLabels()")
    w, h = text_size("House of Medici")
    assert ev(s, "Medici.labelpos") == "inside"
    assert ev(s, "Medici.width") > w and ev(s, "Medici.height") > h
    assert ev(s, "Acciaiuoli.height") > ev(s, "Medici.height")          # two lines
    assert ev(s, "Pazzi.width") < ev(s, "Medici.width")                 # shorter label, narrower


def test_text_width_table():
    w1, h1 = text_size("iiii")
    w2, _ = text_size("WWWW")
    assert w2 > 3 * w1 and h1 == pytest.approx(11.5)
    assert text_size("ab", 2.0)[0] == pytest.approx(2 * text_size("ab")[0])


def test_new_shapes_from_files(s, tmp_path):
    from tests.test_gml_dot import load
    t = load(tmp_path, "s.dot", "graph { a [shape=triangle]; b [shape=diamond]; c [shape=hexagon]; d [shape=octagon]; e [shape=box] }", "makeFromDOT")
    assert [n.style for n in sorted(t.graph._nodes_list(), key=lambda n: n._name)] == [11, 12, 13, 14, 1]
    out = tmp_path / "o.dot"
    assert t.run(f"exportDOT({str(out)!r})")
    text = out.read_text()
    for shape in ("triangle", "diamond", "hexagon", "octagon"):
        assert f'shape="{shape}"' in text
    u = load(tmp_path, "s.gml", 'graph [ node [ id 1 graphics [ type "triangle" ] ] node [ id 2 graphics [ type "diamond" ] ] ]', "makeFromGML")
    assert sorted(n.style for n in u.graph._nodes_list()) == [11, 12]
    run(s, "shapeBy(name)")
    assert set(ev(s, "[n.style for n in g.nodes]")) == {1, 2, 3, 11, 12, 13, 14}


def test_label_placement_options(s, tmp_path):
    run(s, "labelPlacement('particles')\nconstantLabelSize()")
    labels = s.rec.of("overlay")[-1]["labels"]
    assert labels["placement"] == "particles" and labels["screen"] is True
    assert not s.run("labelPlacement('magic')")
    run(s, "optimizeLabels(1.5)")
    assert s.rec.of("labels")[-1] == {"type": "labels", "op": "optimize", "ms": 1500}
    from tests.test_persist import roundtrip
    assert roundtrip(s).view.labels["placement"] == "particles"
    run(s, "undo()")                                         # optimizeLabels changes nothing to undo
    run(s, "undo()")
    assert s.view.labels["placement"] == "candidates" and s.view.labels["screen"] is False


def test_excentric_lens_command(s):
    run(s, "excentricLens(radius=80, autoSize=true, maxLabels=10)")
    assert s.rec.of("lens")[-1] == {"type": "lens", "on": True, "radius": 80.0, "auto": True, "max": 10}
    run(s, "excentricLens(false)")
    assert s.rec.of("lens")[-1] == {"type": "lens", "on": False}
