"""MINGLE and FDEB edge bundling."""
import numpy as np
import pytest

from guess import Session, bundling
from tests.test_gython import Recorder, ev


def flow(n=200, seed=1):
    """Two clusters with many long edges between them: what bundling is for."""
    rng = np.random.default_rng(seed)
    L = np.c_[rng.normal(100, 40, 40), rng.normal(300, 120, 40)]
    R = np.c_[rng.normal(900, 40, 40), rng.normal(300, 120, 40)]
    return np.array([[*L[a], *R[b]] for a, b in zip(rng.integers(0, 40, n), rng.integers(0, 40, n))])


def ink(paths):
    """Total drawn length, counting shared segments once."""
    segs = set()
    for p in paths:
        for a, b in zip(p, p[1:]):
            segs.add((tuple(np.round(a, 3)), tuple(np.round(b, 3))))
    return sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)


def test_mingle_saves_ink_and_keeps_ends():
    E = flow()
    paths = bundling.mingle(E)
    assert len(paths) == len(E)
    for e, p in zip(E, paths):
        assert p[0] == pytest.approx(tuple(e[:2])) and p[-1] == pytest.approx(tuple(e[2:]))
    straight = np.hypot(E[:, 2] - E[:, 0], E[:, 3] - E[:, 1]).sum()
    assert ink(paths) < 0.6 * straight
    assert max(len(p) for p in paths) >= 6                    # several levels of bundles


def test_fdeb_pulls_compatible_edges_together():
    E = flow()
    paths = bundling.fdeb(E)
    mids = np.array([p[len(p) // 2] for p in paths])
    straight = (E[:, 1] + E[:, 3]) / 2
    assert mids[:, 1].std() < 0.3 * straight.std()
    for e, p in zip(E, paths):
        assert p[0] == pytest.approx(tuple(e[:2])) and p[-1] == pytest.approx(tuple(e[2:]))
    # perpendicular edges are not compatible: they stay straight
    X = np.array([[0, 0, 100, 0], [50, -50, 50, 50]], float)
    for e, p in zip(X, bundling.fdeb(X)):
        assert np.allclose(np.array(p)[:, 1 if e[1] == e[3] else 0], e[1] if e[1] == e[3] else e[0])


def test_bundle_edges_command_sets_and_clears_bends():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    E = flow(120)
    code = ["newGraph('flow')"]
    for i in range(40):
        code.append(f"addNode('l{i}', x={E[i % len(E), 0]}, y={E[i % len(E), 1]})")
        code.append(f"addNode('r{i}', x={E[i % len(E), 2]}, y={E[i % len(E), 3]})")
    rng = np.random.default_rng(3)
    for a, b in zip(rng.integers(0, 40, 150), rng.integers(0, 40, 150)):
        code.append(f"addEdge(l{a}, r{b})")
    assert s.run("\n".join(code)), rec.of("error")
    for cmd in ("bundleEdges()", "bundleEdges(method='fdeb')", "bundleEdges(method='fdeb', strength=0.5)"):
        assert s.run(cmd), rec.of("error")
        assert len(s.graph.bends) > 100, cmd
    assert s.run("unbundleEdges()") and not s.graph.bends
    assert not s.run("bundleEdges(method='nope')")
    # bundling by groups still works as before
    assert s.run("addNodeField('side', VARCHAR, 'l')\nfor n in g.nodes: n.side = n.name[0]\nbundleEdges(side)")
    assert len(s.graph.bends) > 100
    assert ev(s, "len(g.edges)") > 0
