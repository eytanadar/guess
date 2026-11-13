"""Batch 10 explainers: testing community detection on benchmarks, and structure beyond communities."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_measuring_performance_benchmark_sweep_and_real_networks():
    a = App("ch14-measuring-performance")
    assert a.ev("st['planted']") >= 5 and len(a.s.graph.nodes) == 250
    a.press("Find communities")
    sc = a.ev("scores()")
    assert sc["nmi"] > 0.9 and "NMI" in a.markdown()                  # μ = 0.2: Louvain finds the planted groups
    # misplaced nodes get red rings; the others none
    wrong = a.ev("len([v for v in g.nodes if v.strokewidth >= 3])")
    assert wrong < 25
    a.set("slider", "mixing μ", 0.65)
    a.press("Find communities")
    assert a.ev("scores()")["nmi"] < 0.5                              # blurred: lost
    a.press("Run every method")
    rows = a.ev("st['table']")
    assert [r[0] for r in rows] == a.ev("METHODS") and all(r[2] is None or 0 <= r[2] <= 1 for r in rows)
    # the paced sweep fills NMI curves that fall with μ
    a.tab("Simulate")
    a.press("Simulate: μ from 0.05 to 0.7")
    a.tick(30)
    sim = a.ev("st['sim']")
    lou = [sum(v) / len(v) for _mu, v in sorted(sim["Louvain"].items())]
    assert len(lou) == 13 and lou[0] > 0.95 and lou[-1] < 0.3
    assert a.ev("sim_chart()") is not None and "drops below NMI 0.5" in a.ev("sim_text()")
    a.tab("Real networks")
    text = a.ev("real_text()")
    assert "Karate club" in text and "Political blogs" in text and "ground truth" in text


def test_other_structure_tabs():
    a = App("ch14-other-structure")
    # overlapping: link communities and clique percolation find the three circles and the three shared people
    a.press("Link communities")
    assert a.ev("ov['found']") == 3
    assert a.ev("sorted(v.name for v in g.nodes if v.link_count > 1)") == ["Ana", "Ben", "Cai"]
    a.press("Clique percolation")
    assert a.ev("ov['found']") == 3 and a.ev("sorted(v.name for v in ov['cpm_multi'])") == ["Ana", "Ben", "Cai"]
    a.press("One group each (Louvain)")
    assert "forced to choose" in a.markdown()
    # hierarchy: two groups are the departments, four the teams
    a.tab("Hierarchy")
    a.set("slider", "groups", 2)
    assert "two departments: **1.00**" in a.ev("hier_text()")
    a.set("slider", "groups", 4)
    assert a.ev("dendro_chart()") is not None
    a.press("Merge step by step")
    a.tick(60)
    assert a.ev("HI['step']") == 39
    # core and periphery: the planted core is found, and the plain block model agrees
    a.tab("Core and periphery")
    a.press("Find core and periphery")
    assert a.ev("cp['res']['core']") == 12 and a.ev("all((v.core == 1) == (v.block == 0) for v in g.nodes)")
    a.press("Plain block model, 2 groups")
    assert a.ev("cp['sbm_nmi']") > 0.9 and a.ev("core_matrix()") is not None
    # ranking: rank tracks hidden strength, scrambled contests don't
    a.tab("Ranking")
    a.press("Rank them")
    assert a.ev("RK['share']") > 0.75
    assert a.ev("spearman({v.name: v.rank for v in g.nodes}, RK['strength'])") > 0.8
    a.press("Scramble who won")
    a.press("Rank them")
    assert abs(a.ev("spearman({v.name: v.rank for v in g.nodes}, RK['strength'])")) < 0.4
    a.press("Simulate: clearer and murkier contests")
    a.tick(40)
    sim = a.ev("RK['sim']")
    assert len(sim) == 28 and sim[-1][1] > sim[0][1]
    # latent space: the hidden positions are perfect, a scatter isn't, a layout from the edges recovers much
    a.tab("Latent space")
    a.press("Hidden positions")
    assert "correlation **1.00**" in a.ev("latent_text()")
    a.press("Scatter")
    a.press("Lay out from the edges")
    corr = float(a.ev("latent_text()").split("correlation **")[1].split("**")[0])
    assert corr > 0.6
