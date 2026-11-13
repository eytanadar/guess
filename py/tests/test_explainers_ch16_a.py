"""Batch 11 explainers: SI and SIR, and SIS, SIRS and SEIR, in a fully mixed population."""
import math
import statistics

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def test_si_sir_outbreak_equations_and_final_size():
    a = App("ch16-si-sir")
    pos = a.ev("[(n.x, n.y) for n in PEOPLE]")
    a.press("Run")
    a.tick(3)
    assert a.ev("ep['t']") == 3 and a.ev("len(getDrawings())") > 0          # contacts drawn each step
    a.tick(400)
    s, i, r = a.ev("tally()")
    assert a.ev("ep['done']") and i == 0 and r > 100                          # R0 = 3.3: most are infected
    assert a.ev("[(n.x, n.y) for n in PEOPLE]") == pos                       # nobody moves
    assert abs(a.ev("final_size(3.3333333)") - (1 - math.exp(-3.3333333 * a.ev("final_size(3.3333333)")))) < 1e-9
    assert "R₀ = β/γ" in a.markdown() and a.ev("outbreak_chart()") is not None
    # SI: everyone is infected in the end
    a.set("dropdown", "Model", "SI")
    a.press("To the end")
    assert a.ev("tally()") == (0, 144, 0) and "logistic" in a.markdown()
    # the sweep: below R0 = 1 outbreaks stay small, above 2 they track r = 1 - exp(-R0 r)
    a.tab("R₀ and final size")
    a.press("Simulate: final size against R₀")
    a.tick(20)
    pts = a.ev("sweep['pts']")
    assert len(pts) == 9 and max(pts[0.5]) < 0.1
    for r0 in (2.0, 3.0, 4.0):
        assert abs(statistics.mean(pts[r0]) - a.ev(f"final_size({r0})")) < 0.06
    assert a.ev("sweep_chart()") is not None


def test_sis_sirs_seir_endemic_levels_and_phase_plane():
    a = App("ch16-sis-sirs")
    a.press("To the end")
    rows = a.ev("ep['rows']")
    assert a.ev("ep['t']") == 300
    assert abs(statistics.mean(r[3] for r in rows[-100:]) - a.ev("steady()")) < 0.05   # SIS: x* = 1 - 1/R0
    th = a.ev("theory('SIS', 300)")
    assert abs(th[-1][3] - (1 - 0.2 / 0.6)) < 1e-3
    # SIRS: the equations spiral in to the steady state; the run keeps going in waves
    a.set("dropdown", "Model", "SIRS")
    th = a.ev("theory('SIRS', 3000)")
    assert abs(th[-1][3] - a.ev("steady()")) < 1e-3 and abs(th[-1][1] - 0.2 / 0.6) < 1e-3
    xs = [row[3] for row in th[:600]]
    peaks = [k for k in range(1, len(xs) - 1) if xs[k - 1] < xs[k] > xs[k + 1]]
    assert len(peaks) >= 2                                                      # waves
    a.press("Run")
    a.tick(60)
    assert a.ev("ep['t']") == 60 and a.ev("phase_chart()") is not None
    assert "spiral" in a.markdown() or "waves" in a.markdown()
    # SEIR: exposed people appear, and it burns out; its final size matches SIR's
    a.set("dropdown", "Model", "SEIR")
    a.press("To the end")
    assert max(r[2] for r in a.ev("ep['rows']")) > 0 and a.ev("tally()")["I"] == 0
    th = a.ev("theory('SEIR', 2000)")
    r0 = 3.0
    rinf = 0.9
    for _ in range(300):
        rinf = 1 - math.exp(-r0 * rinf)
    assert abs(th[-1][4] - rinf) < 0.02
    # the endemic threshold sweep tracks 1 - 1/R0
    a.tab("Endemic threshold")
    a.press("Simulate: endemic level against R₀")
    a.tick(20)
    pts = a.ev("sweep['pts']")
    assert len(pts) == 10 and max(pts[0.5]) == 0.0
    for r0 in (2.0, 3.0, 5.0):
        assert abs(statistics.mean(pts[r0]) - (1 - 1 / r0)) < 0.05
    assert a.ev("sweep_chart()") is not None and "endemic" in a.markdown()
