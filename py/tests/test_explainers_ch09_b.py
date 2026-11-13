"""Batch 6 explainers: link prediction and disambiguation (9.4), components and the bow tie (10.1)."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder, _tabs  # noqa: F401


def test_ch09_correcting_predicts_links_and_fixes_names():
    a = App("ch09-correcting")
    assert "Hide" in a.markdown()
    a.press("Hide edges")
    k = len(a.ev("lp['hidden']"))
    assert k == round(0.10 * len(a.ev("EDGES0")))
    assert a.ev("len([e for e in g.edges if e.visible])") == len(a.ev("EDGES0")) - k
    a.press("Predict")
    a.tick(3)
    assert a.ev("lp['shown']") == 3
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())          # the newest guess
    a.press("Predict at once")
    assert a.ev("lp['shown']") == k and 0 < a.ev("lp['hits']") <= k
    assert a.ev("lp['auc']") > 0.8                                                # shared neighbours beat chance
    assert "](guess:n" in a.ev("lp_text()") and a.ev("lp_chart()") is not None
    hits = a.ev("lp['hits']")
    assert a.ev("len([e for e in g.edges if e.pred == 1])") == k - hits          # wrong guesses drawn in red
    a.set("dropdown", "Score", "Random guessing")
    a.press("Predict at once")
    assert abs(a.ev("lp['auc']") - 0.5) < 0.01
    a.press("Simulate: every method")
    a.tick(40)
    sims = a.ev("lp['sims']")
    assert set(sims) == set(a.ev("METHODS")) and all(len(v[40]) == 5 for v in sims.values())
    assert sum(sims["Adamic–Adar"][10]) / 5 > sum(sims["Preferential attachment (kᵢkⱼ)"][10]) / 5
    assert "| Jaccard |" in a.ev("sim_table()")
    a.press("Show every edge")
    assert a.ev("all(e.visible for e in g.edges)") and not a.ev("[e for e in g.edges if e.pred == 1]")
    # disambiguation: three merged names are split, one split person merged, and the numbers match the truth
    a.s.dispatch(_tabs(a)._id, "change", "Disambiguation")
    assert a.ev("graphNames()[0]") == "authors"
    assert sorted(v for v, _ in a.ev("suspects()")) == ["r_jsmith", "r_mgarcia", "r_ywang"]
    assert a.ev("RAWSTATS['dist']") < a.ev("TRUTH['dist']")                      # merged names are shortcuts
    a.press("Split merged names")
    a.tick(1)
    assert "different people" in a.ev("cur['focus']")
    a.tick(10)
    assert a.ev("suspects()") == [] and len(a.ev("cur['log']")) == 3
    a.press("Merge duplicates")
    a.tick(10)
    now = a.ev("stats(cur['G'])")
    truth = a.ev("TRUTH")
    assert (now["n"], now["m"]) == (truth["n"], truth["m"]) and abs(now["dist"] - truth["dist"]) < 1e-9
    assert nx.is_isomorphic(a.ev("cur['G']"), a.ev("T"))
    assert "Larsen" in a.ev("da_text()") and a.ev("da_chart()") is not None     # similar names left apart
    assert len(a.s.graph._nodes_list()) == truth["n"]
    a.press("Back to the records")
    assert a.ev("len(g.nodes)") == a.ev("RAWSTATS['n']")
    a.s.dispatch(_tabs(a)._id, "change", "Link prediction")
    assert a.ev("graphNames()[0]") == "links"


def test_ch10_components_tables_bow_tie_and_reach():
    a = App("ch10-components")
    assert "**67%**" in a.ev("pieces_text()")                     # 404 of the 600 blogs
    a.press("Compare the networks")
    a.tick(15)
    rows = a.ev("cmp_['rows']")
    assert len(rows) == len(a.ev("NETS"))
    assert rows["Karate club"]["big"] == 34 and rows["US airports"]["count"] == 3
    assert "| Les Misérables |" in a.ev("compare_table()")
    a.set("dropdown", "Show", "Citations (visualisation papers)")
    assert a.ev("graphNames()[0]") == "pieces" and a.ev("len(g.nodes)") == 1044
    assert "265 single nodes" in a.ev("pieces_text()") and a.ev("sizes_chart()") is not None
    # the bow tie: sizes from bowTie(), laid out in | core | out
    a.s.dispatch(_tabs(a)._id, "change", "Bow tie")
    assert a.ev("graphNames()[0]") == "blogs"
    sizes = a.ev("SIZES")
    assert sizes["core"] == 224 and sizes["in"] == 89 and sizes["out"] == 69 and sum(sizes.values()) == 600
    xs = {p: a.ev(f"sum(n.x for n in g.nodes if n.bowtie == {p!r}) / len([n for n in g.nodes if n.bowtie == {p!r}])")
          for p in ("in", "core", "out")}
    assert xs["in"] < xs["core"] < xs["out"]
    assert "| core (strongly connected) | 224 |" in a.ev("tie_text()")
    a.press("Follow a path from in to out")
    a.tick(12)
    path = a.ev("tie['path']")
    parts = a.ev("PART")
    assert parts[path[0]] == "in" and parts[path[-1]] == "out" and a.ev("tie['i']") == len(path)
    a.set("dropdown", "Colour", "Political leaning")
    a.click(path[0])
    assert path[0] == a.ev("tie['picked']")
    # reach from a blog in the in-component: it reaches the core and all of out
    a.s.dispatch(_tabs(a)._id, "change", "Reach")
    v = a.ev("sorted(v for v in B if PART[v] == 'in')[0]")
    a.click(v)
    a.tick(40)
    B = a.ev("B")
    assert a.ev("reach['outset']") == nx.descendants(B, v) | {v}
    assert a.ev("reach['inset']") == nx.ancestors(B, v) | {v}
    assert {w for w in B if parts[w] in ("core", "out")} <= a.ev("reach['outset']")
    assert a.ev("reach_chart()") is not None and "**in** part" in a.ev("reach_text()")
