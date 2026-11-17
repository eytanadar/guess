"""Output formats: x >> table, showAs, setFormat by kind and by command, custom formats."""
from guess.compiler import to_python
from tests.test_linked_output import _s


def out(s, code):
    s.rec.clear()
    assert s.run(code), s.rec.of("error")
    (o,) = s.rec.of("out")
    (seg,) = o["segs"]
    return seg


def test_pipe_applies_to_the_whole_query():
    assert to_python("dept == 'd1' >> table") == "__display__(__gpipe__(dept == 'd1', table))"
    assert "__gbool__" in to_python("degree > 3 and dept == 'x' >> summary").split("__gpipe__(")[1]
    assert to_python("a | b >> table(degree)") == "__display__(__gpipe__(__gor__(a, b), table(degree)))"
    assert to_python("n == m >> 1") == "__display__(n == __gpipe__(m, 1))"      # still a shift
    # the command a value came from, for setFormat(command, ...)
    assert to_python("louvainClusters() >> table").endswith(", 'louvainClusters')")


def test_shift_still_shifts():
    s = _s()
    assert s.run("__r = 20 >> 2") and s.ns["__r"] == 5


def test_table_of_a_set_has_the_query_fields_and_links_nodes():
    s = _s()
    seg = out(s, "dept == 'dept1' >> table")
    assert seg["tbl"]["cols"] == ["node", "dept"]
    assert len(seg["tbl"]["rows"]) == 43
    assert "n" in seg["tbl"]["rows"][0][0] and seg["tbl"]["rows"][0][1] == "dept1"
    seg = out(s, "(degree > 8) >> table(dept, degree, sort=degree)")
    assert seg["tbl"]["cols"] == ["node", "dept", "degree"]
    degs = [int(r[2]) for r in seg["tbl"]["rows"]]
    assert degs == sorted(degs, reverse=True)
    seg = out(s, "(degree > 8) >> table(degree, sort=degree, reverse=false)")
    degs = [int(r[1]) for r in seg["tbl"]["rows"]]
    assert degs == sorted(degs)


def test_table_of_groups_values_dict_and_node():
    s = _s()
    seg = out(s, "groupBy(dept) >> table(sort='size')")
    assert seg["tbl"]["cols"] == ["label", "size", "members"]
    first = seg["tbl"]["rows"][0]
    assert first[0] == "dept6" and first[1] == "52" and first[2]["c"] == 1
    seg = out(s, "dept.distinct >> table(sort='count')")
    assert seg["tbl"]["cols"] == ["dept", "count"] and seg["tbl"]["rows"][0][1] == "52"
    assert seg["tbl"]["rows"][0][0]["q"] == "dept == 'dept6'"
    seg = out(s, "{v1: 3, v2: 4} >> table")
    assert seg["tbl"]["cols"] == ["key", "value"] and seg["tbl"]["rows"][1] == [{"n": 1, "t": "v2"}, "4"]
    seg = out(s, "v4 >> table")
    assert seg["tbl"]["cols"] == ["field", "value"] and ["dept", "dept3"] in seg["tbl"]["rows"]


def test_summary_count_plain_folded():
    s = _s()
    seg = out(s, "groupBy(dept) >> summary")
    assert seg["g"] == ["grouped by dept: 21 groups, sizes 1–52 (402 nodes)"] and len(seg["x"]) == 402
    seg = out(s, "dept == 'dept1' >> count")
    assert seg["g"] == ["43"] and len(seg["x"]) == 43 and seg["a"] == "dept == 'dept1'"
    assert out(s, "dept == 'dept3' >> plain").startswith("v4, v5, ")
    assert out(s, "groupBy(dept) >> plain").splitlines()[3].startswith("dept3: [v4, ")
    assert out(s, "dept == 'dept1' >> folded")["c"] == 1
    assert out(s, "dept == 'dept1' >> 'count'")["g"] == ["43"]       # by name
    assert out(s, "showAs(dept == 'dept1', 'count')")["g"] == ["43"]


def test_set_format_by_kind_and_by_command():
    s = _s()
    assert s.run("setFormat('set', count)")
    assert out(s, "dept == 'dept1'")["g"] == ["43"]
    assert out(s, "print(dept == 'dept1')")["g"] == ["43"]
    assert "g" in out(s, "dept == 'dept1' >> list")              # given for this value: wins
    assert s.run("setFormat('set')")                              # back to the default
    assert "[" in out(s, "dept == 'dept1'")["g"]
    assert s.run("setFormat(groupBy, table)")
    assert "tbl" in out(s, "groupBy(dept)")
    assert "tbl" not in out(s, "louvainClusters()")
    assert s.run("resetFormats()")
    assert "tbl" not in out(s, "groupBy(dept)")
    s.rec.clear()
    assert not s.run("setFormat('bogus', table)")
    assert "not a kind or a command" in s.rec.of("error")[-1]["summary"]


def test_custom_format_function():
    s = _s()
    assert s.run("def sizes(v):\n    return f'{len(v)} things'\nsetFormat('set', sizes)")
    assert out(s, "dept == 'dept3'") == "9 things"
    assert out(s, "(dept == 'dept1') >> sizes") == "43 things"      # after >> too
    assert s.run("def firsts(v):\n    return v[:2]\nsetFormat('set', firsts)")
    seg = out(s, "dept == 'dept3'")
    assert [x for x in seg["g"] if isinstance(x, dict)] == [{"n": 3, "t": "v4"}, {"n": 4, "t": "v5"}]


def test_format_names_stay_usable_as_variables():
    s = _s()
    assert s.run("count = 3\nsummary = 'x'\n__r = count")
    assert s.ns["__r"] == 3
    assert "tbl" in out(s, "dept == 'dept1' >> table")             # table still a format


def test_formats_lists_kinds_and_formats():
    s = _s()
    s.rec.clear()
    assert s.run("setFormat('groups', table(sort='size'))\nformats()")
    kinds, fmts = [o["segs"][0] for o in s.rec.of("out")]
    assert ["groups", "a set of groups (groupBy(dept), louvainClusters())", "table(sort='size')"] in kinds["tbl"]["rows"]
    assert {r[0] for r in fmts["tbl"]["rows"]} == {"list", "folded", "table", "summary", "count", "plain"}
