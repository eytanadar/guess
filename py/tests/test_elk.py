"""ELK layouts, run with the same elkjs as the page (through Node). Skipped
when Node or web/node_modules is missing (e.g. the Python CI job)."""
import pathlib

import pytest

from guess import elk
from tests.test_linked_output import _s

WEB = pathlib.Path(__file__).resolve().parents[2] / "web"
RUNNER = elk.node_runner(WEB)
pytestmark = pytest.mark.skipif(RUNNER is None, reason="needs node and web/node_modules (npm install)")


@pytest.fixture
def s():
    elk._RUNNER[0] = RUNNER
    sess = _s()
    yield sess
    elk._RUNNER[0] = None


def test_layered_puts_edges_downward_and_routes_them(s):
    assert s.run('makeSimpleDirectedRandom(20, 30); remove(feedbackEdges())')
    assert s.run("elkLayout()")
    g = s.ns["g"]
    # direction DOWN: every edge goes from a higher layer to a lower one
    assert all(e.node1.y + e.node1.height / 2 < e.node2.y + e.node2.height / 2 for e in g.edges)
    assert s.run('elkLayout(direction="RIGHT")')
    assert all(e.node1.x + e.node1.width / 2 < e.node2.x + e.node2.width / 2 for e in g.edges)


def test_every_algorithm_runs_and_errors_are_clear(s):
    assert s.run('makeSample("karate")')
    for alg in elk.ALGORITHMS:
        s.rec.clear()
        assert s.run(f'elkLayout("{alg}")'), (alg, s.rec.of("error"))
    pos = [(n.x, n.y) for n in s.ns["g"].nodes]
    assert len(set(pos)) == len(pos)                     # nobody stacked
    s.rec.clear()
    assert not s.run('elkLayout("nope")')
    assert "unknown algorithm" in s.rec.of("error")[0]["summary"]
    s.rec.clear()
    assert not s.run('elkLayout(direction="SIDEWAYS")')
    assert "DOWN" in s.rec.of("error")[0]["summary"]


def test_straight_edges_and_options(s):
    assert s.run('makeSample("karate"); elkLayout()')
    assert len(s.ns["g"].bends) > 0
    assert s.run('elkLayout("stress")')                  # non-layered: straight edges
    assert len(s.ns["g"].bends) == 0
    assert s.run('elkLayout(options={"layered.spacing.nodeNodeBetweenLayers": 120}, route=false)')
    assert len(s.ns["g"].bends) == 0
