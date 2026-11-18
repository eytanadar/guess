"""colaLayout: port of WebCola (stress majorization + VPSC projection)."""
import time

import numpy as np

from guess.colalayout import _VPSC, _overlap_constraints, _scc
from tests.test_fcose_layout import _overlaps
from tests.test_linked_output import _s
from tests.test_sgd_layout import _stress


def _xy(s):
    return [(n.x, n.y) for n in s.ns["g"].nodes]


def test_vpsc_solves_separation_and_equality_constraints():
    # three variables all wanting 0: x0 + 2 <= x1, x1 + 2 <= x2 -> -2, 0, 2
    v = _VPSC(np.zeros(3), np.ones(3), [0, 1], [1, 2], [2.0, 2.0], [False, False])
    v.solve()
    assert np.allclose(v.positions(), [-2, 0, 2])
    v = _VPSC(np.array([0.0, 5.0]), np.ones(2), [0], [1], [1.0], [True])
    v.solve()
    assert np.allclose(v.positions(), [2, 3])           # equality pulls both together
    # a cycle of constraints is marked unsatisfiable instead of looping
    v = _VPSC(np.zeros(2), np.ones(2), [0, 1], [1, 0], [1.0, 1.0], [False, False])
    v.solve()
    assert v.unsat.any()


def test_overlap_constraints_and_scc():
    cx, cy = np.array([0.0, 5.0, 100.0]), np.zeros(3)
    w = h = np.full(3, 10.0)
    cs = _overlap_constraints(cx, cy, w, h, 0)
    assert (0, 1, 10 + 1e-6, False) in cs
    assert _scc(4, [0, 1, 2], [1, 0, 3])[0] == _scc(4, [0, 1, 2], [1, 0, 3])[1]


def test_cola_lowers_stress_without_overlaps_and_is_repeatable():
    s = _s()
    assert s.run('makeSample("lesmis")')
    assert s.run("randomLayout()")
    before = _stress(s, 100)
    assert s.run("colaLayout(maxSimulationTime=None)")
    after = _stress(s, 100)
    assert after < 0.35 and after < before / 5, (before, after)
    assert _overlaps(s) == 0
    assert s.run("colaLayout(randomize=true, seed=3, maxSimulationTime=None, iterations=40)")
    first = _xy(s)
    assert s.run("colaLayout(randomize=true, seed=3, maxSimulationTime=None, iterations=40)")
    assert _xy(s) == first


def test_cola_flow_puts_targets_below_sources():
    s = _s()
    assert s.run("makeSimpleDirectedRandom(20, 30); remove(feedbackEdges())")
    assert s.run('colaLayout(flow="y", flowSeparation=40, maxSimulationTime=None, iterations=100)')
    g = s.ns["g"]
    for e in g.edges:
        a, b = e.node1, e.node2
        assert (b.y + b.height / 2) - (a.y + a.height / 2) >= 40 - 1e-6
    assert _overlaps(s) == 0


def test_cola_pins_constraints_and_options():
    s = _s()
    assert s.run('makeSample("lesmis"); Valjean.fixed = true; __p = (Valjean.x, Valjean.y)')
    assert s.run("colaLayout(maxSimulationTime=None, iterations=50)")
    assert (s.ns["Valjean"].x, s.ns["Valjean"].y) == s.ns["__p"]
    assert s.run('Valjean.fixed = false')
    assert s.run('colaLayout(alignment={"vertical": [[Javert, Cosette, Marius]]}, '
                 'gapInequalities=[{"axis": "x", "left": Javert, "right": Fantine, "gap": 80}], '
                 'maxSimulationTime=None, iterations=50)')
    ns = s.ns
    cx = lambda n: n.x + n.width / 2
    assert abs(cx(ns["Javert"]) - cx(ns["Cosette"])) < 1e-3
    assert abs(cx(ns["Javert"]) - cx(ns["Marius"])) < 1e-3
    assert cx(ns["Fantine"]) - cx(ns["Javert"]) >= 80 - 1e-3
    assert s.run("colaLayout(edgeSymDiffLength=30, avoidOverlap=false, iterations=20)")
    assert s.run("colaLayout(edgeLength=weight, iterations=20)")
    s.rec.clear()
    assert not s.run('colaLayout(flow="z")')
    assert "flow" in s.rec.of("error")[0]["summary"]


def test_cola_sample_graph_runs_in_reasonable_time():
    s = _s()                                    # 402 nodes, many components
    t = time.monotonic()
    assert s.run("colaLayout()")                # default: stops after 4 s
    assert time.monotonic() - t < 8
    assert _overlaps(s) == 0
    assert all(np.isfinite(_xy(s)).ravel())
