import math

from guess import Session
from guess.geo import outlines, projector
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    s.run("addNodeField('latitude', DOUBLE, None); addNodeField('longitude', DOUBLE, None)")
    return s


def test_projections():
    merc = projector("mercator")
    assert all(abs(v) < 1e-12 for v in merc(0, 0))
    assert abs(merc(180, 0)[0] - math.pi) < 1e-12 and merc(0, 89)[1] == merc(0, 85)[1]   # clipped
    alb = projector("albers")
    x, y = alb(-96, 37.5)                     # the centre maps to the origin
    assert abs(x) < 1e-12 and abs(y) < 1e-12
    assert alb(-80, 40)[0] > 0 > alb(-110, 40)[0]     # east is right
    assert projector("equirectangular")(10, 20) == (10, 20)


def test_geo_layout_places_north_up_and_picks_a_map():
    s = _s()
    for name, lat, lon in (("nyc", 40.7, -74.0), ("la", 34.0, -118.2), ("chi", 41.9, -87.6), ("nowhere", None, None)):
        s.run(f"n = addNode({name!r})")
        if lat is not None:
            s.run(f"n.latitude, n.longitude = {lat}, {lon}")
    assert s.run("geoLayout()"), s.rec.of("error")
    g = s.graph
    nyc, la, chi = (g.getNodeByName(k) for k in ("nyc", "la", "chi"))
    assert la.x < chi.x < nyc.x                 # west to east
    assert la.y > nyc.y                         # LA is south: lower on screen
    assert s.view.map and s.view.map["rings"]   # all in the US: the states
    printed = "".join(m.get("text", "") for m in s.rec.msgs)
    assert "usa map" in printed and "1 without coordinates" in printed
    assert g.getNodeByName("nowhere").y > max(nyc.y, la.y, chi.y)
    # the map is part of the view: undo and saved sessions keep it
    assert s.view.record()["map"]["rings"]
    s.run("addNode('tokyo').latitude = 35.7")
    s.run("tokyo.longitude = 139.7")
    assert s.run("geoLayout(projection='equirectangular', map='auto', land=lightgray)")
    assert "world map" in "".join(m.get("text", "") for m in s.rec.msgs)
    assert s.view.map["fill"] is not None
    assert s.run("removeMap()") and s.view.map is None
    assert s.run("geoLayout(map=None)") and s.view.map is None
    s.rec.clear()
    assert not s.run("geoLayout(projection='flat earth')")


def test_outlines_load():
    world, usa = outlines("world"), outlines("usa")
    assert len(world) > 100 and len(usa) > 45
    assert all(-180 <= lon <= 180 and -90 <= lat <= 90 for r in world for lon, lat in r)


def test_robustness_curves():
    s = Session(Recorder())
    # a star: losing the hub shatters it; random failures rarely hit the hub
    for i in range(9):
        s.run(f"addEdge(addNode('hub'), addNode('leaf{i}'))")
    assert s.run("__r = robustness(['degree', 'random', 'adaptive'], trials=3)")
    r = s.ns["__r"]
    assert r["degree"][0] == (0.0, 1.0)
    assert r["degree"][1] == (0.1, 0.1)          # the hub goes first: everyone is alone
    assert r["random"][1][1] > 0.1               # on average the hub survives the first removal
    assert r["degree"][-1] == (1.0, 0.0) and r["adaptive"][1] == (0.1, 0.1)
    assert s.run("__b = robustness('betweenness', show=False)")    # computed on demand
    assert s.ns["__b"]["betweenness"][1][1] == 0.1


def test_geo_distance():
    s = _s()
    s.run("a = addNode('lhr'); a.latitude, a.longitude = 51.47, -0.45")
    s.run("b = addNode('jfk'); b.latitude, b.longitude = 40.64, -73.78")
    s.run("addNode('x')")
    s.run("addEdge(lhr, jfk); addEdge(lhr, x)")
    assert s.run("geoDistance()"), s.rec.of("error")
    lens = {(e._n1.name, e._n2.name): e.km for e in s.graph.edges}
    assert 5530 < lens[("lhr", "jfk")] < 5560            # about 5,540 km
    assert lens[("lhr", "x")] is None


def test_loading_a_new_graph_drops_the_map_and_background_image(tmp_path):
    s = _s()
    s.run("n = addNode('nyc'); n.latitude, n.longitude = 40.7, -74.0")
    s.run("m = addNode('la'); m.latitude, m.longitude = 34.0, -118.2")
    assert s.run("geoLayout()") and s.view.map
    s.view.image = {"url": "data:image/png;base64,", "x": 0, "y": 0}
    p = tmp_path / "small.gdf"
    p.write_text("nodedef> name\na\nb\nedgedef> node1,node2\na,b\n")
    assert s.run(f"makeFromGDF({str(p)!r})"), s.rec.of("error")
    assert s.view.map is None and s.view.image is None
    assert s.view.record()["map"] is None
