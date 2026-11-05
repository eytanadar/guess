"""Help index, panel data, styles, table(), structured errors."""
from tests.test_gython import ev, s  # noqa: F401  (fixture)


def errors(sess):
    return [m for m in sess.rec.of("error")]


def test_help_index_and_examples_run(s):
    h = s.help_index()
    names = {c["name"] for c in h["commands"]}
    assert {"colorize", "forceAtlas2Layout", "undo", "labelBy", "table"} <= names
    assert all(c["group"] in h["groups"] for c in h["commands"])
    assert len(h["examples"]) > 40


def test_curated_examples_compile(s):
    from guess import compiler
    from guess.helpdata import examples
    for e in examples():
        compiler.compile_gython(e["code"], is_protected=s.is_protected)   # no syntax errors


def test_errors_have_summary_line_and_suggestion(s):
    s.rec.clear()
    s.run("a1 = 1\ncolorize(dpet)")
    (e,) = errors(s)
    assert e["line"] == 2 and "did you mean 'dept'" in e["summary"]
    s.rec.clear()
    s.run("bob.colr")
    assert "did you mean 'color'" in errors(s)[0]["summary"]
    s.rec.clear()
    s.run("for n in g.nodes\n    pass")
    e = errors(s)[0]
    assert e["line"] == 1 and e["summary"].startswith("Syntax error")


def test_table_and_field_data(s):
    t = s.panel_data("table", "n")
    names = [f["name"] for f in t["fields"]]
    assert "dept" in names and "indegree" in names
    assert {r[1] for r in t["rows"]} == {"bob", "alice", "jane", "al_x"}
    assert not next(f for f in t["fields"] if f["name"] == "indegree")["editable"]
    e = s.panel_data("table", "e", [ev(s, "g.edges")[0]._id])
    assert len(e["rows"]) == 1
    info = {f["name"]: f for f in s.panel_data("fields", "e")}
    assert info["freq"]["numeric"] and info["freq"]["max"] == 30 and sum(info["freq"]["hist"]) == 4
    dept = next(f for f in s.panel_data("fields", "n") if f["name"] == "dept")
    assert not dept["numeric"] and dept["values"] == [["IT", 2], ["Sales", 2]]


def test_label_shape_legend_and_styles(s, tmp_path):
    assert s.run("labelBy(dept)")
    assert ev(s, "(bob.label, bob.labelvisible)") == ("IT", True)
    assert s.run("shapeBy(dept)")
    assert {ev(s, "bob.style"), ev(s, "jane.style")} == {2, 1}
    s.rec.clear()
    assert s.run("colorize(dept); legendFor(dept)")
    assert [e["t"] for e in s.view.legends[max(s.view.legends)]._entries] == ["IT", "Sales"]
    assert s.run("colorBy(freq, white, red); legendFor(freq)")
    assert s.run("defineStyle('red', ['g.nodes.color = red', 'labelBy(jobfunc)'])")
    assert s.run("g.nodes.color = blue")
    assert s.run("applyStyle('red')")
    assert ev(s, "bob.color") == "red" and ev(s, "bob.label") == "Manager"
    s.run("undo()")
    assert ev(s, "bob.color") == "blue"
    assert s.view.record()["styles"] == ["red"]
    from tests.test_persist import roundtrip
    assert roundtrip(s).view.styles == {"red": ["g.nodes.color = red", "labelBy(jobfunc)"]}
    assert not s.run("applyStyle('nope')")
    assert s.run("removeStyle('red')") and s.view.styles == {}


def test_table_command_and_help_message(s):
    s.rec.clear()
    s.run("table(dept == 'IT')")
    assert s.rec.of("table")[-1] == {"type": "table", "kind": "n", "ids": [ev(s, "bob")._id, ev(s, "alice")._id]}
    s.rec.clear()
    s.run("table(g.edges)")
    assert s.rec.of("table")[-1]["kind"] == "e" and s.rec.of("table")[-1]["ids"] is None
    s.rec.clear()
    s.run("help(colorize)")
    assert s.rec.of("help")[-1]["topic"] == "colorize"
