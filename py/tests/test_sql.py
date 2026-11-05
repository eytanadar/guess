from tests.test_gython import Recorder, ev, names, s  # noqa: F401


def test_select_rows_and_elements(s):
    rows = ev(s, "sql('SELECT dept, count(*) FROM nodes GROUP BY dept ORDER BY dept')")
    assert rows == [("IT", 2), ("Sales", 2)]
    assert names(ev(s, "sql(\"SELECT name FROM nodes WHERE jobfunc = 'Manager'\")")) == ["al_x", "bob"]
    assert names(ev(s, "sql('SELECT __edgeid FROM edges WHERE freq > 9')")) == ["bob->jane", "bob-alice"]
    # elements combine with the rest of Gython
    assert names(ev(s, "sql(\"SELECT name FROM nodes WHERE dept = 'IT'\") & (jobfunc == 'Designer')")) == ["alice"]
    assert ev(s, "sql('SELECT max(freq) FROM edges')") == [30]


def test_update_writes_back(s):
    s.rec.clear()
    s.run("sql(\"UPDATE nodes SET color = 'red', width = 20 WHERE dept = 'Sales'\")")
    assert ev(s, "jane.color") == "red" and ev(s, "al_x.width") == 20 and ev(s, "bob.color") == "cornflowerblue"


def test_errors(s):
    s.rec.clear()
    assert not s.run("sql('SELECT nope FROM nodes')")
    assert "SQL error" in s.rec.of("error")[0]["text"]
    s.rec.clear()
    assert not s.run("sql('DELETE FROM nodes')")
    assert "can't add or delete" in s.rec.of("error")[0]["text"]
    assert len(s.graph.nodes) == 4
