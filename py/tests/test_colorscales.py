"""Built-in colour scales: ColorBrewer, viridis, turbo, categorical schemes."""
from guess import scales
from guess._colorscales import SCALES
from tests.test_linked_output import _s


def ev(s, code):
    assert s.run(f"__r = {code}"), s.rec.of("error")
    return s.ns["__r"]


def test_scales_match_d3():
    v = scales.get("viridis")
    assert v.kind == "sequential" and v.at(0) == "68,1,84" and v.at(1) == "253,231,37"
    assert v.at(0.5) == "33,145,140"                        # d3.interpolateViridis(0.5) = #21918c
    assert scales.get("Viridis_r").at(0) == "253,231,37"     # _r reverses; case doesn't matter
    # ColorBrewer's own discrete classes
    assert scales.get("Blues").colors(3) == ["222,235,247", "158,202,225", "49,130,189"]
    assert scales.get("Set2").colors(2) == ["102,194,165", "252,141,98"]
    assert scales.get("tableau10").colors(1) == ["78,121,167"]
    assert len(scales.get("category10").colors(12)) == 12   # categorical repeats
    assert scales.get("redblue").name == "RdBu" and scales.get("tab10").name == "category10"
    kinds = {k for k, _s, _h in SCALES.values()}
    assert kinds == {"sequential", "diverging", "cyclical", "categorical"} and len(SCALES) >= 70


def test_unknown_scale_suggests():
    s = _s()
    assert not s.run("colorBy(degree, 'virdis')")
    assert "did you mean 'viridis'" in s.rec.of("error")[-1]["summary"]


def test_commands_take_scales():
    s = _s()
    assert s.run("colorBy(degree, 'viridis')")
    top = max(s.graph.nodes, key=lambda n: n.degree)
    assert top.color == "253,231,37"
    assert s.run("colorBy(degree, 'RdBu', midpoint=3)")
    assert s.run("colorize(dept, 'Set2')")
    big = max(ev(s, "groupBy(dept)"), key=len)
    assert big[0].color == "102,194,165"                    # the largest group gets the first colour
    assert s.run("colorize(dept, 'YlGnBu')")
    assert ev(s, "generateColors('Blues', 3)") == ["222,235,247", "158,202,225", "49,130,189"]
    assert ev(s, "colorScale('magma').colors(2)") == ["0,0,4", "252,253,191"]
    lg = ev(s, "GradientLegend(palette='magma', lo=0, hi=10)")
    assert lg._ramp["min"] == 0 and lg._ramp["max"] == 10 and len(lg._ramp["stops"]) == 17
    assert s.run("heatMap(v1, palette='turbo')")
    assert s.run("pieChart([degree, x], palette='Dark2')")
    assert s.run("colorBy(degree, red, blue)")              # colours still work


def test_scales_print_as_swatches():
    s = _s()
    s.rec.clear()
    assert s.run("colorScale('viridis')")
    seg = s.rec.of("out")[-1]["segs"][0]
    assert seg["g"][0] == "viridis " and seg["g"][1]["col"] == [68, 1, 84, 255]
    s.rec.clear()
    assert s.run("colorScales('diverging')")
    rows = s.rec.of("out")[-1]["segs"][0]["tbl"]["rows"]
    assert "RdBu" in [r[0] for r in rows] and all(r[1] == "diverging" for r in rows)
