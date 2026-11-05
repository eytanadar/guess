import json

from guess import Session, persist
from tests.test_gython import Recorder, ev


def chain_session():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    s.run("for nm in ('a', 'b', 'c', 'd'): addNode(nm)\n"
          "addDirectedEdge(a, b); addDirectedEdge(b, c); addDirectedEdge(c, d); long = addDirectedEdge(a, d)")
    return s


def test_sugiyama_bends_route_long_edges():
    s = chain_session()
    s.rec.clear()
    assert s.run("sugiyamaLayout(true)"), s.rec.of("error")
    patches = s.rec.of("patch")
    long = ev(s, "long")
    pts = s.graph.bends[long]
    assert len(pts) == 2                                   # spans 3 levels -> 2 dummies
    ys = [ev(s, "a.y") + 5] + [p[1] for p in pts] + [ev(s, "d.y") + 5]
    assert ys == sorted(ys)                                # route runs downward
    rec = [e for m in patches for e in m["edges"] if e["i"] == long._id][-1]
    assert len(rec["b"]) == 4
    assert all(e not in s.graph.bends for e in s.graph._edges_list() if e is not long)


def test_other_layouts_clear_bends_and_sessions_keep_them():
    s = chain_session()
    s.run("sugiyamaLayout(true)")
    data = json.loads(json.dumps(persist.serialize(s)))
    t = Session(Recorder())
    persist.load(t, data)
    assert len(t.graph.bends) == 1
    s.run("circleLayout()")
    assert s.graph.bends == {}
