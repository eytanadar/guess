"""Batch 10 explainers: the map equation (Infomap) and fitting stochastic block models."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_infomap_code_lengths_walk_and_simulation():
    a = App("ch14-infomap")
    # the planted groups compress the walk; the found partition is at least as good and matches them
    rows = a.ev("compare_rows()")
    one, real, _louv, found = rows
    assert found[2] <= real[2] + 1e-9 < one[2] and found[1] == 3 and found[4] > 0.99
    # map equation of a single module = entropy of the stationary distribution
    import math
    deg = a.ev("st['deg']")
    m2 = sum(deg.values())
    assert abs(one[2] + sum(k / m2 * math.log2(k / m2) for k in deg.values())) < 1e-9
    # walking: Huffman bits per step land close to L
    a.press("Walk")
    a.tick(20)
    assert a.ev("st['steps']") >= 15 and a.ev("g.getNodeByName(st['at']).strokewidth") > 0
    a.press("2,000 steps at once")
    assert abs(a.ev("st['bits'] / st['steps']") - a.ev("L_now()")) < 0.15
    assert abs(a.ev("st['bits1'] / st['steps']") - a.ev("L_one()")) < 0.15
    assert a.ev("walk_chart()") is not None and "bits a step" in a.markdown()
    # clicking moves a node to another module; L changes
    L0 = a.ev("L_now()")
    a.click("n0")
    assert a.ev("st['part_name']") == "edited by hand" and a.ev("L_now()") != L0
    a.set("dropdown", "Partition", "One group (no communities)")
    assert a.ev("len(set(st['part'].values()))") == 1
    # comparing, and the mixing simulation: the planted groups stop compressing as they mix
    a.tab("Compare partitions")
    assert "| partition |" in a.markdown() and a.ev("compare_chart()") is not None
    a.press("Simulate: mix the groups")
    a.tick(20)
    res = a.ev("st['sim']['res']")
    assert len(res) == 8
    lo, hi = min(res), max(res)
    saving = lambda x: sum(r[0] - r[1] for r in res[x]) / len(res[x])
    assert saving(lo) > saving(hi) > -1                  # describing by planted groups saves less as they mix
    assert a.ev("sim_chart()") is not None and "NMI with the planted groups" in a.markdown()
    a.set("dropdown", "Network", "Karate club (34 members)")
    assert not a.errors() and a.ev("len(st['names'])") == 34


def test_sbm_fit_moves_models_and_starts():
    a = App("ch14-sbm-inference")
    # one-move climbs never lower the likelihood, and stop at a local maximum
    a.press("Fit, one move at a time")
    a.tick(60)
    hist = [h[1] for h in a.ev("st['hist']")]
    assert all(b >= x - 1e-9 for x, b in zip(hist, hist[1:])) and a.ev("st['done']")
    assert a.ev("best_move(dict(st['part']))") is None
    # the script's likelihood matches GUESS's fitBlockModel
    a.press("Best of 10 starts")
    assert abs(a.ev("loglik(st['part'])") - (-739.3884)) < 0.01
    assert a.ev("loglik(st['part'])") > a.ev("loglik(st['truth'])")       # the optimum beats the real split
    a.set("dropdown", "Model", "Plain block model")
    a.press("Best of 10 starts")
    assert a.ev("len({st['part'][v] for v in hubs()})") == 1            # the plain model groups the hubs
    a.tab("Block matrix")
    assert "edges to 1" in a.markdown() and a.ev("matrix_chart()") is not None
    a.tab("Plain or degree-corrected")
    md = a.markdown()
    assert "factions except for 2 members" in md and "| Plain block model |" in md
    a.press("Simulate: 20 random starts")
    a.tick(25)
    assert len(a.ev("st['starts']")) == 20 and a.ev("sim_chart()") is not None and "20 climbs" in a.markdown()
    # hand moves change the likelihood; planted groups are found by the degree-corrected fit
    a.set("dropdown", "Network", "Three planted groups (36 nodes)")
    a.tab("Fit")
    a.set("dropdown", "Model", "Degree-corrected block model")
    a.press("Best of 10 starts")
    assert a.ev("nmi(st['part'], st['truth'])") > 0.8
    L0 = a.ev("loglik(st['part'])")
    a.click("n0")
    assert a.ev("loglik(st['part'])") != L0 and not a.errors()
