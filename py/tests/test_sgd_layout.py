"""sgdLayout: stress layout by stochastic gradient descent (the s_gd2 method)."""
import numpy as np

from guess.layouts import _round_robin
from tests.test_linked_output import _s


def _stress(s, length=40.0):
    """Normalised stress of the current layout against hop distances."""
    g = s.ns["g"]
    nodes = list(g.nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    adj = [[] for _ in nodes]
    for e in g.edges:
        a, b = idx[e.node1], idx[e.node2]
        adj[a].append(b)
        adj[b].append(a)
    X = np.array([[n.x, n.y] for n in nodes])
    num = den = 0.0
    for src in range(len(nodes)):
        dist = {src: 0}
        q = [src]
        for u in q:
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        for t, d in dist.items():
            if t > src:
                e = np.hypot(*(X[src] - X[t])) / length
                num += (e - d) ** 2 / d ** 2
                den += 1
    return num / den


def test_round_robin_visits_every_pair_once():
    for k in (2, 5, 6, 9):
        A, B = _round_robin(k)
        pairs = [tuple(sorted((a, b))) for ra, rb in zip(A, B) for a, b in zip(ra, rb) if a >= 0 and b >= 0]
        assert len(pairs) == len(set(pairs)) == k * (k - 1) // 2
        for ra, rb in zip(A, B):                 # a round never uses a node twice
            used = [x for x in np.concatenate([ra, rb]) if x >= 0]
            assert len(used) == len(set(used))


def test_sgd_layout_lowers_stress_and_is_repeatable():
    s = _s()
    assert s.run('makeSample("lesmis")')
    assert s.run("randomLayout()")
    before = _stress(s)
    assert s.run("sgdLayout()")
    after = _stress(s)
    assert after < 0.15 and after < before / 3, (before, after)
    first = [(n.x, n.y) for n in s.ns["g"].nodes]
    assert s.run("randomLayout(); sgdLayout()")
    assert [(n.x, n.y) for n in s.ns["g"].nodes] == first   # seeded: same result


def test_sgd_layout_options_and_errors():
    s = _s()
    assert s.run('makeSample("lesmis")')
    assert s.run("Valjean.fixed = true; __p = (Valjean.x, Valjean.y)")
    assert s.run("sgdLayout(iterations=10, weight=weight, seed=2)")
    assert (s.ns["Valjean"].x, s.ns["Valjean"].y) == s.ns["__p"]          # pinned nodes stay put
    s.rec.clear()
    assert not s.run("sgdLayout(weight=x)")
    assert "edge field" in s.rec.of("error")[0]["summary"]
    assert s.run("sgdLayout()")          # the sample graph has several components: packed
