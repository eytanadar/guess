"""Layouts that keep running between cells (continuous=true), stepped by a timer."""
from tests.test_linked_output import _s


def _pos(s):
    return [(n.x, n.y) for n in s.ns["g"].nodes]


def _loop_timer(s):
    return s._layouts.looping["timer"]._id


def test_forceatlas2_runs_between_cells_without_undo_steps_and_stops():
    s = _s()
    undo = len(s.undo_stack)
    assert s.run("forceAtlas2Layout(continuous=true)")
    tid = _loop_timer(s)
    before = _pos(s)
    for _ in range(3):
        assert s.dispatch(tid, "fire")
    moved = _pos(s)
    assert moved != before
    assert len(s.undo_stack) == undo                   # ticks add no undo steps (nor does starting it)
    # a change from elsewhere: the layout carries on from there
    assert s.run("v1.x = 5000")
    s.dispatch(tid, "fire")
    assert s.ns["v1"].x != 5000
    assert s.run("stopLayout()")
    assert s._layouts.looping is None
    held = _pos(s)
    assert not s.dispatch(tid, "fire")                  # the timer is gone
    assert _pos(s) == held
    s.rec.clear()
    assert s.run("stopLayout()")
    assert "no layout" in "".join(m.get("text", "") for m in s.rec.of("text"))


def test_every_spring_layout_can_loop_and_another_layout_stops_it():
    s = _s()
    for call in ("frLayout(continuous=true)", "springLayout(continuous=true)",
                 "weightedSpringLayout(5, 50, continuous=true)", "physicsLayout(continuous=true)"):
        assert s.run(call), call
        before = _pos(s)
        s.dispatch(_loop_timer(s), "fire")
        assert _pos(s) != before, call
    tid = _loop_timer(s)
    assert s.run("circleLayout()")                     # any other layout ends the loop
    assert s._layouts.looping is None
    assert not s.dispatch(tid, "fire")
    s.rec.clear()
    assert not s.run("forceAtlas2Layout(gravitySources=[], continuous=true)")   # fails up front
    assert s._layouts.looping is None


def test_layouts_from_other_modules_stop_the_loop_too():
    from guess.layouts import _Layouts
    s = _s()
    assert s.run("forceAtlas2Layout(continuous=true)")
    other = _Layouts(s)          # as Graphviz, ELK and igraph build their own
    other.snap()
    assert s._layouts.looping is None


def test_a_dragged_node_is_held_where_the_pointer_is_until_released():
    s = _s()
    assert s.run("forceAtlas2Layout(continuous=true)")
    tid = _loop_timer(s)
    v1 = s.ns["v1"]
    start = (v1.x, v1.y)
    nbr = v1.getNeighbors()[0]
    d0 = abs(nbr.x - 3000)
    s.hold_nodes([v1._id, 3000.0, 3000.0], False)       # dragging v1 far out
    for _ in range(6):
        s.dispatch(tid, "fire")
    assert (v1.x, v1.y) == start                         # the layout doesn't move the held node...
    assert abs(nbr.x - 3000) < d0                        # ...and its neighbours feel it where it's held
    s.hold_nodes([v1._id, 3000.0, 3000.0], True)        # released there
    assert (v1.x, v1.y) == (3000.0, 3000.0)
    undo = len(s.undo_stack)
    s.dispatch(tid, "fire")
    assert (v1.x, v1.y) != (3000.0, 3000.0)              # free again: the layout moves it on from there
    assert len(s.undo_stack) == undo
