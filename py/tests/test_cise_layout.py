"""ciseLayout: CiSE circular spring embedder for clustered graphs (port of cytoscape.js-cise)."""
import numpy as np

from tests.test_linked_output import _s


def _centres(s):
    ns = list(s.ns["g"].nodes)
    return ns, np.array([[n.x + n.width / 2, n.y + n.height / 2] for n in ns])


def _circles(s, field):
    """Per cluster value: (centre, mean radius, radius spread, member indices)."""
    ns, X = _centres(s)
    vals = [getattr(n, field) for n in ns]
    out = {}
    for v in set(vals) - {None}:
        idx = [i for i, x in enumerate(vals) if x == v]
        c = X[idx].mean(0)
        r = np.hypot(*(X[idx] - c).T)
        out[v] = (c, r.mean(), r.std(), idx)
    return out


def _check_circles(s, field):
    circ = _circles(s, field)
    assert len(circ) > 1
    for c, r, spread, idx in circ.values():
        if len(idx) > 2:
            assert spread < 1e-6 * max(r, 1)           # on a circle round their centroid
    keys = list(circ)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            ca, ra, _, _ = circ[keys[a]]
            cb, rb, _, _ = circ[keys[b]]
            assert np.hypot(*(ca - cb)) > ra + rb       # circles don't overlap
    return circ


def test_cise_clusters_on_separate_circles_and_repeatable():
    s = _s()
    assert s.run("ciseLayout(dept)"), s.rec.of("error")
    _check_circles(s, "dept")
    first = [(n.x, n.y) for n in s.ns["g"].nodes]
    assert s.run("randomLayout(); ciseLayout(dept)")
    assert [(n.x, n.y) for n in s.ns["g"].nodes] == first      # seeded: repeatable
    assert s.run('randomLayout(); ciseLayout("dept")')             # by name
    assert [(n.x, n.y) for n in s.ns["g"].nodes] == first


def test_cise_groups_and_unclustered_nodes():
    s = _s()
    assert s.run('makeSample("lesmis")')
    assert s.run("__c = louvainClusters(); ciseLayout(__c)"), s.rec.of("error")
    _check_circles(s, "louvain_class")
    assert s.run("randomLayout(); ciseLayout(groupBy(louvain_class))")
    _check_circles(s, "louvain_class")
    # nodes without a value are free nodes, still placed away from the circles
    assert s.run("addNodeField('part', VARCHAR, None)\n"
                 "for n in g.nodes: n.part = None if n.louvain_class == 0 else str(n.louvain_class)\n"
                 "randomLayout(); ciseLayout(part)"), s.rec.of("error")
    circ = _check_circles(s, "part")
    ns, X = _centres(s)
    free = [i for i, n in enumerate(ns) if n.part is None]
    assert free and np.isfinite(X[free]).all()
    for c, r, _, idx in circ.values():
        assert (np.hypot(*(X[free] - c).T) > r - 1).all()    # not inside any circle


def test_cise_pins_and_inner_nodes():
    s = _s()
    assert s.run('makeSample("lesmis"); louvainClusters(); Valjean.fixed = true; __p = (Valjean.x, Valjean.y)')
    assert s.run("ciseLayout(louvain_class)"), s.rec.of("error")
    assert (s.ns["Valjean"].x, s.ns["Valjean"].y) == s.ns["__p"]
    assert s.run("Valjean.fixed = false; ciseLayout(louvain_class, allowNodesInsideCircle=true, "
                 "maxRatioOfNodesInsideCircle=0.3)"), s.rec.of("error")
    _, X = _centres(s)
    assert np.isfinite(X).all()


def test_avsdf_order_reduces_crossings():
    from guess.ciselayout import _avsdf, _chord_crossings
    rng = np.random.default_rng(3)
    m = 14
    # two dense halves joined by a couple of edges: a random order crosses a lot
    pairs = {(a, b) for a in range(m) for b in range(a + 1, m)
             if (a < 7) == (b < 7) and rng.random() < 0.5} | {(0, 7), (6, 13)}
    ea, eb = np.array(sorted(pairs)).T

    def total(order):
        pos = np.empty(m, np.intp)
        pos[order] = np.arange(m)
        return _chord_crossings(pos[ea], pos[eb], pos[ea], pos[eb], m) / 2

    order, ang, r = _avsdf(m, ea, eb, np.full(m, 14.0), 12.5)
    assert sorted(order) == list(range(m)) and r > 0
    assert np.all(np.diff(ang[order]) > 0)                    # angles follow the order
    rand = np.mean([total(rng.permutation(m)) for _ in range(50)])
    assert total(order) < rand / 2


def test_cise_bad_args():
    s = _s()
    s.rec.clear()
    assert not s.run("ciseLayout('nosuchfield')")
    assert "nosuchfield" in s.rec.of("error")[0]["summary"]
