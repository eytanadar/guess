"""Networks explainers, Chapter 7 (part a): eigenvector/Katz centrality and
PageRank/HITS. Uses the App driver from test_explainers."""
import numpy as np

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401  (the fixture runs in the data folder)


def _switch(a, title):
    tabs = _tabs(a)
    a.s.dispatch(tabs._id, "change", title)
    assert not a.errors(), a.errors()


def test_power_iteration_converges_to_the_eigenvector():
    a = App("ch07-eigenvector-katz")
    assert sorted(a.s.ns["graphNames"]()) == ["directed", "karate"]
    for _ in range(60):
        a.call("power_step()")
    p = a["power"]
    x = p["x"] / p["x"].max()
    assert np.abs(x - a["VEC"]).max() < 1e-3
    assert abs(p["kappa"][-1][1] - a["KAPPA"]) < 1e-3
    assert "Step **60**" in a.ev("power_text()")
    assert a.ev("power_chart()") is not None
    a.press("Start from one node")
    assert a["power"]["t"] == 0 and a["power"]["x"].sum() == 1
    a.press("Iterate")
    a.tick(5)
    assert a["power"]["t"] == 5
    assert any(e.linestyle == "flow" for e in a.s.graph.edges)
    a.press("Pause")


def test_directed_zeros_spread_and_katz_removes_them():
    a = App("ch07-eigenvector-katz")
    _switch(a, "Directed: zeros spread")
    assert a.s.ns["graphNames"]()[0] == "directed"
    a.press("Iterate x ← Ax")
    a.tick(12)
    zeros = {v for v, val in zip(a["DNAMES"], a["dpow"]["x"]) if val == 0}
    assert {"S1", "S2", "S3", "P1", "P2", "Q1"} <= zeros
    assert not zeros & {"A", "B", "C", "D", "E", "F", "G", "H", "I"}
    assert "have score zero" in a.ev("dtext()")
    a.press("Iterate Katz")
    a.tick(12)
    assert (a["dpow"]["x"] > 0).all()
    a.press("Reset")
    assert a["dpow"]["t"] == 0


def test_katz_alpha_slides_from_degree_to_eigenvector():
    a = App("ch07-eigenvector-katz")
    _switch(a, "Katz α")
    a.set("slider", "α as %", 2)
    deg = a["KA"].sum(axis=1)
    lo = a.ev("spearman(katz_values(2)[0], KA.sum(axis=1))")
    hi = a.ev("spearman(katz_values(98)[0], VEC)")
    assert lo > 0.95 and hi > 0.95
    assert a.node("k34").katz > a.node("k12").katz
    text = a.ev("katz_text()")
    assert "| rank | degree | Katz | eigenvector |" in text
    a.press("Simulate: sweep α")
    assert a["katzs"]["sweep"] is not None and a.ev("katz_chart()") is not None
    a.press("Scatter against degree")
    assert a.ev("katz_chart()") is not None
    assert deg.max() == 17


def test_random_surfer_converges_to_pagerank():
    a = App("ch07-pagerank-hits")
    assert len(a.s.graph.nodes) == 19
    a.press("Surf")
    a.tick(6)
    assert a["surf"]["steps"] == 6
    assert any(e.linestyle == "flow" for e in a.s.graph.edges) or a.s.view.drawings
    a.press("Pause")
    a.press("2,000 steps at once")
    for _ in range(10):
        a.call("surf_many(2000)")
    pr = a.ev("pagerank_of(0.85)")
    share = np.array([a["surf"]["visits"][v] for v in a["PAGES"]]) / a["surf"]["steps"]
    assert np.abs(share - pr).max() < 0.02
    assert abs(pr.sum() - 1) < 1e-9
    assert a.ev("surf_chart()") is not None and "share of time is the PageRank" in a.ev("surf_text()")
    a.press("Reset")
    assert a["surf"]["steps"] == 0


def test_pagerank_tab_damping_and_sweep():
    a = App("ch07-pagerank-hits")
    _switch(a, "PageRank")
    pr = a.ev("pagerank_of(0.85)")
    top = a["PAGES"][int(np.argmax(pr))]
    assert any(e.linestyle == "flow" and e.node2.name == top for e in a.s.graph.edges)
    # pages with no links in get only the random jump (and the dangling pages' share): all the same, the least
    assert abs(a.node("directory").prval - a.node("blog3").prval) < 1e-12
    assert a.node("directory").prval == min(n.prval for n in a.s.graph.nodes)
    farm_hi = a.ev("sum(pagerank_of(0.95)[IX[v]] for v in ('farm', 'spam1', 'spam2', 'spam3'))")
    farm_lo = a.ev("sum(pagerank_of(0.5)[IX[v]] for v in ('farm', 'spam1', 'spam2', 'spam3'))")
    assert farm_hi > farm_lo
    low = a.node("directory").prval
    a.set("slider", "α: chance", 50)
    assert a.node("directory").prval > low
    assert "| page | PageRank |" in a.ev("pr_text()")
    assert a.ev("pr_chart()") is not None
    a.press("Simulate: sweep α")
    assert len(a["prs"]["sweep"]) == 5 and a.ev("pr_chart()") is not None
    a.press("PageRank against links in")
    assert a["prs"]["sweep"] is None


def test_hubs_and_authorities():
    a = App("ch07-pagerank-hits")
    _switch(a, "Hubs and authorities")
    hub, auth = a.ev("hits_scores()")
    P = a["PAGES"]
    assert P[int(np.argmax(hub))] in ("portal", "directory")
    assert a.node("directory").hubscore > 0.8 and a.node("directory").authscore < 0.05
    a.set("dropdown", "Size by", "Hubs")
    assert a.node("directory").width > a.node("wiki").width
    assert "Top **hubs**" in a.ev("hits_text()") and a.ev("hits_chart()") is not None
