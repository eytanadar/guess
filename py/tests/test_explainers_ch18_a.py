"""ch18-web-search and ch18-distributed-search."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401


def test_web_search_blend_and_link_farm():
    a = App("ch18-web-search")
    assert not a.errors(), a.errors()
    blend = "weight on links (PageRank), %"
    a.call("search('network science')")
    order = {}
    for w in (0, 50, 100):
        a.set("slider", blend, w)
        order[w] = a.ev("[r[1] for r in ranking()[0]]")
    # text alone: the keyword-stuffed page wins; a blend: honest pages win; links alone: popular pages rise
    assert order[0][0] == "pg_spam"
    assert order[50][0] in ("pg_wiki", "pg_notes") and order[50].index("pg_spam") > 1
    assert "pg_spam" not in order[100][:3]
    assert "guess:n" in a.markdown()                               # results are linkTo chips
    a.set("slider", blend, 50)
    pr = a.ev("page_rank()")
    assert abs(sum(pr.values()) - 1) < 1e-9
    # the link farm grows page by page, revealed in place, and pumps up the spam page
    before = a.ev("{v.name: (v.x, v.y) for v in g.nodes}")
    a.tab("Link farm")
    a.press("Build a link farm, page by page")
    a.tick(12)
    assert a.ev("st['farm']") == a.ev("FARM")
    rows = a.ev("st['farm_rows']")
    assert rows[-1][1] > rows[0][1] * 10 and rows[-1][1] > rows[-1][2]   # spam ends above the best honest page
    assert a.ev("ranking('network science', 0.5)[0][0][1]") == "pg_spam"
    assert a.ev("all(v.visible for v in g.nodes)")
    assert a.ev("{v.name: (v.x, v.y) for v in g.nodes}") == before          # nodes never move
    a.press("Simulate: who wins at each blend")
    a.tick(13)
    sweep = a.ev("st['sweep']")
    assert len(sweep) == a.ev("FARM") + 1 and sweep[-1][1] > sweep[0][1]
    assert "links that were meant to catch it" in a.markdown()
    a.press("Remove the farm")
    assert a.ev("st['farm']") == 0 and a.ev("not any(v.visible for v in g.nodes if v.name.startswith('pg_farm'))")


def test_distributed_search_strategies_and_scaling():
    a = App("ch18-distributed-search")
    assert not a.errors(), a.errors()
    res = {}
    for strat in ("Flooding", "Random walk", "Walk to the best-connected neighbour"):
        a.set("dropdown", "Strategy", strat)
        a.press("To the end")
        res[strat] = a.ev("(st['steps'], st['msgs'], st['found'])")
    assert all(r[2] for r in res.values())
    # flooding: fewest steps, most messages; the hub-seeking walk: fewer messages than the random walk here
    assert res["Flooding"][0] <= min(r[0] for r in res.values())
    assert res["Flooding"][1] > res["Walk to the best-connected neighbour"][1]
    assert res["Walk to the best-connected neighbour"][1] < res["Random walk"][1]
    assert len(a.ev("st['done']")) == 3
    # the paced search runs and stops when found
    a.set("dropdown", "Strategy", "Random walk")
    a.press("Search")
    a.tick(200)
    assert a.ev("st['found']")
    a.click("peer" + str(a.ev("NODES[0] if NODES[0] != st['target'] else NODES[1]")))
    assert a.ev("st['steps']") == 0
    a.tab("How costs grow")
    a.press("Simulate: bigger and bigger networks")
    a.tick(8)
    rows = a.ev("st['simrows']")
    assert len(rows) == 6
    heavy_hub = [r[(2.1, "Walk to the best-connected neighbour")] for r in rows]
    heavy_flood = [r[(2.1, "Flooding")] for r in rows]
    assert max(heavy_hub) < 10 and heavy_flood[-1] > 5 * heavy_flood[0]
    assert "the trick needs heavy tails" in a.markdown()
