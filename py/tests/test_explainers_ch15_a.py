"""Batch 11 explainers: random failure, and targeted attack."""
from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_random_failure_follows_theory_and_nodes_stay_put():
    a = App("ch15-random-failure")
    assert not a.errors()
    before = _positions(a)
    assert "Threshold φ_c" in a.markdown()
    # lowering phi only removes nodes; the giant piece shrinks; theory is close for this network
    a.set("slider", "φ, share kept", 0.6)
    s6 = a.ev("show(0.6)")
    assert abs(s6 - a.ev("theory_S(st['pk'], 0.6)")) < 0.12
    a.set("slider", "φ, share kept", 0.15)
    assert a.ev("show(0.15)") < 0.1                       # below phi_c = 0.27: no giant piece
    # failing one by one: each step removes one more node and flashes it
    a.set("slider", "φ, share kept", 1.0)
    a.press("Fail nodes one by one")
    a.tick(5)
    i = a.ev("st['failing']")
    assert i is not None and a.ev(f"st['u'][{i}] >= st['phi']")
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())
    a.tick(400)
    assert a.ev("st['phi']") == 0.0 and _positions(a) == before   # every node failed, none moved
    # the simulation agrees with the generating-function theory
    a.tab("Theory and simulation")
    a.press("Simulate: 4,000 nodes")
    a.tick(12)
    for model in a.ev("MODELS"):
        rec = a.ev(f"st['sim'][{model!r}]")
        assert rec["runs"] == 4
        sim03 = rec["sum"][15] / rec["runs"]
        assert abs(sim03 - a.ev(f"theory_S(sim_pk({model!r}), 0.3)")) < 0.05
    assert a.ev("sim_chart()") is not None
    # heavy tails: the Internet's threshold is tiny, the power grid's is not
    a.tab("Heavy tails")
    pks = a.ev("real_degrees()")
    assert a.ev("threshold(real_degrees()['Internet (ASes 2006)'])") < 0.01
    assert a.ev("threshold(real_degrees()['US power grid'])") > 0.2 and len(pks) == 3
    a.set("dropdown", "Network", "Power-law degrees (α = 2.5)")
    assert not a.errors() and a.ev("threshold(st['pk'])") < 0.2


def test_attack_beats_failure_and_acquaintances_have_more_friends():
    a = App("ch15-targeted-attack")
    assert not a.errors()
    before = _positions(a)
    # attack: hubs in order of degree; theory matches the network
    a.set("slider", "share removed (hubs first)", 0.05)
    assert abs(a.ev("show()") - a.ev("theory_attack(pk_of(st['deg']), 0.05)")) < 0.05
    a.set("slider", "share removed (hubs first)", 0.0)
    a.press("Remove hubs one by one")
    a.tick(2)
    assert a.ev("st['flash']") == a.ev("st['order'][1]") and a.ev("st['deg'][st['order'][0]] == max(st['deg'])")
    a.tick(100)
    assert a.ev("st['k']") == 75 and _positions(a) == before
    assert a.ev("show()") < 0.2 < a.ev("random_at(0.25)")      # 25% by attack destroys what failure does not
    # three networks compared
    a.tab("Random vs attack")
    a.press("Compare the three networks")
    a.tick(5)
    cmp = a.ev("st['cmp']")
    assert len(cmp) == 3
    for r in cmp.values():
        assert a.ev("half_point")(r["attack"]) < a.ev("half_point")(r["random"])
    assert "times" in a.markdown()
    # acquaintance immunisation picks better-connected people than random choice
    a.tab("Acquaintance immunisation")
    a.press("Pick acquaintances")
    a.tick(80)
    pairs = a.ev("st['pairs']")
    deg = a.ev("st['deg']")
    assert len(pairs) == 60
    assert sum(deg[f] for _p, f in pairs) > 1.4 * sum(deg[p] for p, _f in pairs)
    a.press("Simulate: three strategies")
    a.tick(8)
    assert a.ev("strat_chart()") is not None and not a.errors()
    for net in ("Internet sample (300 ASes)", "Power grid region (400 stations)"):
        a.set("dropdown", "Network", net)
        assert not a.errors() and a.ev("len(st['random'])") > 100
