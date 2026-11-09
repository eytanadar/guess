"""Undo / redo of commands, node drags, history()."""
from tests.test_gython import ev, s  # noqa: F401  (fixture)


def names(sess):
    return sorted(n._name for n in sess.graph._nodes_list())


def test_undo_values_structure_and_fields(s):
    assert s.run("bob.color = red; alice.size = 30")
    assert s.run("remove(jane)")
    assert s.run("addNodeField('score', DOUBLE, 1); bob.score = 5")
    assert s.run("addNode('zed'); addEdge(zed, bob)")
    assert names(s) == ["al_x", "alice", "bob", "zed"]
    s.run("undo()")
    assert names(s) == ["al_x", "alice", "bob"] and "zed" not in s.ns
    s.run("undo()")
    assert "score" not in s.graph.node_schema and "score" not in s.ns
    s.run("undo()")
    assert names(s) == ["al_x", "alice", "bob", "jane"] and len(s.graph._edges) == 4
    assert ev(s, "jane") is s.graph._nodes["jane"] and len(ev(s, "g.deleted")) == 0
    s.run("undo()")
    assert ev(s, "(bob.color, alice.width)") == ("cornflowerblue", 10)
    s.run("redo()")
    s.run("redo()")
    assert ev(s, "bob.color") == "red" and "jane" not in names(s)
    s.run("bob.color = blue")           # a new command clears the redo stack
    s.rec.clear()
    s.run("redo()")
    assert "nothing to redo" in "".join(m["text"] for m in s.rec.of("text"))


def test_queries_and_prints_are_not_undo_steps(s):
    s.run("bob.color = red")
    s.run("print(bob.color); dept == 'IT'; help(colorize)")
    s.run("undo()")
    assert ev(s, "bob.color") == "cornflowerblue"


def test_undo_layout_view_states_and_load(s, tmp_path):
    before = ev(s, "(bob.x, bob.y)")
    s.run("circleLayout()")
    assert ev(s, "(bob.x, bob.y)") != before
    s.run("undo()")
    assert ev(s, "(bob.x, bob.y)") == before
    s.run("curvedEdges(); createConvexHull(dept == 'IT'); ss('a')")
    assert s.view.curvature and s.view.hulls and "a" in s.graph.states
    s.run("undo()")
    assert not s.view.curvature and not s.view.hulls and "a" not in s.graph.states
    s.run("makeSimpleRandom(20, 30)")
    assert len(s.graph._nodes) == 20
    s.run("undo()")
    assert names(s) == ["al_x", "alice", "bob", "jane"] and ev(s, "bob.dept") == "IT"


def test_node_drags_are_one_undo_step(s):
    b, a = ev(s, "bob"), ev(s, "alice")
    # what the display submits (as a hidden console cell) when a selection is dragged
    s.run("bob.x = 1.0; bob.y = 2.0\nalice.x = 3.0; alice.y = 4.0")
    assert (b.x, a.y) == (1.0, 4.0)
    s.run("undo()")
    assert (b.x, a.y) != (1.0, 4.0)


def test_history_lists_every_command(s, tmp_path):
    s.run("bob.color = red")
    s.run("bob.color = red")
    s.rec.clear()
    s.run("history()")
    text = "".join(m["text"] for m in s.rec.of("text"))
    assert text.count("bob.color = red") == 2 and "] history()" in text
    f = tmp_path / "h.py"
    s.run(f"saveHistory({str(f)!r})")
    assert f.read_text().count("bob.color = red") == 2


def test_print_links_graph_objects(s):
    s.rec.clear()
    s.run("for n in (dept == 'IT'):\n    print('node', n)")
    outs = s.rec.of("out")
    assert len(outs) == 2 and outs[0]["segs"][2] == {"n": ev(s, "bob")._id, "t": "bob"}
    s.rec.clear()
    s.run("print('plain', 3)")
    assert not s.rec.of("out") and "plain 3" in "".join(m["text"] for m in s.rec.of("text"))
