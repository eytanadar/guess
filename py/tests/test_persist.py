import json

from guess import Session, persist
from tests.test_gython import Recorder, ev, names, s  # noqa: F401


def roundtrip(sess):
    data = json.loads(json.dumps(persist.serialize(sess)))
    rec = Recorder()
    t = Session(rec)
    t.rec = rec
    persist.load(t, data)
    return t


def test_roundtrip_everything(s):
    s.run("addNodeField('score', DOUBLE, 1.5)\nbob.score = 9\nbob.color = red\n(bob<->alice).width = 4")
    s.run("ss(1999)\nbob.jobfunc = 'CEO'\nremove(jane)\naddRange(alice, '1-5')")
    s.run("h = createConvexHull((bob, alice), randomColor(100))\nl = Legend()\nl.add(bob, 'boss')")
    s.run("setDisplayBackground(lightyellow)")
    t = roundtrip(s)
    assert ev(t, "bob.score") == 9 and ev(t, "alice.score") == 1.5
    assert ev(t, "bob.color") == "red" and ev(t, "(bob<->alice).width") == 4
    assert "jane" not in t.ns and len(ev(t, "g.deleted")) == 4
    assert ev(t, "bob[1999].jobfunc") == "Manager" and ev(t, "bob.jobfunc") == "CEO"
    t.run("ls(1999)")
    assert "jane" in t.ns and len(t.graph.edges) == 4
    assert names(ev(t, "Node rcontains 3")) == ["alice"]
    ov = t.rec.of("overlay")[-1] if t.rec.of("overlay") else None
    t.rec.clear()
    t.scene()
    ov = t.rec.of("overlay")[-1]
    assert len(ov["hulls"]) == 1 and ov["legends"][0]["entries"][0]["t"] == "boss"
    assert ov["background"] == 0xFCFCCA


def test_app_script_runs_on_load(s, tmp_path):
    (tmp_path / "ui.py").write_text("ui.dock(Panel('App', Label('hello')))\nbob.color = green\n")
    s.run(f"exportApp({str(tmp_path / 'app.guess')!r}, {str(tmp_path / 'ui.py')!r})")
    data = json.loads((tmp_path / "app.guess").read_text())
    assert data["app"] is True and "ui.dock" in data["script"]
    rec = Recorder()
    t = Session(rec)
    t.rec = rec
    assert t.run(f"makeFromSession({str(tmp_path / 'app.guess')!r})"), rec.of("error")
    assert any(m["type"] == "ui" and m["op"] == "dock" for m in rec.msgs)
    assert ev(t, "bob.color") == "green"


def test_curved_edges_setting(s):
    s.run("curvedEdges()")
    assert s.view.curvature == 1.2
    s.run("curvedEdges(0.6)")
    s.flush()
    ov = [m for m in s.rec.of("overlay")][-1]
    assert ov["curvature"] == 0.6
    assert roundtrip(s).view.curvature == 0.6
    s.run("curvedEdges(false)")
    assert s.view.curvature == 0
    assert not s.run("curvedEdges(5)")
    s.run('setEdgeColorMode("mixed")')
    assert roundtrip(s).view.edge_color == "mixed"
    assert not s.run('setEdgeColorMode("rainbow")')
