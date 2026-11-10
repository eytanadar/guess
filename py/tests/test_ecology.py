from guess import Session
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def _chain(s):
    # grass -> rabbit -> fox; grass -> deer; fox also eats deer
    for a, b in (("grass", "rabbit"), ("rabbit", "fox"), ("grass", "deer"), ("deer", "fox")):
        s.run(f"addDirectedEdge(addNode({a!r}), addNode({b!r}))")


def test_trophic_levels():
    s = _s()
    _chain(s)
    s.run("addDirectedEdge(rabbit, addNode('hawk'))")
    s.run("addDirectedEdge(fox, hawk)")
    assert s.run("trophicLevels()"), s.rec.of("error")
    g = s.graph
    tl = {n.name: round(n.trophic, 3) for n in g.nodes}
    assert tl == {"grass": 1.0, "rabbit": 2.0, "deer": 2.0, "fox": 3.0, "hawk": 3.5}
    assert g.getNodeByName("hawk").omnivory == 0.5 and g.getNodeByName("fox").omnivory == 0.0
    roles = {n.name: n.role for n in g.nodes}
    assert roles["grass"] == "basal" and roles["hawk"] == "top" and roles["fox"] == "intermediate"


def test_extinction_cascade():
    s = _s()
    _chain(s)
    assert s.run("__r = extinctions(['basal', 'least'], show=False)")
    r = s.ns["__r"]
    # losing the grass starves everything: 1 removal, everyone gone
    assert r["basal"][1] == (0.25, 0.0)
    # removing the fox first (least connected? fox has 2, rabbit 2, deer 2, grass 2: ties by order)
    assert r["least"][-1] == (1.0, 0.0)


def test_niche_model_reproducible():
    s = _s()
    assert s.run("makeNicheModel(25, 0.15, seed=3)")
    first = sorted((e._n1.name, e._n2.name) for e in s.graph.edges)
    assert s.run("makeNicheModel(25, 0.15, seed=3)")
    assert sorted((e._n1.name, e._n2.name) for e in s.graph.edges) == first
    # food is lower in the niche than its eater... except the range can reach above
    assert all(n.degree > 0 for n in s.graph.nodes)
    s.rec.clear()
    assert not s.run("makeNicheModel(2, 0.1)")


def test_nestedness():
    s = _s()
    s.run("addNodeField('kind', VARCHAR, None)")
    # perfectly nested: plant p1 visited by a1..a3, p2 by a1..a2, p3 by a1
    for i in (1, 2, 3):
        s.run(f"addNode('p{i}').kind = 'plant'")
        s.run(f"addNode('a{i}').kind = 'animal'")
    for p, animals in (("p1", (1, 2, 3)), ("p2", (1, 2)), ("p3", (1,))):
        for a in animals:
            s.run(f"addEdge({p}, a{a})")
    assert s.run("__n = nestedness(kind, rows='plant')")
    assert s.ns["__n"] == (100.0, 100.0, 100.0)


def test_rewire_keep_preserves_two_mode():
    s = _s()
    s.run("addNodeField('kind', VARCHAR, None)")
    import random
    rng = random.Random(1)
    for i in range(10):
        s.run(f"addNode('p{i}').kind = 'plant'")
        s.run(f"addNode('a{i}').kind = 'animal'")
    for i in range(10):
        for j in range(10):
            if rng.random() < 0.3:
                s.run(f"addEdge(p{i}, a{j})")
    degrees = sorted((n.name, n.degree) for n in s.graph.nodes)
    assert s.run("rewire(keep=kind, seed=2)"), s.rec.of("error")
    g = s.graph
    assert all(e._n1.kind != e._n2.kind for e in g.edges)
    assert sorted((n.name, n.degree) for n in g.nodes) == degrees
    s.rec.clear()
    assert not s.run("use('main'); rewire(keep='nosuch')")
