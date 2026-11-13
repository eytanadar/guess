"""Batch 13 explainers: fixed points and stability; stability of dynamics on networks."""
import math

import numpy as np

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_fixed_points_one_and_two_variables():
    a = App("ch17-fixed-points")
    # logistic: 0 unstable, 1 stable; a start at x = 0.5 (axis point 20 of 40) ends at 1
    assert a.ev("deriv(0.0)") > 0 > a.ev("deriv(1.0)")
    assert a.ev("g.getNodeByName('fixed1').strokewidth") < a.ev("g.getNodeByName('fixed0').strokewidth")
    grid = a.ev("[(n.name, n.x, n.y) for n in g.nodes if n.name.startswith('ax')]")
    a.click("ax20")
    a.tick(400)
    assert a.ev("ph['done']") and abs(a.ev("ph['pos']") - 1.0) < 1e-3
    assert a.ev("[(n.name, n.x, n.y) for n in g.nodes if n.name.startswith('ax')]") == grid   # only the marker moves
    assert a.ev("chart1() is not None") and "**dies away** (stable)" in a.markdown()
    # two stable states: from just below 0 it goes to -1
    a.set("dropdown", "System", "Two stable states: dx/dt = x − x³")
    a.call("start_at(-0.05)")
    a.call("to_the_end()")
    assert abs(a.ev("ph['pos']") + 1) < 1e-3
    # sin x: stable at odd multiples of pi
    a.set("dropdown", "System", "A pendulum's angle: dx/dt = sin x")
    assert a.ev("deriv(math.pi)") < 0 < a.ev("deriv(0.0)")
    # two variables: the competition model's fixed points have the textbook types
    a.tab("Two variables")
    kinds = a.ev("[classify(jacobian(u, w))[0] for u, w in TWO_D[ph['sys2']]['fixed']]")
    assert kinds == ["unstable node (source)", "stable node (sink)", "stable node (sink)", "saddle (unstable)"]
    a.click("q3_12")                                       # u ~ 0.5, w ~ 2.4: species w wins
    a.tick(500)
    u, w = a.ev("ph['pos']")
    assert a.ev("ph['done']") and abs(u) < 0.01 and abs(w - 2) < 0.01
    assert a.ev("chart2() is not None") and len(a.ev("getDrawings()")) > 225
    # predator-prey has a centre, the damped pendulum a stable spiral and two saddles
    a.set("dropdown", "Phase plane", "Predator and prey")
    assert a.ev("classify(jacobian(1.0, 1.0))[0]") == "centre (neutral)"
    a.set("dropdown", "Phase plane", "Damped pendulum")
    assert a.ev("[classify(jacobian(u, w))[0] for u, w in TWO_D[ph['sys2']]['fixed']]") == \
        ["saddle (unstable)", "stable spiral", "saddle (unstable)"]
    a.press("Random start")
    a.tick(3)
    assert a.ev("btn2.text") == "Pause"
    a.press("Pause")
    assert a.ev("btn2.text") == "Continue"


def test_network_stability_threshold_modes_and_sweep():
    a = App("ch17-network-stability")
    A = a.ev("st['A']")
    k1 = float(np.linalg.eigvalsh(A)[-1])
    assert abs(a.ev("threshold()") - 1 / k1) < 1e-9
    pos = a.ev("[(n.x, n.y) for n in g.nodes]")
    # below the threshold a kick dies away
    a.set("slider", "coupling b", 0.15)
    a.press("Kick the busiest node")
    a.tick(300)
    assert a.ev("st['hist'][-1][1]") < 1e-3
    # above it, it grows to a new state (held by tanh)
    a.set("slider", "coupling b", 0.4)
    a.press("Kick the busiest node")
    a.tick(300)
    assert a.ev("st['hist'][-1][1]") > 1 and a.ev("[(n.x, n.y) for n in g.nodes]") == pos
    assert a.ev("kick_chart() is not None") and "**Unstable**" in a.markdown()
    # the measured long-run rate matches -a + b k1 and crosses zero at the threshold
    a.set("slider", "coupling b", 0.15)
    a.tab("Networks compared")
    a.press("Simulate: growth rate against b")
    a.tick(20)
    pts = a.ev("st['sweep']['pts']")
    assert len(pts) == 11
    for bv, r in pts:                     # (at weak coupling all modes decay at nearly the same rate)
        assert abs(r - (-1 + bv * k1)) < 0.05
    assert "theory" in a.markdown() and len(a.ev("SPECTRA")) == 4
    # inhibition: the most negative eigenvalue decides, and the growing pattern alternates in sign
    a.set("dropdown", "Coupling", "Inhibition (neighbours push the opposite way)")
    kn = float(np.linalg.eigvalsh(A)[0])
    assert abs(a.ev("threshold()") - 1 / -kn) < 1e-9
    a.set("slider", "coupling b", 0.6)
    a.tab("Kick it")
    a.press("Kick the busiest node")
    a.tick(300)
    xs = a.ev("st['x']")
    opposite = sum(1 for i in range(len(xs)) for j in range(len(xs)) if A[i, j] and xs[i] * xs[j] < 0)
    same = sum(1 for i in range(len(xs)) for j in range(len(xs)) if A[i, j] and xs[i] * xs[j] > 0)
    assert opposite > 2 * same
    # two variables per node: the threshold moves to (a + 1)/|kn| and modes turn (complex eigenvalues)
    a.set("dropdown", "Model", "Two variables per node")
    assert abs(a.ev("threshold()") - 2 / -kn) < 1e-9
    a.tab("Modes")
    assert a.ev("mode_chart() is not None") and "2 × 2" in a.markdown()
    a.press("Show the mode that grows first")
    # other networks: the ring and the karate club build and have their own thresholds
    for net in ("Ring (60 nodes, 4 neighbours each)", "Karate club", "A few hubs (60 nodes)"):
        a.set("dropdown", "Network", net)
        assert len(a.ev("st['names']")) == len(a.ev("list(g.nodes)"))
