"""Graphviz layouts, run with the same WebAssembly Graphviz as the page (through
Node). Skipped when Node or web/node_modules is missing (e.g. the Python CI job)."""
import itertools
import math
import pathlib

import pytest

from guess import Session, gv
from tests.test_gython import Recorder, ev

WEB = pathlib.Path(__file__).resolve().parents[2] / "web"
RUNNER = gv.node_runner(WEB)
pytestmark = pytest.mark.skipif(RUNNER is None, reason="needs node and web/node_modules (npm install)")


@pytest.fixture
def s():
    gv._RUNNER[0] = RUNNER
    rec = Recorder()
    sess = Session(rec)
    sess.rec = rec
    yield sess
    gv._RUNNER[0] = None


def run(s, code):
    s.rec.clear()
    assert s.run(code), s.rec.of("error")


def centres(s):
    return {n._name: (n.x + n.width / 2, n.y + n.height / 2, max(n.width, n.height) / 2)
            for n in s.graph._nodes_list()}


def overlaps(s, slack=0.98):
    c = list(centres(s).values())
    return sum(1 for (x1, y1, r1), (x2, y2, r2) in itertools.combinations(c, 2)
               if math.hypot(x1 - x2, y1 - y2) < (r1 + r2) * slack)


def test_dot_layout_layers_a_dag_and_routes_edges(s):
    run(s, "makeSimpleDirectedRandom(25, 40)\nremove(feedbackEdges())\ndotLayout()")
    c = centres(s)
    for e in s.graph._edges_list():
        assert c[e._n1._name][1] < c[e._n2._name][1], "edges point down"
    long_edges = [e for e in s.graph._edges_list() if abs(c[e._n1._name][1] - c[e._n2._name][1]) > 40]
    assert any(e in s.graph.bends for e in long_edges)
    run(s, "dotLayout(rankdir='LR', route=False)")
    c = centres(s)
    assert all(c[e._n1._name][0] < c[e._n2._name][0] for e in s.graph._edges_list())
    assert not s.graph.bends


def test_dot_clusters_keep_groups_apart(s):
    run(s, "makeSample('karate')\ndotLayout(clusters=club)")
    c = centres(s)
    boxes = {}
    for n in s.graph._nodes_list():
        x, y, r = c[n._name]
        b = boxes.setdefault(n.club, [math.inf, math.inf, -math.inf, -math.inf])
        b[0], b[1], b[2], b[3] = min(b[0], x - r), min(b[1], y - r), max(b[2], x + r), max(b[3], y + r)
    (a0, a1, a2, a3), (b0, b1, b2, b3) = boxes.values()
    assert a2 <= b0 or b2 <= a0 or a3 <= b1 or b3 <= a1, "the two clubs' boxes don't overlap"


def test_force_and_radial_engines(s):
    run(s, "makeSample('karate')")
    for cmd in ["neatoLayout()", "neatoLayout(mode='sgd')", "sfdpLayout()", "fdpLayout(clusters=club)",
                "circoLayout()", "twopiLayout(n0)", "osageLayout(club)", "graphvizLayout('neato', mode='KK')"]:
        run(s, "for n in g.nodes: n.x = 0; n.y = 0")
        run(s, cmd)
        pts = {(round(x), round(y)) for x, y, _r in centres(s).values()}
        assert len(pts) == 34, cmd
    run(s, "neatoLayout()")
    assert overlaps(s) == 0


def test_twopi_puts_the_root_in_the_middle(s):
    run(s, "makeSample('karate')\ntwopiLayout(n0)")
    c = centres(s)
    cx = sum(x for x, _y, _r in c.values()) / len(c)
    cy = sum(y for _x, y, _r in c.values()) / len(c)
    d0 = math.hypot(c["n0"][0] - cx, c["n0"][1] - cy)
    assert d0 < min(math.hypot(x - cx, y - cy) for k, (x, y, _r) in c.items() if k in ("n33", "n32"))


def test_remove_overlap_keeps_the_shape(s):
    run(s, "makeSample('karate')\nneatoLayout()")
    before = centres(s)
    run(s, "for n in g.nodes: n.x = n.x / 5; n.y = n.y / 5")         # squeeze: lots of overlaps
    assert overlaps(s) > 10
    squeezed = centres(s)
    run(s, "removeOverlap()")
    assert overlaps(s) == 0
    after = centres(s)
    # left-to-right order is mostly kept
    names = list(before)
    agree = sum((squeezed[a][0] < squeezed[b][0]) == (after[a][0] < after[b][0])
                for a, b in itertools.combinations(names, 2))
    assert agree / math.comb(len(names), 2) > 0.85
    mx = sum(x for x, _y, _r in after.values()) / 34
    mx0 = sum(x for x, _y, _r in squeezed.values()) / 34
    assert abs(mx - mx0) < 1e-6                                       # stays where it was


def test_fixed_nodes_stay_and_undo(s):
    run(s, "makeSample('karate')\nn0.fixed = true\nn0.x = 500\nn0.y = 500\nneatoLayout()")
    assert ev(s, "(n0.x, n0.y)") == pytest.approx((500, 500), abs=1)
    pos = ev(s, "(n5.x, n5.y)")
    run(s, "sfdpLayout()")
    run(s, "undo()")
    assert ev(s, "(n5.x, n5.y)") == pytest.approx(pos)


def test_needs_graphviz_message(s):
    gv._RUNNER[0] = None
    run(s, "makeSample('karate')")
    assert not s.run("dotLayout()")
    assert "Graphviz loads in the background" in s.rec.of("error")[-1]["text"]
    assert not s.run("graphvizLayout('bogus')")
