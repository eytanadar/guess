"""Query semantics that plain Python gets wrong for sets: chained comparisons,
and/or/not, `in`, plus value summaries and highest/lowest."""
from pathlib import Path

from guess import Session
from tests.test_gython import Recorder

SAMPLE = Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    return s


def ev(s, code):
    assert s.run(f"__r = {code}"), s.rec.of("error")
    return s.ns["__r"]


def test_chained_comparison_intersects():
    s = _s()
    assert len(ev(s, "3 < degree < 6")) == len(ev(s, "(degree > 3) & (degree < 6)")) == 49
    assert ev(s, "(3 < degree < 6).annotation") == "(degree > 3) & (degree < 6)"
    assert ev(s, "(1 < 2 < 3, 1 < 3 < 2, 3 > 2 == 2)") == (True, False, True)


def test_and_or_not_on_sets():
    s = _s()
    both = ev(s, "(dept == 'dept1') & (degree > 3)")
    assert list(ev(s, "(dept == 'dept1') and (degree > 3)")) == list(both)
    assert len(ev(s, "(dept == 'dept1') or (dept == 'dept2')")) == len(ev(s, "(dept == 'dept1') | (dept == 'dept2')"))
    n = len(s.graph.nodes)
    assert len(ev(s, "not (dept == 'dept1')")) == n - len(ev(s, "dept == 'dept1'"))
    assert len(ev(s, "not (freq > 100)")) == len(s.graph.edges) - len(ev(s, "freq > 100"))
    # plain values and tests keep Python's meaning
    assert ev(s, "(0 and 5, 0 or 5, 3 and 4, not 0, not [1])") == (0, 5, 4, True, False)
    assert ev(s, "1 if (dept == 'dept1') and (degree > 100) else 2") == 2
    assert ev(s, "[n.name for n in g.nodes if n.degree > 3 and n.dept == 'dept1']") == [x.name for x in both]
    assert s.run("def f(a):\n    return a and 5\n__r = (f(0), f(3))") and s.ns["__r"] == (0, 5)
    assert s.run("__r = 0\nif (dept == 'dept1') and (degree > 3):\n    __r = 1") and s.ns["__r"] == 1
    # walrus inside a boolean expression still works (not wrapped)
    assert ev(s, "[y for x in [1, 2, 3] if (y := x * 2) and y > 2]") == [4, 6]


def test_membership_queries():
    s = _s()
    assert len(ev(s, "degree in [1, 2]")) == len(ev(s, "(degree == 1) | (degree == 2)"))
    assert len(ev(s, "dept not in ('dept1', 'dept2')")) == \
        len(s.graph.nodes) - len(ev(s, "(dept == 'dept1') | (dept == 'dept2')"))
    assert ev(s, "(dept in ('dept1',)).annotation") == "dept in ('dept1')"
    assert ev(s, "v1 in g.nodes") is True
    assert ev(s, "2 in [1, 2]") is True


def test_precedence_hint():
    s = _s()
    assert not s.run("dept == 'dept1' & degree > 3")
    assert "parentheses" in s.rec.of("error")[-1]["summary"]
    assert ev(s, "6 & 3") == 2                          # numbers are untouched


def test_no_self_suggestion_for_missing_object():
    s = _s()
    assert not s.run("g.getNodeByName('zzz').color = red")
    assert "did you mean" not in s.rec.of("error")[-1]["summary"]


def test_values_summaries_and_iterable_fields():
    s = _s()
    vals = ev(s, "(dept == 'dept1').degree")
    assert isinstance(vals, list) and abs(vals.avg - sum(vals) / len(vals)) < 1e-9
    assert vals.count == len(vals) and vals.max == max(vals) and vals.sum == sum(vals)
    assert ev(s, "max(degree)") == ev(s, "degree.max")
    assert ev(s, "degree.median") == ev(s, "g.nodes.degree.median")
    assert ev(s, "(dept == 'dept1').dept.distinct") == ["dept1"]


def test_highest_lowest_and_descending():
    s = _s()
    hi = ev(s, "highest(degree, 3)")
    assert [n.degree for n in hi] == sorted(ev(s, "g.nodes.degree"), reverse=True)[:3]
    assert hi.annotation == "highest 3 by degree"
    assert [n.degree for n in ev(s, "lowest(degree, 2)")] == [0, 0]
    assert [n.degree for n in ev(s, "sortBy(degree, descending=true)[:3]")] == [n.degree for n in hi]
    within = ev(s, "highest(degree, 2, dept == 'dept1')")
    assert all(n.dept == "dept1" for n in within) and len(within) == 2


def test_reserved_names_loosened():
    s = _s()
    # an explicit import replaces a command for the session; del brings it back
    assert s.run("from math import log\n__r = log(100, 10)"), s.rec.of("error")
    assert s.ns["__r"] == 2.0 and "now your import" in s.rec.of("text")[-1]["text"]
    assert s.run("del log") and getattr(s.ns["log"], "_guess_command", False)
    assert not s.run("import g")                     # never the graph
    # loop variables may reuse a node's name, for the cell
    s.run("addNode('n')")
    assert s.run("for n in g.nodes[:3]: pass"), s.rec.of("error")
    assert ev(s, "n.name") == "n"                     # the node again afterwards
    assert not s.run("n = 5")                         # plain assignment is still protected
    # nodes and fields never hide Python's builtins
    s.run("addNode('len'); addNodeField('type', VARCHAR, 'a')")
    assert ev(s, "len([1, 2, 3])") == 3
    assert ev(s, "type(3).__name__") == "int"
    assert len(ev(s, "Node.type == 'a'")) == len(s.graph.nodes)
    assert ev(s, "g.getNodeByName('len').name") == "len"


def test_minus_assign_matches_minus():
    s = _s()
    assert ev(s, "(lambda a: a)(5)") == 5
    s.run("a = (dept == 'dept1')\na -= (dept == 'dept2')")
    assert list(s.ns["a"]) == list(ev(s, "(dept == 'dept1') - (dept == 'dept2')"))
    assert "a.difference(b)" in s.ns["a"].annotation
    s.run("k = 10\nk -= 3\nst = {1, 2}\nst2 = st\nst -= {1}")
    assert s.ns["k"] == 7 and s.ns["st2"] == {2} and s.ns["st"] is s.ns["st2"]


def test_field_names_as_strings_and_renamed_commands():
    s = _s()
    assert s.run("sizeBy('degree', 4, 20)\ncolorBy('pagerank', yellow, red)\nlegendFor('dept')\n"
                 "__r = len(highest('degree', 3))"), s.rec.of("error")
    assert s.ns["__r"] == 3
    assert not s.run("sizeBy('degre', 4, 20)")
    assert "did you mean 'degree'" in s.rec.of("error")[-1]["summary"]
    assert s.run("resizeLinear(degree, smallest=5, largest=30)"), s.rec.of("error")
    assert s.run("addNodeField(name='score', type=DOUBLE, default=1.5)") and ev(s, "v1.score") == 1.5
    assert s.run("pieChart(dept)\nremovePies()\nbundleEdges()\nremoveBundles()"), s.rec.of("error")
    assert not s.run("pieOff()") and not s.run("unbundleEdges()")
