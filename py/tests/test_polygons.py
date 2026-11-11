"""Regular polygon node shapes: polygon(), polygonBy(), and DOT round trips."""
from tests.test_gython import s  # noqa: F401  (fixture)


def test_polygon_style_codes(s):
    assert s.run("bob.style = polygon(5)")
    assert s.run("assert bob.style == 105")
    assert not s.run("polygon(2)")
    assert not s.run("polygon('x')")


def test_polygon_by_field(s):
    assert s.run("addNodeField('k', INTEGER, 0)")
    assert s.run("bob.k = 7\nalice.k = 99")
    assert s.run("polygonBy(k)")
    assert s.run("assert bob.style == 107 and alice.style == 112")      # capped at largest=12
    assert s.run("polygonBy(name, 3, 4)")
    assert s.run("assert {n.style for n in g.nodes} <= {103, 104}")
    assert s.run("undo()")
    assert s.run("assert bob.style == 107")


def test_polygon_dot_round_trip(s, tmp_path):
    assert s.run("bob.style = polygon(7)")
    f = tmp_path / "g.dot"
    assert s.run(f"exportDOT({str(f)!r})")
    text = f.read_text()
    assert "polygon" in text and "sides=7" in text.replace('"', "")
    assert s.run(f"makeFromDOT({str(f)!r})")
    assert s.run("assert bob.style == 107")
