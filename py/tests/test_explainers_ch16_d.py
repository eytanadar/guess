"""ch16-two-diseases: cross-immunity on the residual network, and coinfection."""
import math

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture moves into the data folder)


def _positions(a):
    return {v._name: (v.x, v.y) for v in a.s.graph._nodes_list()}


def test_cross_immunity_residual_network_and_thresholds():
    a = App("ch16-two-diseases")
    before = _positions(a)
    a.press("Disease 1 only, to the end")
    assert not a.errors(), a.errors()
    assert a.ev("two['phase']") == "between"
    inf1 = a.ev("set(two['inf1'])")
    # the outbreak is exactly the cluster of occupied (u1 < phi1) edges around the first case
    occ = a.ev("occupied(1, phi1.value)")
    adj = a.ev("two['adj']")
    start = a.ev("two['start1']")
    seen, stack = {start}, [start]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen and (min(x, y), max(x, y)) in occ:
                seen.add(y)
                stack.append(y)
    assert seen == inf1
    a.press("Both, to the end")
    inf2 = a.ev("set(two['inf2'])")
    assert inf2 and not (inf1 & inf2)                 # cross-immunity: nobody gets both
    assert _positions(a) == before                     # nobody moves
    text = a.markdown()
    assert "residual network" in text and "Disease 2" in text
    # theory: the residual network is Poisson with mean c(1 - S1); the coexistence threshold is ln c / (c - 1)
    c = 3.0
    assert abs(a.ev("coexistence(3.0)") - math.log(c) / (c - 1)) < 1e-12
    s1, s2 = a.ev("cross_theory(3.0, 0.45, 0.8)")
    assert 0.3 < s1 < 0.5 and 0.2 < s2 < 0.4
    assert a.ev("cross_theory(3.0, 0.6, 1.0)")[1] == 0.0      # past the coexistence threshold: nothing for disease 2


def test_sweeps_follow_theory_and_coinfection_needs_disease_one():
    a = App("ch16-two-diseases")
    a.tab("Two thresholds")
    a.press("Simulate: sweep φ₁ (cross-immunity)")
    a.tick(60)
    assert not a.errors(), a.errors()
    rows = a.ev("averaged(two['sweep'])")
    assert len(rows) == 21
    for p, s1, s2 in rows:
        t1, t2 = a.ev(f"cross_theory(3.0, {p}, phi2.value)")
        if abs(p - 1 / 3) > 0.06 and abs(p - math.log(3) / 2) > 0.06:     # away from the thresholds
            assert abs(s1 - t1) < 0.06 and abs(s2 - t2) < 0.08, (p, s1, t1, s2, t2)
    a.tab("Coinfection")
    a.press("Coinfection to the end")
    assert not a.errors(), a.errors()
    inf1, inf2 = a.ev("set(two['inf1'])"), a.ev("set(two['inf2'])")
    assert inf2 and inf2 <= inf1                       # disease 2 only among people who had disease 1
    a.press("Simulate: sweep φ₁ (coinfection)")
    a.tick(60)
    rows = a.ev("averaged(two['csweep'])")
    assert all(b <= s1 + 1e-9 for _p, s1, b in rows)
    assert all(b == 0 for p, _s1, b in rows if p < 1 / 3)  # no disease 1 epidemic, no disease 2
    assert "reaches 5% of everyone" in a.markdown()
