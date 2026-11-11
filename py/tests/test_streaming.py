"""streamFrom(): Gephi streaming events applied between commands, not undo steps."""
from guess import streaming
from tests.test_gython import s  # noqa: F401  (fixture)


def test_stream_events(s):
    assert s.run("streamFrom('http://localhost:8080/workspace1?operation=getGraph')")
    start = s.rec.of("stream")[-1]
    assert start["op"] == "start" and start["url"].startswith("http://localhost")
    sid = start["id"]
    steps_before = len(s.undo_stack) if hasattr(s, "undo_stack") else None
    n = streaming.apply_batch(s, sid, [
        {"an": {"A": {"label": "Alice", "size": 12, "r": 1, "g": 0, "b": 0, "dept": "sales"}}},
        {"an": {"B": {"x": 10, "y": 20}}},
        {"ae": {"AB": {"source": "A", "target": "B", "directed": True, "weight": 2}}},
        {"ae": {"AC": {"source": "A", "target": "C"}}},          # C is new: created on the fly
        {"cn": {"A": {"dept": "support"}}},
        {"ce": {"AB": {"weight": 5}}},
        {"cn": {"nobody": {"x": 1}}},                             # changing a missing node: ignored
    ])
    assert n == 7
    assert s.run("assert A.label == 'Alice' and A.dept == 'support' and A.width == 12")
    assert s.run("assert A.color == '255,0,0' or A.color.startswith('255,0,0')")
    assert s.run("assert B.y == -20")
    e = s.stream.edges["AB"]
    assert e._directed and e.weight == 5
    assert "C" in s.graph._nodes
    streaming.apply_batch(s, sid, [{"de": {"AB": {}}}, {"dn": {"C": {}}}])
    assert e._id not in s.graph._edges and "C" not in s.graph._nodes and "AC" not in s.stream.edges
    if steps_before is not None:
        assert len(s.undo_stack) == steps_before                 # not undo steps
    assert s.run("stopStream()")
    assert s.rec.of("stream")[-1]["op"] == "stop"
    assert streaming.apply_batch(s, sid, [{"an": {"Z": {}}}]) == 0  # stopped: ignored
    assert not s.run("streamFrom('ftp://x')")
