from tests.test_gython import Recorder, ev, s  # noqa: F401  (fixture)


def overlays(sess):
    return sess.rec.of("overlay")


def test_hulls_follow_membership(s):
    s.rec.clear()
    s.run("h = createConvexHull(dept == 'IT', randomColor(120))")
    (ov,) = overlays(s)
    assert len(ov["hulls"]) == 1 and len(ov["hulls"][0]["nodes"]) == 2
    assert 0.4 < ov["hulls"][0]["a"] < 0.5
    s.rec.clear()
    s.run("remove(bob)")
    assert overlays(s)[-1]["hulls"][0]["nodes"] == [ev(s, "alice")._id]
    s.rec.clear()
    s.run("h.color = red")
    assert overlays(s)[-1]["hulls"][0]["c"] == 0xFF0000
    s.run("removeConvexHulls()")
    assert overlays(s)[-1]["hulls"] == []


def test_paper_cluster_hulls(s):
    s.rec.clear()
    assert s.run("for clust in groupBy(dept):\n    createConvexHull(clust, randomColor(120))\n")
    assert len(overlays(s)[-1]["hulls"]) == 2


def test_legend_and_background(s):
    s.rec.clear()
    s.run("bob.color = red\nl = Legend()\nl.add(bob, 'managers')\nl.add(bob<->alice, 'talks')")
    entries = overlays(s)[-1]["legends"][0]["entries"]
    assert [e["k"] for e in entries] == ["n", "e"] and entries[0]["c"] == 0xFF0000
    s.run("GradientLegend(yellow, red, 0, 30)")
    assert overlays(s)[-1]["legends"][1]["ramp"]["max"] == 30
    s.run("setDisplayBackground(black)")
    assert overlays(s)[-1]["background"] == 0
    s.run("l.remove()")
    assert len(overlays(s)[-1]["legends"]) == 1


def test_image_nodes_registered_once(s, tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    s.rec.clear()
    s.run(f"(bob, alice).image = {str(img)!r}; (bob, alice).style = 7")
    images = s.rec.of("image")
    assert len(images) == 1 and images[0]["url"].startswith("data:image/png;base64,")
    nodes = s.rec.of("patch")[-1]["nodes"]
    assert {n["img"] for n in nodes} == {images[0]["key"]}
