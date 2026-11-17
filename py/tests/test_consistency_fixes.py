"""Wrong answers that came with no error: >> lifting, not >>, formats in
queries, colour spellings, set equality and +, `or "x"`, f-strings and table()."""
import pytest

from guess.outformats import Formatted
from tests.test_linked_output import _s


def ev(s, code):
    assert s.run("__r = " + code), s.rec.of("error")
    return s.ns["__r"]


def err(s, code):
    s.rec.clear()
    assert not s.run(code)
    return s.rec.of("error")[-1]["summary"]


def out(s, code):
    s.rec.clear()
    assert s.run(code), s.rec.of("error")
    (o,) = s.rec.of("out")
    (seg,) = o["segs"]
    return seg


# 1 ---------------------------------------------------------------------------
def test_shift_by_a_variable_named_like_a_format_is_a_shift():
    s = _s()
    assert s.run("count = 3\nk = 1")
    assert ev(s, "1 | 16 >> count") == 3
    assert ev(s, "2 == 16 >> count") is True
    assert ev(s, "k | 16 >> count") == 3            # a name on the left: decided at run time
    assert ev(s, "k == 16 >> count") is False


def test_lifting_still_applies_to_queries_and_keeps_order():
    s = _s()
    assert out(s, "dept == 'dept1' >> count")["g"] == ["43"]
    assert out(s, "(dept == 'dept1') | (dept == 'dept2') >> count")["g"] == [str(ev(s, "len((dept == 'dept1') | (dept == 'dept2'))"))]
    assert s.run("calls = []\ndef a():\n    calls.append('a')\n    return dept == 'dept1'\n"
                 "def b():\n    calls.append('b')\n    return dept == 'dept2'\n"
                 "def f():\n    calls.append('f')\n    return count")
    v = ev(s, "a() | b() >> f()")
    assert isinstance(v, Formatted) and s.ns["calls"] == ["a", "b", "f"]


# 2 ---------------------------------------------------------------------------
def test_not_lifts_through_the_format():
    s = _s()
    v = ev(s, 'not (dept == "dept1") >> summary')
    assert isinstance(v, Formatted) and v.fmt.name == "summary"
    assert len(v.value) == ev(s, "len(g.nodes)") - 43
    seg = out(s, 'not (dept == "dept1") >> count')
    assert seg["g"] == [str(ev(s, "len(g.nodes)") - 43)]


# 3 ---------------------------------------------------------------------------
def test_user_format_after_a_query():
    s = _s()
    assert s.run("def myfmt(v):\n    return f'{len(v)} things'")
    assert out(s, "degree > 3 >> myfmt") == f"{ev(s, 'len(degree > 3)')} things"   # lifted too
    assert s.run("fx = 3 >> myfmt")
    msg = err(s, "degree > fx")
    assert "parentheses" in msg and ">> myfmt" in msg
    assert "parentheses" in err(s, "(dept == 'dept1') | fx")


# 4 ---------------------------------------------------------------------------
def test_colour_queries_compare_colours_not_spellings():
    s = _s()
    assert s.run('v4.color = "#ff0000"\nv5.color = red\nv6.color = "#FF0000"\nv7.color = "255,0,0"')
    reds = {"v4", "v5", "v6", "v7"}
    assert {n._name for n in ev(s, 'color == "red"')} == reds
    assert {n._name for n in ev(s, "color == red")} == reds
    assert {n._name for n in ev(s, 'color == "#FF0000"')} == reds
    assert not reds & {n._name for n in ev(s, 'color != "red"')}
    assert {n._name for n in ev(s, 'color in ("red", "blue")')} >= reds
    groups = ev(s, "groupBy(color)")
    red_groups = [grp for grp in groups if any(n._name in reds for n in grp)]
    assert len(red_groups) == 1 and {n._name for n in red_groups[0]} == reds
    d = ev(s, "color.distinct")
    assert len(d) == 2                                     # the default colour and red
    assert str(d[1]) == "#ff0000"                          # shown as first written
    assert {n._name for n in d.groups()[d[1]]} == reds
    assert len(ev(s, "g.nodes.color.distinct")) == 2


# 5 ---------------------------------------------------------------------------
def test_set_equality_ignores_order_and_plus_is_union():
    s = _s()
    assert s.run('a = (dept=="dept1") | (dept=="dept2")\nb = (dept=="dept2") | (dept=="dept1")')
    assert ev(s, "a == b") is True and ev(s, "a != b") is False
    assert ev(s, "a == set(b)") is True
    assert ev(s, "a == list(b)") is False                   # against a list: as lists
    assert ev(s, "groupBy(dept) == groupBy(dept)") is True
    assert ev(s, "len(a + a)") == len(s.ns["a"])
    assert ev(s, "list(a + (dept == 'dept3'))") == list(ev(s, "a | (dept == 'dept3')"))
    assert ev(s, "type([1] + a).__name__") == "list" and ev(s, "len([v1] + a)") == len(s.ns["a"]) + 1
    with pytest.raises(TypeError):
        hash(s.ns["a"])


# 6 ---------------------------------------------------------------------------
def test_query_or_bare_value_is_an_error():
    s = _s()
    msg = err(s, 'dept == "dept1" or "dept2"')
    assert "dept in ('dept1', 'dept2')" in msg
    assert "did you mean" in err(s, "degree > 3 and 5")
    assert "did you mean" in err(s, '(dept == "dept1") | "dept2"')
    assert "did you mean" in err(s, "(dept == 'nothing') or 'none'")   # empty or not
    assert s.run("chosen = g.nodes[:2]")
    assert ev(s, "chosen or 'none'") is s.ns["chosen"]                 # not a query: Python's or
    assert ev(s, "g.nodes[:0] or 'none'") == "none"


# 7 ---------------------------------------------------------------------------
def test_fstring_uses_the_format():
    s = _s()
    assert ev(s, 'f"{highest(degree, 3) >> count} nodes"') == "3 nodes"
    assert ev(s, 'str(highest(degree, 3) >> count)') == "3"
    s.rec.clear()
    assert s.run('print(f"{highest(degree, 3) >> count} nodes")')
    (o,) = s.rec.of("out")
    assert isinstance(o["segs"][0], dict) and o["segs"][0]["g"] == ["3"] and o["segs"][1] == " nodes"


# 8 ---------------------------------------------------------------------------
def test_table_of_a_set_sorted_opens_the_table():
    s = _s()
    s.rec.clear()
    assert s.run('table(dept=="dept1", sort=degree)')
    (t,) = s.rec.of("table")
    degs = [s.graph.node_by_id(i).degree for i in t["ids"]]
    assert len(degs) == 43 and degs == sorted(degs, reverse=True)
    s.rec.clear()
    assert s.run('table(dept=="dept1", sort=degree, descending=false)')
    degs = [s.graph.node_by_id(i).degree for i in s.rec.of("table")[0]["ids"]]
    assert degs == sorted(degs)
    assert repr(ev(s, "table(sort=degree)")).startswith("<format table")
    assert repr(ev(s, "table(degree, descending=false)")).startswith("<format table")
    seg = out(s, "(degree > 8) >> table(degree, sort=degree, descending=false)")
    degs = [int(r[1]) for r in seg["tbl"]["rows"]]
    assert degs == sorted(degs)
