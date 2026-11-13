"""Batch 11 explainers: two diseases and complex contagion; epidemics on networks."""
import random

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_epidemics_on_networks():
    a = App("ch16-epidemics-on-networks")
    assert a.ev("graphNames()") == ["random", "hubs", "school"]
    assert a.ev("len(adj['school'])") == 256
    # hubs: same people and nearly the same contacts as the random network, but a larger <k^2>/<k>
    assert abs(a.ev("mean_degree('hubs')") - a.ev("mean_degree('random')")) < 1
    assert a.ev("excess('hubs')") > 1.5 * a.ev("excess('random')")
    before = _positions(a)
    a.press("Start an outbreak")
    a.tick(6)
    assert a.ev("sim['t']") >= 1 and a.ev("sim['curve'][0][2]") > 0
    # every transmission went along an edge, from someone infected
    for pair in a.ev("sim['tree']"):
        u, v = tuple(pair)
        assert v in a.ev(f"adj['random'][{u!r}]")
    a.press("To the end")
    assert a.ev("sim['curve'][-1][2]") == 0 and "**Over.**" in a.markdown()
    assert _positions(a) == before                                    # nodes never move
    assert a.ev("outbreak_chart()") is not None
    # the explainer's step follows spread()'s rules: compare outbreak sizes with outbreaks()
    mine = [a.ev(f"run_sir('random', 0.1, 0.2, random.Random({k}))") for k in range(300)]
    theirs = a.ev("outbreaks(runs=300, beta=0.1, gamma=0.2, show=false, seed=3)")
    assert abs(sum(mine) / len(mine) * 200 - theirs.mean) < 15
    # hubs are reached first: the newly infected early on have more contacts than average
    a.tab("Who catches it first")
    random.seed(0)
    early = []
    for k in range(5):
        a.call(f"sim['rnd'] = random.Random({k})")
        a.press("Run an outbreak to the end")
        nd = a.ev("sim['newdeg']")
        if len(nd) > 4:
            early.append(sum(d for _t, d in nd[1:4]) / 3)
    assert early and sum(early) / len(early) > a.ev("mean_degree('random')")
    # simulate: simulated sizes follow the configuration-model prediction well above the threshold
    a.tab("Simulate")
    a.press("Simulate: sweep β")
    a.tick(15)
    rows = a.ev("sim['sweep']")
    assert len(rows) == 12
    for b, size, share in rows:
        if b >= 0.13:
            assert abs(size - a.ev(f"final_size_cm('random', T_of({b}, 0.2))")) < 0.1
    assert a.ev("sweep_chart()") is not None and "| β |" in a.markdown()
    # compare the three networks
    a.tab("Compare networks")
    a.press("Compare the three networks")
    a.tick(4)
    cmp_ = a.ev("sim['cmp']")
    assert set(cmp_) == {"random", "hubs", "school"} and cmp_["school"][0] > cmp_["random"][0]
    # switching networks and clicking a node to start there
    a.set("dropdown", "Network", "School contacts (simulated)")
    assert a.ev("graphNames()[0]") == "school"
    a.tab("Outbreak")
    a.click("T1A")
    assert a.ev("sim['seed']") == "T1A" and a.ev("sim['state']['T1A']") == "I"
    a.press("One step")
    assert a.ev("sim['t']") == 1
    assert not a.errors()


def test_two_diseases_and_complex_contagion():
    a = App("ch16-complex-contagion")
    assert a.ev("graphNames()[0]") == "two diseases"
    before = _positions(a)
    a.press("Start both diseases")
    a.tick(3)
    curve = a.ev("co['curve']")
    assert curve[0] == (0, 1, 1, 1)
    # each new infection crossed an edge from someone who had that disease
    for pair in a.ev("co['edgesA']"):
        u, v = tuple(pair)
        assert v in a.ev(f"co['adj'][{u}]")
    a.press("To the end")
    assert not a.ev("co['freshA']") and not a.ev("co['freshB']")
    assert _positions(a) == before
    assert len(a.ev("poisson_network(1500, 4.0, random.Random(77))")) == 1500
    a.tab("Simulate the jump")
    a.press("Simulate: alone and helped")
    a.tick(15)
    rows = a.ev("co['sweep']")
    assert len(rows) == 13 and rows[-1][1] > 0.6 and rows[0][2] < 0.1
    # helping each other: around p = 1/c the helped outbreak is far bigger than the lone one
    assert any(h > a_ + 0.3 for p, a_, h, _ma, _mh in rows if 0.2 <= p <= 0.3)
    assert a.ev("co_sweep_chart()") is not None
    # complex contagion: the ring spreads, full rewiring stalls with two contacts needed
    a.tab("Complex contagion")
    assert a.ev("graphNames()[0]") == "ideas"
    a.press("Spread the idea")
    a.tick(80)
    assert a.ev("cx['curve'][-1][1]") == 150
    for pair in a.ev("cx['edges']"):
        u, v = tuple(pair)
        assert v in a.ev(f"cx['adj'][{u}]")
    a.set("dropdown", "Network", "Rewired at random (100%)")
    a.press("Spread the idea")
    a.tick(80)
    assert a.ev("cx['curve'][-1][1]") < 30 and "stalled" in a.markdown()
    a.set("slider", "contacts needed", 1)
    a.press("Start again")
    a.press("Spread the idea")
    a.tick(80)
    assert a.ev("cx['curve'][-1][1]") == 150
    a.click("w40")
    assert a.ev("cx['start']") == 40
    a.tab("Shortcuts help or hurt")
    a.press("Simulate: rewire more and more")
    a.tick(10)
    sw = a.ev("cx['sweep']")
    assert len(sw) == 7 and sw[0][1] == 1.0 and sw[-1][1] < 0.2      # complex contagion stalls when rewired
    assert sw[0][2] > 3 * sw[-1][2]                                     # simple contagion speeds up
    assert a.ev("cx_sweep_chart()") is not None
    assert not a.errors()
