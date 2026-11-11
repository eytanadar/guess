"""Output that links to the graph: dicts, sets, f-strings, long groups, chart queries."""
from pathlib import Path

from guess import Session
from tests.test_gython import Recorder

SAMPLE = Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    rec.msgs.clear() if hasattr(rec, "msgs") else None
    return s


def last_out(s, code):
    before = len(s.rec.of("out"))
    assert s.run(code), s.rec.of("error")
    outs = s.rec.of("out")[before:]
    assert outs, f"no linked output from {code!r}"
    return outs[-1]["segs"]


def ids(segs):
    out = []
    for sg in segs:
        if isinstance(sg, dict):
            if "n" in sg:
                out.append(("n", sg["n"]))
            elif "e" in sg:
                out.append(("e", sg["e"]))
            else:
                out += ids(sg.get("g", []))
                out += [tuple(x) for x in sg.get("x", [])]
    return out


def test_dicts_and_sets_link():
    s = _s()
    segs = last_out(s, "{n: n.degree for n in g.nodes[:2]}")
    assert ids(segs) == [("n", 0), ("n", 1)]
    assert segs[0]["g"][0] == "{" and segs[0]["g"][-1] == "}"
    assert len(ids(last_out(s, "set(g.nodes[:3])"))) == 3
    assert ids(last_out(s, "{'a': [v1, v2]}")) == [("n", 0), ("n", 1)]


def test_fstrings_link_and_stay_strings():
    s = _s()
    segs = last_out(s, 'print(f"first is {v1}, then {v2.degree}")')
    assert segs[0] == "first is " and segs[1] == {"n": 0, "t": "v1"}
    assert s.run('__t = f"{v1}-{v2}"') and s.ns["__t"] == "v1-v2" and isinstance(s.ns["__t"], str)
    assert s.run('__t = f"{3.14159:.2f}|{v1!r}|{5:>3}"') and s.ns["__t"] == "3.14|v1|  5"
    segs = last_out(s, 'print(f"hubs {highest(degree, 3)}")')
    assert len(ids(segs)) == 3 and segs[1]["a"] == "highest 3 by degree"


def test_long_groups_link_every_member():
    s = _s()
    segs = last_out(s, "g.nodes")
    assert len(ids(segs)) == len(s.graph.nodes)          # 402: 500 shown, the rest under x
    s.run("for i in range(600): addNode(f'extra{i}')")
    segs = last_out(s, "g.nodes")
    assert len(ids(segs)) == len(s.graph.nodes) == 1002


def test_summary_objects_link_their_elements():
    s = _s()
    s.run("for i in range(4): addDirectedEdge(v1, addNode(f'k{i}'))")
    segs = last_out(s, "offspring(show=False)")
    assert isinstance(segs[0]["g"][0], str) and "R =" in segs[0]["g"][0]
    assert ("n", 0) in ids(segs)


def test_chart_marks_carry_queries():
    s = _s()
    charts = []
    s.emit = lambda m: charts.append(m) if m.get("type") == "chart" else None
    s.run("plotHistogram(degree, 4)")
    qs = [it["q"] for it in charts[-1]["items"]]
    assert qs[0].startswith("(degree >= ") and "<=" in qs[-1]
    for it in charts[-1]["items"]:
        assert s.run(f"__q = {it['q']}") and len(s.ns["__q"]) == it["value"]
    s.run("plotSizes(dept)")
    it = charts[-1]["items"][0]
    assert s.run(f"__q = {it['q']}") and len(s.ns["__q"]) == it["value"]
    s.run("outbreaks(20, beta=0.5, gamma=0.5)")
    bars = charts[-1]["items"]
    assert sum(b["value"] for b in bars) == 20 and all(b["ids"] for b in bars if b["value"])


def test_distinct_values_link_to_their_members():
    s = _s()
    segs = last_out(s, "dept.distinct")
    grp = segs[0]
    assert grp["a"].startswith("21 values of dept")
    first = grp["g"][1]
    assert first["q"].startswith("dept == ") and first["x"]
    assert s.run(f"__q = {first['q']}") and len(s.ns["__q"]) == len(first["x"])
    sub = last_out(s, "(dept == 'dept1').jobfun.distinct")[0]["g"][1]
    assert "q" not in sub and "(in the set)" in sub["a"]
    assert sorted(ev_(s, "dept.distinct"))[:1] == ["dept0"]


def ev_(s, code):
    assert s.run(f"__r = {code}"), s.rec.of("error")
    return s.ns["__r"]


def test_outputs_are_tagged_with_their_graph():
    s = _s()
    before = s.graph_gen
    assert s.run("v1")
    assert s.rec.of("out")[-1]["gid"] == before
    s.run(f"makeFromGDF({str(SAMPLE)!r})")
    assert s.graph_gen == before + 1


def test_provenance_records_which_cell_changed_what():
    s = _s()
    s.current_cell = 2
    s.run("colorize(dept)")
    s.current_cell = 3
    s.run("v1.size = 30")
    prov = {a: c for a, c, _code in s.describe("n", 0)["prov"]}
    assert prov["color"] == 2 and prov["size"] == 3
    assert ("n", 0) in [tuple(x) for x in s.cell_changes(2)] and len(s.cell_changes(3)) == 1
    s.current_cell = 4
    s.run("undo()")
    prov = {a: c for a, c, _code in s.describe("n", 0)["prov"]}
    assert "size" not in prov and prov["color"] == 2


def test_peek_is_safe_and_describes_names_and_queries():
    s = _s()
    s.run("hubs = highest(degree, 5)")
    assert len(s.peek("hubs")["items"]) == 5
    assert len(s.peek("3 < degree < 6")["items"]) == 49
    f = s.peek("dept")
    assert "21 distinct values" in f["title"] and len(f["colors"]["n"]) == len(s.graph.nodes)
    assert s.peek("v1.degree")["title"] == "v1.degree = 1"
    n = len(s.graph.nodes)
    for bad in ["remove(v1)", "__import__('os')", "g.nodes.__class__", "[x for x in g.nodes]", "v1.color = red"]:
        assert s.peek(bad) is None
    assert len(s.graph.nodes) == n
    assert "__peek__" not in s.ns


def test_errors_link_the_nodes_and_edges_they_name():
    s = _s()
    s.run("v1.foo")
    err = s.rec.of("error")[-1]
    assert {"n": 0, "t": "v1"} in err["segs"] and err["gid"] == s.graph_gen
    assert "".join(x if isinstance(x, str) else x["t"] for x in err["segs"]) == err["summary"]
    s.run("raise ValueError(v1, v2)")
    assert ids(s.rec.of("error")[-1]["segs"]) == [("n", 0), ("n", 1)]
    s.run("raise ValueError('no such thing')")
    assert "segs" not in s.rec.of("error")[-1]
    s.run("remove(v3)\nraise ValueError(\"node 'v3' is gone\")")
    assert "segs" not in s.rec.of("error")[-1]         # removed: nothing to link to


def test_history_scrubber_moves_through_undo_steps():
    s = _s()
    s.current_cell = 2
    s.run("colorize(dept)")
    s.current_cell = 3
    s.run("v1.size = 40")
    s.current_cell = 4
    s.run("addNode('zz')")
    h = s.history_steps()
    assert h["at"] == len(h["steps"]) and [x["cell"] for x in h["steps"][-3:]] == [2, 3, 4]
    i = len(h["steps"]) - 2
    assert s.history_items(i) == [["n", 0]] and h["steps"][i]["count"] == 1
    assert s.history_goto(i) == i                       # before v1.size = 40
    assert s.ns["v1"].size != 40 and "zz" not in s.graph._nodes
    h = s.history_steps()
    assert h["at"] == i and [x["done"] for x in h["steps"][-2:]] == [False, False]
    undone = [m for m in s.rec.of("undone")]
    assert [m["cell"] for m in undone[-2:]] == [4, 3] and all(m["undone"] for m in undone[-2:])
    assert s.history_goto(i + 2) == i + 2
    assert s.ns["v1"].size == 40 and "zz" in s.graph._nodes
    assert s.history_goto(10_000) == i + 2 and s.history_goto(-5) == 0
    assert s.history_items(999) == []


def test_last_click():
    s = _s()
    assert ev_(s, "lastClick()") is None
    s.last_click = (1, 2.5)
    assert ev_(s, "lastClick()") == (1.0, 2.5)


def test_table_query_filters_with_gython_and_changes_nothing():
    s = _s()
    q = s.table_query("degree > 10", "n")
    assert len(q["ids"]) == len(ev_(s, "degree > 10")) and q["other"] == 0
    assert s.table_query("v1", "n") is None                 # a bare node name: text search
    assert s.table_query("dept1", "n") is None              # not a name: text search
    assert s.table_query("highest(degree, 5)", "n") is None  # calls wait for Enter
    assert len(s.table_query("highest(degree, 5)", "n", full=True)["ids"]) == 5
    assert s.table_query("weight > 0", "n")["other"] > 0     # edges: the other tab
    assert "error" in s.table_query("nonsense(", "n", full=True)
    assert "isn't a set" in s.table_query("3", "n", full=True)["error"]
    n, steps = len(s.graph.nodes), len(s.undo_stack)
    s.rec.clear()
    q = s.table_query("[(remove(v1), v2)[1]]", "n", full=True)
    assert q["ids"] == [1] and len(s.graph.nodes) == n and "v1" in s.graph._nodes
    assert len(s.undo_stack) == steps and not s.rec.of("error")


def test_label_cluster_and_cluster_info():
    s = _s()
    assert s.cluster_info("cluster") == {"exists": False, "type": None, "labels": [], "next": 1, "total": 402}
    assert s.run('labelCluster(["v1", "v2"], 1)') and s.run('labelCluster(["v2", "v3"], 2, relabel=False)')
    info = s.cluster_info("cluster")
    assert info["type"] == "INTEGER" and info["labels"] == [[0, 1], [1, 1], [2, 2]] and info["next"] == 3
    assert not s.run('labelCluster(["v4"], "a")')                  # a number field keeps numbers
    assert "holds numbers" in s.rec.of("error")[-1]["summary"]
    assert s.run('labelCluster(["v4"], "north", "region")') and s.cluster_info("region")["type"] == "VARCHAR"
    assert not s.run('labelCluster(["nobody"], 1)')
    s.run("undo()")
    assert s.cluster_info("region")["exists"] is False
