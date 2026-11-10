from guess import Session
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def _ev(s, expr):
    assert s.run(f"__r = ({expr})"), s.rec.of("error")
    return s.ns["__r"]


def test_computed_fields_follow_the_graph():
    s = _s()
    for a, b in (("a", "b"), ("b", "c"), ("d", "e")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert _ev(s, "len(component.distinct)") == 2
    assert _ev(s, "b.betweenness") == 1.0
    # several edits in a row, then one read: recomputed once, correctly
    s.run("addEdge(c, d)")
    s.run("addEdge(e, addNode('f'))")
    assert _ev(s, "len(component.distinct)") == 1
    assert _ev(s, "c.betweenness") > 1.0
    s.run("remove(c)")
    assert _ev(s, "sorted(len(grp) for grp in groupBy(component))") == [2, 3]
    assert _ev(s, "b.betweenness") == 0.0
    # undo restores the structure, and the fields follow
    s.run("undo()")
    assert _ev(s, "len(component.distinct)") == 1


def test_queries_and_weights_refresh():
    s = _s()
    for a, b in (("a", "b"), ("b", "c")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert len(_ev(s, "strength > 1")) == 1             # b
    s.run("(a <-> b).weight = 5")
    assert sorted(n.name for n in _ev(s, "strength > 1")) == ["a", "b"]


def test_user_assignment_wins_until_recompute():
    s = _s()
    for a, b in (("a", "b"), ("b", "c")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert _ev(s, "b.betweenness") == 1.0
    s.run("b.betweenness = 42")
    s.run("addEdge(a, c)")
    assert _ev(s, "b.betweenness") == 42                # the user's value stays
    s.run("recompute(betweenness)")
    assert _ev(s, "b.betweenness") == 0.0
    s.run("remove(a <-> c)")
    assert _ev(s, "b.betweenness") == 1.0               # following the graph again


def test_copies_start_stale():
    s = _s()
    for a, b in (("a", "b"), ("b", "c"), ("c", "d")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert _ev(s, "len(component.distinct)") == 1
    # a subgraph without the middle edge: its copied `component` is recomputed on read
    s.run("subgraph((a <-> b) | (c <-> d), 'parts')")
    assert _ev(s, "len(component.distinct)") == 2
