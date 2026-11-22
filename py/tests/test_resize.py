"""resize() and colorize(): scales and sizes chosen from the field and the layout."""
from tests.test_linked_output import _s


def _said(s):
    return "".join(m.get("text", "") for m in s.rec.of("text"))


def test_resize_infers_the_scale_and_sizes_and_takes_overrides():
    s = _s()
    g = s.ns["g"]
    s.rec.clear()
    assert s.run("resize(pagerank)")
    assert "sqrt" in _said(s)                            # skewed numbers
    sizes = sorted(n.size for n in g.nodes)
    assert 3 <= sizes[0] < sizes[-1] <= 80               # from the layout's spacing
    s.rec.clear()
    assert s.run("resize(dept)")                         # text: evenly by rank
    assert "by rank" in _said(s)
    assert len({n.size for n in g.nodes}) == len(set(n.dept for n in g.nodes))
    assert s.run("resize(degree, 5, 40, transform='log')")
    assert min(n.size for n in g.nodes) == 5 and max(n.size for n in g.nodes) == 40
    s.rec.clear()
    assert s.run("resize(freq)")                         # an edge field: widths
    assert "widths 0.5" in _said(s)
    assert min(e.width for e in g.edges) == 0.5
    s.rec.clear()
    assert not s.run("resize(degree, transform='cube')")
    assert "transform is" in s.rec.of("error")[0]["summary"]


def test_resize_keeps_resizelinear_spacing_with_rank():
    s = _s()
    assert s.run("resize(degree, 5, 30, transform='rank')")
    sizes = sorted({n.size for n in s.ns["g"].nodes})
    steps = {round(b - a, 6) for a, b in zip(sizes, sizes[1:])}
    assert sizes[0] == 5 and sizes[-1] == 30 and len(steps) == 1    # evenly spaced distinct values


def test_colorize_picks_categorical_or_gradient():
    s = _s()
    g = s.ns["g"]
    assert s.run("colorize(dept)")                       # text: a colour per value
    assert len({str(n.color) for n in g.nodes}) == len({n.dept for n in g.nodes})
    assert s.run("louvainClusters(name='team')")         # group ids, even under another name
    s.rec.clear()
    assert s.run("colorize(team)")
    assert "gradient" not in _said(s)
    s.rec.clear()
    assert s.run("colorize(degree)")                     # numbers: a gradient
    assert "viridis" in _said(s)
    assert s.run("Node.score = 0.0\nfor n in g.nodes: n.score = n.degree - 3")
    s.rec.clear()
    assert s.run("colorize(score)")                      # crossing zero: diverging
    assert "RdBu" in _said(s)
    assert s.run("colorize(degree, palette='Set2')")    # an explicit palette still wins
