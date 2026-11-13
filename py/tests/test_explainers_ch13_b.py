"""Batch 8 explainers: the Barabási–Albert model, and the first-mover advantage."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_barabasi_albert_grows_in_place_and_makes_hubs():
    a = App("ch13-barabasi-albert")
    n, m = a.ev("st['n']"), a.ev("st['m']")
    assert len(a.s.graph._nodes_list()) == n
    assert a.ev("len([v for v in g.nodes if v.visible])") == m + 1         # only the starting clique
    before = _positions(a)
    a.press("Grow node by node")
    a.tick(8)
    assert a.ev("st['k']") == 8 and a.ev("len([v for v in g.nodes if v.visible])") == m + 1 + 8
    assert sum(1 for e in a.s.graph._edges_list() if e.visible and e.linestyle == "flow") == m   # the newcomer's edges
    assert "linked to" in a.markdown() and a.ev("grow_chart()") is not None
    a.press("Show the whole network")
    assert all(v.visible for v in a.s.graph._nodes_list()) and _positions(a) == before   # nobody moved
    # degrees: every newcomer brings m edges
    deg = a.ev("shown_degrees()")
    assert sum(deg) == 2 * len(a.ev("st['edges']")) and min(deg) >= m
    # uniform attachment: no big hubs
    a.set("dropdown", "Attach", "Uniform (any node equally)")
    assert a.ev("st['model']").startswith("Uniform")
    _tab(a, "Degree distributions")
    b = a.ev("big_pair()")
    assert max(b["pref"]) > 3 * max(b["unif"])
    assert 2.6 < b["fit_tail"]["alpha"] < 3.4 and "α =" in a.markdown()
    a.set("dropdown", "Axes", "log-linear")
    assert a.ev("dist_chart()") is not None
    _tab(a, "Hubs")
    a.press("Simulate: networks of 250 to 16,000 nodes")
    a.tick(10)
    sw = a.ev("st['sweep']")
    assert len(sw) == 7 and sw[-1][1] > 4 * sw[0][1] and sw[-1][2] < 2.5 * sw[0][2]
    assert a.ev("hubs_chart()") is not None and "√n" in a.markdown()


def test_first_mover_oldest_win_follow_and_citations():
    a = App("ch13-first-mover")
    assert "Rank correlation between arrival and degree" in a.markdown()
    deg = a.ev("degrees_at(steps())")
    assert sum(deg[:30]) / 30 > 3 * sum(deg[150:]) / 150                    # early nodes are the hubs
    assert a.ev("oldest_chart()") is not None
    a.press("Simulate: 30 networks of 2,000")
    a.tick(32)
    assert a.ev("st['sim']['runs']") == 30 and a.ev("sim_chart()") is not None
    before = _positions(a)
    _tab(a, "Follow a node")
    a.press("An early node")
    assert a.ev("st['follow']") == 5
    a.press("Replay the growth")
    a.tick(40)
    k = a.ev("st['k']")
    assert 0 < k < a.ev("steps()")
    shown = a.ev("len([v for v in g.nodes if v.visible])")
    assert shown == k + 3 and _positions(a) == before                         # revealed in place
    traj = a.ev("trajectory(5)")
    assert traj[-1][1] == a.ev("degrees_at(steps())")[5] and traj[0][1] == 2   # arrives with m links
    assert "Following" in a.markdown() and a.ev("follow_chart()") is not None
    _tab(a, "Real citations")
    assert a.ev("graphNames()")[0] == "papers"
    md = a.markdown()
    assert "mean citations from this field" in md and a.ev("papers_chart()") is not None
    early = [v.indegree for v in a.s.graph._nodes_list() if v.year and v.year < 1995]
    late = [v.indegree for v in a.s.graph._nodes_list() if v.year and v.year >= 2015]
    assert sum(early) / len(early) > 5 * sum(late) / len(late)
    _tab(a, "Oldest win")
    assert a.ev("graphNames()")[0] == "model" and all(v.visible for v in a.s.graph._nodes_list())
