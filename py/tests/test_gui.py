from tests.test_gython import Recorder, ev, names, s  # noqa: F401


def ui_msgs(sess, op):
    return [m for m in sess.rec.msgs if m["type"] == "ui" and m["op"] == op]


def test_paper_slider_example(s):
    s.rec.clear()
    code = (
        "testSlider = Slider(freq.min, freq.max + 1, label='freq')\n"
        "def hideshow(val):\n"
        "    (freq < val).visible = false\n"
        "    (freq >= val).visible = true\n"
        "testSlider.mouseReleased = hideshow\n"
        "ui.dock(Panel('Threshold', testSlider))\n"
    )
    assert s.run(code), s.rec.of("error")
    (dock,) = ui_msgs(s, "dock")
    slider = dock["panel"]["children"][0]
    assert slider["kind"] == "slider" and slider["props"]["max"] == 31
    s.rec.clear()
    assert s.dispatch(slider["id"], "change", 10)
    assert ev(s, "testSlider.value") == 10
    assert names(ev(s, "Edge.visible == true")) == ["bob->jane", "bob-alice"]


def test_button_lambda_and_updates(s):
    s.run("b = Button('Go', onClick=lambda: center())\nlab = Label('x')\np = Panel('P', b, lab)\nui.dock(p)")
    bid = ev(s, "b")._id
    s.rec.clear()
    s.dispatch(bid, "click")
    assert s.rec.of("center")
    s.rec.clear()
    s.run("lab.text = 'hello'")
    assert ui_msgs(s, "update")[0]["props"] == {"text": "hello"}
    s.run("b.actionPerformed = lambda event: bob.__setattr__('color', 'red')")
    s.dispatch(bid, "click")
    assert ev(s, "bob.color") == "red"


def test_graph_events_and_errors(s):
    s.rec.clear()
    s.run("graphevents.clickNode = lambda n: center([n] + n.getNeighbors())")
    assert ui_msgs(s, "events")[-1]["enabled"] == ["clickNode"]
    s.rec.clear()
    s.dispatch("graph", "clickNode", ["n", ev(s, "bob")._id])
    assert len(s.rec.of("center")[0]["nodes"]) == 3
    s.run("graphevents.mouseEnterNode = lambda n: 1/0")
    s.rec.clear()
    s.dispatch("graph", "mouseEnterNode", ["n", 0])
    assert "ZeroDivisionError" in s.rec.of("error")[0]["text"]
    assert not s.run("graphevents.bogus = 1")


def test_timers(s):
    s.run("count = [0]\ndef tick():\n    count[0] += 1\nt = every(0.5, tick)")
    tid = ev(s, "t")._id
    s.dispatch(tid, "fire"); s.dispatch(tid, "fire")
    assert ev(s, "count[0]") == 2
    s.rec.clear()
    s.run("t.stop()")
    assert ui_msgs(s, "cancelTimer")
    assert not s.dispatch(tid, "fire")
    # a failing repeating timer stops itself
    s.run("bad = every(1, lambda: 1/0)")
    s.dispatch(ev(s, "bad")._id, "fire")
    assert not ev(s, "bad").running


def test_charts(s):
    s.rec.clear()
    s.run("c = plotHistogram(freq, 3)")
    (ch,) = s.rec.of("chart")
    assert [i["value"] for i in ch["items"]] == [3, 0, 1]
    assert sum(len(i["ids"]) for i in ch["items"]) == 4
    s.rec.clear()
    s.run("plotSizesPie(dept)")
    pie = s.rec.of("chart")[0]
    assert pie["kind"] == "pie" and sorted(i["value"] for i in pie["items"]) == [2, 2]
    s.rec.clear()
    s.run("plotDistrib(freq)")
    assert [i["value"] for i in s.rec.of("chart")[0]["items"]] == [30, 10, 5, 2]
    s.run("c.close()")
    assert ui_msgs(s, "close")
