from guess import Session
from guess.investigate import normalize_name
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def test_normalize_name():
    assert normalize_name("Acme Ltd.") == normalize_name("ACME") == "acme"
    assert normalize_name("Smith, John") == normalize_name("john smith")
    assert normalize_name("Dr. José Núñez") == normalize_name("Nunez Jose")


def test_find_duplicates_and_merge():
    s = _s()
    s.run("addNodeField('phone', VARCHAR, None)")
    for name, label in (("a", "John Smith"), ("b", "Smith, John"), ("c", "Jane Doe"), ("x", "Bank"), ("y", "Shop")):
        s.run(f"addNode({name!r}).label = {label!r}")
    s.run("c.phone = '555'")
    s.run("addEdge(a, x).weight = 2")
    s.run("addEdge(b, x).weight = 3")        # parallel after merging: weights add
    s.run("addEdge(b, y)")
    s.run("addEdge(a, b)")                   # inside the group: disappears
    assert s.run("__p = findDuplicates(label, threshold=0.9)")
    pairs = s.ns["__p"]
    assert [(p[0].name, p[1].name, p[2]) for p in pairs] == [("a", "b", 1.0)]
    assert s.run("mergeNodes(__p)"), s.rec.of("error")
    g = s.graph
    assert sorted(n.name for n in g.nodes) == ["a", "c", "x", "y"]
    a = g.getNodeByName("a")
    assert a.merged == 2 and a.aliases == "b; Smith, John"
    w = {e._n2.name if e._n1 is a else e._n1.name: e.weight for e in a._inc.values()}
    assert w == {"x": 5.0, "y": 1.0}
    assert s.run("undo()") and len(s.graph.nodes) == 5
    s.run("c.phone = '555'")
    assert s.run("mergeNodes(a, c, name='c')")
    assert s.graph.getNodeByName("c").merged == 2 and s.graph.getNodeByName("c").phone == "555"
    s.rec.clear()
    assert not s.run("mergeNodes(x)")


def test_group_stats_and_cycles():
    s = _s()
    s.run("addNodeField('grp', VARCHAR, None)")
    for n, grp in (("a", "one"), ("b", "one"), ("c", "one"), ("d", "two"), ("e", "two")):
        s.run(f"addNode({n!r}).grp = {grp!r}")
    for x, y in (("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "e")):
        s.run(f"addDirectedEdge({x}, {y})")
    assert s.run("__r = groupStats(grp)")
    one = s.ns["__r"][0]
    assert (one["group"], one["size"], one["internal"], one["boundary"]) == ("one", 3, 3, 1)
    assert one["density"] == 1.0 and abs(one["conductance"] - 1 / 7) < 1e-12
    assert s.run("__c = findCycles(3)")
    cyc = s.ns["__c"]
    assert len(cyc) == 1 and sorted(x.name for x in cyc[0] if hasattr(x, "_inc")) == ["a", "b", "c"]
    assert s.run("__c = findCycles(2)") and len(s.ns["__c"]) == 0
