"""Chart widgets in panels, log-scale charts, plotFrequency/plotLine, and
drawings (drawLine, drawText, drawRect, drawCircle)."""
from tests.test_small_batch import _s, ev


def _charts(s):
    return [m for m in s.rec.of("chart")]


def test_plot_frequency_fractions_and_log():
    s = _s()
    assert s.run("plotFrequency(degree)"), s.rec.of("error")
    m = _charts(s)[-1]
    pts = m["series"][0]["points"]
    assert abs(sum(p[1] for p in pts) - 1) < 1e-9
    assert m["xq"] == "degree == {x}" and m["dots"] and "logX" not in m
    s.rec.clear()
    assert s.run("plotFrequency(degree, log=true, cumulative=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    pts = m["series"][0]["points"]
    assert m["logX"] and m["logY"] and pts[0][1] <= 1 and all(p[0] > 0 for p in pts)
    assert [p[1] for p in pts] == sorted((p[1] for p in pts), reverse=True)


def test_histogram_log_bins_and_plot_line():
    s = _s()
    assert s.run("plotHistogram(degree, 5, log=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["logY"] and len(m["items"]) == 5
    assert sum(it["value"] for it in m["items"]) == ev(s, "len([n for n in g.nodes if n.degree > 0])")
    s.rec.clear()
    assert s.run("plotLine({'a': [(1, 1), (2, 4), (0, 3)], 'b': [(1, 2)]}, title='T', log=true)"), s.rec.of("error")
    m = _charts(s)[-1]
    assert m["title"] == "T" and [x["name"] for x in m["series"]] == ["a", "b"]
    assert m["series"][0]["points"] == [[1.0, 1.0], [2.0, 4.0]]     # x = 0 dropped on a log axis


def test_chart_widget_captures_and_follows_the_graph():
    s = _s()
    assert s.run("c = Chart(lambda: plotHistogram(degree))\nui.dock(Panel('P', c))"), s.rec.of("error")
    assert not _charts(s)                                   # not in the dock
    dock = [m for m in s.rec.of("ui") if m["op"] == "dock"][-1]
    spec = dock["panel"]["children"][0]["props"]["spec"]
    assert spec["type"] == "chart" and spec["kind"] == "bar"
    total = sum(it["value"] for it in spec["items"])
    s.rec.clear()
    assert s.run("remove(v1)"), s.rec.of("error")
    ups = [m for m in s.rec.of("ui") if m["op"] == "update" and "spec" in m["props"]]
    assert ups and sum(it["value"] for it in ups[-1]["props"]["spec"]["items"]) == total - 1
    assert not _charts(s)
    # a failing function shows the error in the widget instead of breaking commands
    assert s.run("bad = Chart(lambda: plotHistogram(nosuchfield))"), s.rec.of("error")
    assert ev(s, "bad.spec")["type"] == "error"
    # plot commands outside a Chart still go to the dock
    assert s.run("plotHistogram(degree)") and _charts(s)


def test_drawings_record_undo_and_session_roundtrip(tmp_path):
    s = _s()
    assert s.run("l = drawLine(0, 0, 100, 0, color=red, style='dashed', arrow=true)\n"
                 "t = drawText(50, -10, 'hello', size=20)\n"
                 "r = drawRect(0, 0, 10, 10, fill='255,0,0,60')\n"
                 "c = drawCircle(5, 5, 30)"), s.rec.of("error")
    ds = s.view.record()["drawings"]
    assert [d["k"] for d in ds] == ["line", "text", "rect", "circle"]
    assert ds[0]["st"] == "dashed" and ds[0]["ar"] and ds[0]["c"] == 0xFF0000 and ds[1]["c"] is None
    assert ds[2]["f"] == 0xFF0000 and abs(ds[2]["fa"] - 60 / 255) < 0.01
    assert repr(ev(s, "t")).endswith("text 'hello'>") and len(ev(s, "getDrawings()")) == 4
    assert s.run("t.remove()") and len(s.view.drawings) == 3
    assert s.run("undo()") and len(s.view.drawings) == 4
    path = tmp_path / "d.guess"
    assert s.run(f"saveSession({str(path)!r})"), s.rec.of("error")
    assert s.run("clearDrawings()") and s.view.drawings == []
    assert s.run(f"makeFromSession({str(path)!r})"), s.rec.of("error")
    assert [d["k"] for d in s.view.drawings] == ["line", "text", "rect", "circle"]
    assert not s.run("drawLine(0, 0, 1, 1, style='wavy')")
    assert not s.run("drawText(0, 0, 'x', anchor='left')")
