import math

from guess import Session
from guess.epidemic import nb_dispersion
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def _path(s, n):
    for i in range(n - 1):
        s.run(f"addEdge(addNode('p{i}'), addNode('p{i + 1}'))")


def test_spread_immune_blocks_the_path():
    s = _s()
    _path(s, 6)
    assert s.run("spread([p0], 'SI', beta=1.0, immune=[p3])"), s.rec.of("error")
    g = s.graph
    assert [g.getNodeByName(f"p{i}").infected_at for i in range(6)] == [0, 1, 2, -1, -1, -1]
    assert g.getNodeByName("p3").state == "V"


def test_spread_weight_scales_the_chance():
    s = _s()
    _path(s, 3)
    s.run("g.edges.weight = 0")
    assert s.run("spread([p0], 'SI', beta=0.9, weight=weight, steps=20)"), s.rec.of("error")
    assert s.graph.getNodeByName("p1").infected_at == -1      # weight 0: no chance at all
    s.run("g.edges.weight = 50")
    assert s.run("spread([p0], 'SI', beta=0.1, weight=weight)")
    assert s.graph.getNodeByName("p2").infected_at == 2       # 1 - 0.9**50: near certain


def test_outbreaks_sizes_and_risk():
    s = _s()
    _path(s, 5)
    assert s.run("__r = outbreaks(20, beta=1.0, gamma=0.0, model='SI', show=False)"), s.rec.of("error")
    r = s.ns["__r"]
    assert list(r) == [5] * 20 and r.mean == 5 and r.large == 1.0
    assert all(n.risk == 1.0 for n in s.graph.nodes)
    # immune node in the middle splits the path; seeds never start on it
    assert s.run("__r = outbreaks(50, beta=1.0, model='SI', immune=[p2], show=False)")
    r = s.ns["__r"]
    assert set(r) == {2}
    assert s.graph.getNodeByName("p2").risk == 0.0
    assert s.run("__r = outbreaks(5, seeds=[p0], beta=1.0, model='SI', immune=[p2], show=False)")
    assert set(s.ns["__r"]) == {2}
    assert "outbreaks:" in repr(s.ns["__r"])
    assert not s.run("outbreaks(5, model='zombie')")


def test_offspring_counts_and_dispersion():
    s = _s()
    s.run("for i in range(10): addNode(f'c{i}')")
    for t in range(1, 6):                      # c0 infects five, c1 infects one, the rest no one
        s.run(f"addDirectedEdge(c0, c{t})")
    s.run("addDirectedEdge(c1, c6)")
    assert s.run("__o = offspring(show=False)"), s.rec.of("error")
    o = s.ns["__o"]
    assert o.R == 0.6 and o.zero == 0.8
    assert o.top20 == 1.0                      # c0 and c1 caused all six
    assert s.graph.getNodeByName("c0").offspring == 5
    assert o.k < 1                             # very uneven
    assert s.run("__o = offspring(outdegree > 0, show=False)")
    assert s.ns["__o"].R == 3.0
    s2 = _s()
    _path(s2, 3)
    assert not s2.run("offspring()")           # undirected: not a transmission tree


def test_nb_dispersion():
    assert nb_dispersion([0, 0, 0]) == float("inf")
    assert nb_dispersion([2, 2, 2, 2]) == float("inf")           # no extra variance: Poisson-like
    assert nb_dispersion([0] * 18 + [10, 10]) < 0.3


def test_effective_distance():
    s = _s()
    s.run("addNodeField('dummy', INTEGER, 0)")
    s.run("a = addNode('a'); b = addNode('b'); c = addNode('c'); d = addNode('d')")
    s.run("e1 = addEdge(a, b); e1.weight = 3")
    s.run("e2 = addEdge(a, c); e2.weight = 1")
    s.run("e3 = addEdge(b, d); e3.weight = 1")
    assert s.run("effectiveDistance(a)"), s.rec.of("error")
    g = s.graph
    get = g.getNodeByName
    assert get("a").eff_distance == 0
    assert math.isclose(get("b").eff_distance, round(1 - math.log(0.75), 4))
    assert math.isclose(get("c").eff_distance, round(1 - math.log(0.25), 4))
    # b sends 3/4 of its traffic back to a, 1/4 to d
    assert math.isclose(get("d").eff_distance, round(1 - math.log(0.75) + 1 - math.log(0.25), 4), abs_tol=1e-3)
    assert sum(1 for e in g.edges if e.eff_tree) == 3
    s.run("addNode('lonely')")
    assert s.run("effectiveDistance(a)")
    assert get("lonely").eff_distance is None
