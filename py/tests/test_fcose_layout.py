"""fcoseLayout: spectral draft + CoSE spring embedder (port of cytoscape.js-fcose)."""
import numpy as np

from tests.test_linked_output import _s
from tests.test_sgd_layout import _stress


def _overlaps(s):
    ns = list(s.ns["g"].nodes)
    X = np.array([[n.x + n.width / 2, n.y + n.height / 2] for n in ns])
    W = np.array([[n.width / 2, n.height / 2] for n in ns])
    i, j = np.triu_indices(len(ns), 1)
    return int((((np.abs(X[i] - X[j]) - (W[i] + W[j])) < 0).all(1)).sum())


def test_fcose_lays_out_without_overlaps_and_beats_random():
    s = _s()
    assert s.run('makeSample("lesmis")')
    assert s.run("randomLayout()")
    before = _stress(s, 60)
    assert s.run("fcoseLayout()")
    assert _stress(s, 60) < before / 2
    assert _overlaps(s) == 0
    first = [(n.x, n.y) for n in s.ns["g"].nodes]
    assert s.run("randomLayout(); fcoseLayout()")
    assert [(n.x, n.y) for n in s.ns["g"].nodes] == first        # seeded: repeatable


def test_fcose_quality_pins_and_components():
    s = _s()
    assert s.run('fcoseLayout(quality="draft")')                 # sample graph: many components
    assert s.run('fcoseLayout(quality="proof", idealEdgeLength=80)')
    assert s.run('makeSample("lesmis"); Valjean.fixed = true; __p = (Valjean.x, Valjean.y)')
    assert s.run("fcoseLayout()")
    assert (s.ns["Valjean"].x, s.ns["Valjean"].y) == s.ns["__p"]
    s.rec.clear()
    assert not s.run('fcoseLayout(quality="best")')
    assert "draft" in s.rec.of("error")[0]["summary"]


def test_overlap_separation_matches_cose_base():
    from guess.layouts import _separation
    # b overlaps a from the right by 4 (half sizes 5): pushed right by 4/2 + buffer, slope 0
    f = _separation(np.array([[0.0, 0.0]]), np.array([[6.0, 0.0]]), np.full((1, 2), 5.0), np.full((1, 2), 5.0), 25)
    assert f[0, 0] == 4 / 2 + 25 and f[0, 1] == -25.0     # level centres: direction 1, so -buffer
    # same centre: slope 1, pushed diagonally
    f = _separation(np.zeros((1, 2)), np.zeros((1, 2)), np.full((1, 2), 5.0), np.full((1, 2), 5.0), 25)
    assert f[0, 0] == f[0, 1] == -(10 / 2 + 25)
