"""Output that links to the graph: dicts, sets, f-strings, long groups, chart queries."""
from pathlib import Path

from guess import Session
from tests.test_gython import Recorder

SAMPLE = Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    rec.msgs.clear() if hasattr(rec, "msgs") else None
    return s


def last_out(s, code):
    before = len(s.rec.of("out"))
    assert s.run(code), s.rec.of("error")
    outs = s.rec.of("out")[before:]
    assert outs, f"no linked output from {code!r}"
    return outs[-1]["segs"]


def ids(segs):
    out = []
    for sg in segs:
        if isinstance(sg, dict):
            if "n" in sg:
                out.append(("n", sg["n"]))
            elif "e" in sg:
                out.append(("e", sg["e"]))
            else:
                out += ids(sg.get("g", []))
                out += [tuple(x) for x in sg.get("x", [])]
    return out


def test_dicts_and_sets_link():
    s = _s()
    segs = last_out(s, "{n: n.degree for n in g.nodes[:2]}")
    assert ids(segs) == [("n", 0), ("n", 1)]
    assert segs[0]["g"][0] == "{" and segs[0]["g"][-1] == "}"
    assert len(ids(last_out(s, "set(g.nodes[:3])"))) == 3
    assert ids(last_out(s, "{'a': [v1, v2]}")) == [("n", 0), ("n", 1)]


def test_fstrings_link_and_stay_strings():
    s = _s()
    segs = last_out(s, 'print(f"first is {v1}, then {v2.degree}")')
    assert segs[0] == "first is " and segs[1] == {"n": 0, "t": "v1"}
    assert s.run('__t = f"{v1}-{v2}"') and s.ns["__t"] == "v1-v2" and isinstance(s.ns["__t"], str)
    assert s.run('__t = f"{3.14159:.2f}|{v1!r}|{5:>3}"') and s.ns["__t"] == "3.14|v1|  5"
    segs = last_out(s, 'print(f"hubs {highest(degree, 3)}")')
    assert len(ids(segs)) == 3 and segs[1]["a"] == "highest 3 by degree"


def test_long_groups_link_every_member():
    s = _s()
    segs = last_out(s, "g.nodes")
    assert len(ids(segs)) == len(s.graph.nodes)          # 402: 500 shown, the rest under x
    s.run("for i in range(600): addNode(f'extra{i}')")
    segs = last_out(s, "g.nodes")
    assert len(ids(segs)) == len(s.graph.nodes) == 1002


def test_summary_objects_link_their_elements():
    s = _s()
    s.run("for i in range(4): addDirectedEdge(v1, addNode(f'k{i}'))")
    segs = last_out(s, "offspring(show=False)")
    assert isinstance(segs[0]["g"][0], str) and "R =" in segs[0]["g"][0]
    assert ("n", 0) in ids(segs)


def test_chart_marks_carry_queries():
    s = _s()
    charts = []
    s.emit = lambda m: charts.append(m) if m.get("type") == "chart" else None
    s.run("plotHistogram(degree, 4)")
    qs = [it["q"] for it in charts[-1]["items"]]
    assert qs[0].startswith("(degree >= ") and "<=" in qs[-1]
    for it in charts[-1]["items"]:
        assert s.run(f"__q = {it['q']}") and len(s.ns["__q"]) == it["value"]
    s.run("plotSizes(dept)")
    it = charts[-1]["items"][0]
    assert s.run(f"__q = {it['q']}") and len(s.ns["__q"]) == it["value"]
    s.run("outbreaks(20, beta=0.5, gamma=0.5)")
    bars = charts[-1]["items"]
    assert sum(b["value"] for b in bars) == 20 and all(b["ids"] for b in bars if b["value"])
