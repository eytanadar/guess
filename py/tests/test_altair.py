"""Altair charts: nodeData/edgeData rows, shorthand types, showChart and the display hook."""
import pytest

pytest.importorskip("altair")

from tests.test_linked_output import _s, ev_  # noqa: E402


def rows_of(spec):
    return next(iter(spec["datasets"].values()))


def test_node_data_rows_and_types():
    s = _s()
    d = ev_(s, "nodeData('degree', 'dept')")
    assert len(d.rows) == 402 and set(d.rows[0]) == {"_node", "name", "degree", "dept"}
    assert d.types["degree"] == "quantitative" and d.types["dept"] == "nominal"
    assert "x" not in ev_(s, "nodeData()").rows[0]                 # display plumbing left out
    assert len(ev_(s, "nodeData(dept == 'dept1', 'degree')").rows) == 43
    e = ev_(s, "edgeData('weight')")
    assert set(e.rows[0]) == {"_edge", "name", "weight"} and "-" in e.rows[0]["name"]


def test_a_chart_value_shows_in_the_dock_with_types_from_the_graph():
    s = _s()
    s.current_cell = 7
    assert s.run("alt.Chart(nodeData('degree', 'dept')).mark_point().encode(x='degree', y='dept')"), s.rec.of("error")
    m = s.rec.of("vega")[-1]
    assert m["id"] == "vega:7:0" and m["cell"] == 7 and "degree" in m["fields"]["n"]
    assert m["spec"]["encoding"]["x"] == {"field": "degree", "type": "quantitative"}
    assert len(rows_of(m["spec"])) == 402
    # the same cell again (Run again, watched, live) redraws the same panel
    s.current_cell = 7
    assert s.run("c = alt.Chart(nodeData('dept')).mark_bar().encode(x='dept', y='count()')\nshowChart(c, 'by dept')")
    m = s.rec.of("vega")[-1]
    assert m["id"] == "vega:7:0" and m["title"] == "by dept"


def test_missing_fields_and_bad_values_say_what_to_do():
    s = _s()
    assert not s.run("alt.Chart(nodeData('degree')).mark_point().encode(x='degree', y='pagerank')")
    assert "nodeData('degree', 'pagerank')" in s.rec.of("error")[-1]["summary"]
    assert not s.run("showChart(3)")
    assert "Altair chart" in s.rec.of("error")[-1]["summary"]


def test_live_charts_recompute_after_changes_and_change_nothing():
    s = _s()
    assert s.run("plotHistogram(degree, 4)")
    c = s.rec.of("chart")[-1]
    assert c["canLive"] and not c["live"]
    assert s.set_live(c["id"], True)
    n = len(s.rec.of("chart"))
    assert s.run("print('nothing changes')") and len(s.rec.of("chart")) == n
    assert s.run("remove(degree > 10)")
    c2 = s.rec.of("chart")[-1]
    assert len(s.rec.of("chart")) == n + 1 and c2["id"] == c["id"] and c2["live"]
    assert sum(i["value"] for i in c2["items"]) == len(s.graph.nodes)
    # an Altair chart's nodeData rows are rebuilt
    s.current_cell = 9
    assert s.run("alt.Chart(nodeData('dept')).mark_bar().encode(x='dept', y='count()')")
    v = s.rec.of("vega")[-1]
    assert s.set_live(v["id"], True)
    assert s.run("remove(dept == 'dept1')")
    assert len(rows_of(s.rec.of("vega")[-1]["spec"])) == len(s.graph.nodes)
    # recomputing never changes the graph or adds undo steps (spread colours nodes when run)
    assert s.run("spread([v1], 'SI', beta=0.5, seed=1)")
    sp = s.rec.of("chart")[-1]["id"]
    assert s.set_live(sp, True)
    colours = [n.color for n in s.graph.nodes]
    steps = len(s.undo_stack)
    assert s.run("v2.size = 30")
    assert [n.color for n in s.graph.nodes] == colours and len(s.undo_stack) == steps + 1
    # a chart that can't be recomputed stops being live, with a note
    assert s.run("Node.tmp = 1.5")
    assert s.run("plotHistogram(tmp)")
    h = s.rec.of("chart")[-1]["id"]
    assert s.set_live(h, True)
    assert s.run("v3.size = 25") and h in s.live_charts
    assert s.run("g.nodes.tmp = None")                # no numbers left: tmp can't be plotted
    assert any(m.get("id") == h and m["live"] is False for m in s.rec.of("liveState"))
    assert h not in s.live_charts


def test_live_charts_everywhere():
    s = _s()
    assert s.run("liveCharts()\nplotSizes(dept)")
    assert s.rec.of("chart")[-1]["live"]
    assert s.run("liveCharts(False)") and not s.live_charts
